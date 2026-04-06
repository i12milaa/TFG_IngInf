#include <WiFi.h>
#include "task_comms.h"
#include "config.h"
#include "system.h"
#include "comms_protocol.h"
#include "task_radar.h"

WiFiClient client;

bool connectToServer();
void sendPacket(uint8_t type, void* payload, uint16_t length);
float calcularSiguienteAngulo();

void TaskComms(void *pvParameters) {
    uint8_t buffer[128];

    for (;;) {
        // ESTADO 2: WAITING FOR CONNECTION (Manejo robusto de reconexión)
        if (!client.connected()) {
            client.stop();

            if (!connectToServer()) {
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }

            // ESTADO 3: SYNC (Solicita ID al servidor)
            Payload_HelloReq req;
            WiFi.macAddress(req.mac_address);
            sendPacket(MSG_HELLO_REQ, &req, sizeof(req));
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        // ESTADO 4: RADAR (Procesamiento de Supertrama)
        if (client.available() >= sizeof(PacketHeader)) {
            PacketHeader header;
            client.readBytes((uint8_t*)&header, sizeof(PacketHeader));
            
            if (header.length > 128) { 
                 while(client.available()) client.read();
                 continue; 
            }
            
            if (header.length > 0) {
                uint32_t t_wait = millis();
                while (client.available() < header.length) {
                    if (millis() - t_wait > 100) break;
                    vTaskDelay(1);
                }
                if (client.available() < header.length) {
                    client.stop(); 
                    continue; 
                }
                client.readBytes(buffer, header.length);
            }

            switch (header.type) {
                case MSG_HELLO_ACK: {
                    Payload_HelloAck* p = (Payload_HelloAck*)buffer;
                    SystemManager::instance().radarId = p->assigned_id;
                    SystemManager::instance().current_angle_logic = 0.0f;
                    SystemManager::instance().sweep_direction_up = true;
                    SystemManager::instance().changeState(STATE_RADAR);
                    break;
                }

                case MSG_SUPERFRAME_START: {
                    float nextAngle = calcularSiguienteAngulo();
                    Payload_AngleReq req;
                    req.radar_id = SystemManager::instance().radarId;
                    req.current_angle = SystemManager::instance().current_angle_logic;
                    req.requested_angle = nextAngle;
                    sendPacket(MSG_ANGLE_REQ, &req, sizeof(Payload_AngleReq));
                    break;
                }

                case MSG_SLOT_ASSIGN: {
                    Payload_SlotAssign* p = (Payload_SlotAssign*)buffer;
                    if (p->radar_id == SystemManager::instance().radarId) {
                        SystemManager::instance().t0_last_superframe = millis();
                        
                        HwCommand cmd;
                        cmd.type = HW_CMD_EXECUTE_SLOT;
                        cmd.param = p->confirmed_angle;
                        // Calcula el tiempo absoluto en el que debe ocurrir el disparo
                        cmd.execution_time_ms = SystemManager::instance().t0_last_superframe + p->start_delay_ms;
                        
                        // Limpia comandos viejos (si los hubiera) y encola la orden a la API del radar
                        HwCommand flushCmd;
                        while(xQueueReceive(SystemManager::instance().queueCommands, &flushCmd, 0));
                        xQueueSend(SystemManager::instance().queueCommands, &cmd, portMAX_DELAY);
                        
                        SystemManager::instance().current_angle_logic = p->confirmed_angle;
                    }
                    break;
                }

                case MSG_REPORT_REQ: {
                    HwResult res;
                    // Espera generosa (1000ms) para garantizar que el hardware ha terminado la física
                    if (xQueueReceive(SystemManager::instance().queueResults, &res, pdMS_TO_TICKS(1000)) == pdPASS) {
                        if (res.type == HW_RES_SLOT_DONE) {
                            Payload_DataReport rep;
                            rep.radar_id = SystemManager::instance().radarId;
                            rep.angle = res.angle;
                            rep.distance_cm = res.value;
                            rep.measure_timestamp = millis(); 
                            sendPacket(MSG_DATA_REPORT, &rep, sizeof(Payload_DataReport));
                        }
                    }
                    break;
                }
            }
        }
        vTaskDelay(1);
    }
}

float calcularSiguienteAngulo() {
    float current = SystemManager::instance().current_angle_logic;
    bool up = SystemManager::instance().sweep_direction_up;
    float step = RADAR_STEP_ANGLE; 
    float min_lim = RADAR_MIN_ANGLE;
    float max_lim = RADAR_MAX_ANGLE;

    float next;
    if (up) {
        next = current + step;
        if (next >= max_lim) { next = max_lim; SystemManager::instance().sweep_direction_up = false; }
    } else {
        next = current - step;
        if (next <= min_lim) { next = min_lim; SystemManager::instance().sweep_direction_up = true; }
    }
    return next;
}

bool connectToServer() {
    WiFi.setSleep(false);
    if (client.connect(SERVER_IP, SERVER_PORT)) {
        client.setNoDelay(true); 
        return true;
    }
    return false;
}

void sendPacket(uint8_t type, void* payload, uint16_t length) {
    PacketHeader header;
    header.type = type;
    header.length = length;
    client.write((uint8_t*)&header, sizeof(PacketHeader));
    if (length > 0) client.write((uint8_t*)payload, length);
}