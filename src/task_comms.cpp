#include <WiFi.h>
#include <ESPmDNS.h>
#include <esp_wifi.h>
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
    uint32_t last_msg_time = millis();

    for (;;) {
        if (!client.connected()) {
            client.stop();

            if (SystemManager::instance().motorActive) {
                Serial.println("[COMMS] Servidor caido. Iniciando homing...");

                HwCommand flushCmd;
                while (xQueueReceive(SystemManager::instance().queueCommands, &flushCmd, 0));
                HwResult flushRes;
                while (xQueueReceive(SystemManager::instance().queueResults, &flushRes, 0));

                HwCommand cmdHome;
                cmdHome.type = HW_CMD_HOME;
                xQueueSend(SystemManager::instance().queueCommands, &cmdHome, portMAX_DELAY);

                HwResult homeRes;
                uint32_t t_home = millis();
                while (millis() - t_home < 15000) {
                    if (xQueueReceive(SystemManager::instance().queueResults, &homeRes, pdMS_TO_TICKS(200)) == pdPASS) {
                        if (homeRes.type == HW_RES_HOME_DONE) break;
                    }
                }

                SystemManager::instance().motorActive = false;
                SystemManager::instance().justHomed   = true;
                Serial.println("[COMMS] Homing completado. Esperando servidor...");
            }

            SystemManager::instance().changeState(SYNC_CONTROL);

            if (!connectToServer()) {
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }

            Payload_HelloReq req;
            WiFi.macAddress(req.mac_address);
            sendPacket(MSG_HELLO_REQ, &req, sizeof(req));
            last_msg_time = millis();
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        if (millis() - last_msg_time > 5000) {
            Serial.println("[ERR] Servidor zombie (timeout). Reiniciando red...");
            client.stop(); 
            continue;
        }

        if (client.available() >= sizeof(PacketHeader)) {
            last_msg_time = millis(); 
            
            PacketHeader header;
            client.readBytes((uint8_t*)&header, sizeof(PacketHeader));
            
            if (header.length > 128) { 
                 while(client.available()) client.read();
                 continue; 
            }
            
            if (header.length > 0) {
                uint32_t t_wait = millis();
                while (client.available() < header.length) {
                    if (millis() - t_wait > 1500) break;
                    vTaskDelay(1);
                }
                if (client.available() < header.length) {
                    Serial.println("[COMMS] Timeout recibiendo payload. TCP corrupto. Reiniciando...");
                    client.stop(); 
                    continue; 
                }
                client.readBytes(buffer, header.length);
            }

            switch (header.type) {
                case MSG_HELLO_ACK: {
                    Payload_HelloAck* p = (Payload_HelloAck*)buffer;
                    SystemManager::instance().radarId = p->assigned_id;
                    SystemManager::instance().current_angle_logic = p->saved_angle;
                    SystemManager::instance().sweep_direction_up = true;

                    HwCommand cmdInit;
                    if (SystemManager::instance().justHomed) {
                        cmdInit.type  = HW_CMD_MOVE;
                        Serial.printf("[COMMS] Post-homing: moviendo a posicion guardada %.1f°\n", p->saved_angle);
                    } else {
                        cmdInit.type  = HW_CMD_SYNC_POS;
                    }
                    cmdInit.param = p->saved_angle;
                    xQueueSend(SystemManager::instance().queueCommands, &cmdInit, portMAX_DELAY);
                    SystemManager::instance().justHomed = false;

                    HwResult res;
                    xQueueReceive(SystemManager::instance().queueResults, &res, pdMS_TO_TICKS(1000));
                    HwResult flush;
                    while (xQueueReceive(SystemManager::instance().queueResults, &flush, 0));

                    SystemManager::instance().changeState(RADAR);
                    SystemManager::instance().motorActive = true;

                    while (client.available()) client.read();
                    last_msg_time = millis();
                    break;
                }

                case MSG_SUPERFRAME_START: {
                    // Anclamos t0 aquí: SF_START tiene jitter mínimo de red.
                    // El servidor envía start_delay_ms relativo a este instante,
                    // así execution_time_ms no depende del jitter de SLOT_ASSIGN.
                    SystemManager::instance().t0_last_superframe = millis();
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
                        // t0_last_superframe ya fue fijado en MSG_SUPERFRAME_START.
                        // execution_time_ms = t0_sf_start + start_delay_ms (relativo al SF).
                        HwCommand cmd;
                        cmd.type = HW_CMD_EXECUTE_SLOT;
                        cmd.param = p->confirmed_angle;
                        cmd.execution_time_ms = SystemManager::instance().t0_last_superframe + p->start_delay_ms;
                        
                        HwCommand flushCmd;
                        while(xQueueReceive(SystemManager::instance().queueCommands, &flushCmd, 0));
                        xQueueSend(SystemManager::instance().queueCommands, &cmd, portMAX_DELAY);
                        
                        SystemManager::instance().current_angle_logic = p->confirmed_angle;
                    }
                    break;
                }

                case MSG_REPORT_REQ: {
                    HwResult res;
                    // 300ms: en operación normal el resultado ya está listo cuando llega REPORT_REQ.
                    // Fallo rápido evita bloquear el siguiente SF_START si el timing fue a la deriva.
                    if (xQueueReceive(SystemManager::instance().queueResults, &res, pdMS_TO_TICKS(300)) == pdPASS) {
                        if (res.type == HW_RES_SLOT_DONE) {
                            Payload_DataReport rep;
                            rep.radar_id = SystemManager::instance().radarId;
                            rep.angle = res.angle;
                            rep.distance_cm = res.value;
                            rep.measure_timestamp = millis();
                            sendPacket(MSG_DATA_REPORT, &rep, sizeof(Payload_DataReport));
                        }
                    } else {
                        last_msg_time = millis();
                    }
                    break;
                }
            }
        } else {
             // Retardo solo si no hay nada en el buffer TCP
             vTaskDelay(1);
        }
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
    esp_wifi_set_ps(WIFI_PS_NONE);

    static IPAddress cachedServerIP(0, 0, 0, 0);

    if (cachedServerIP != IPAddress(0, 0, 0, 0)) {
        Serial.printf("[COMMS] Reconectando a IP cacheada %s...\n", cachedServerIP.toString().c_str());
        if (client.connect(cachedServerIP, SERVER_PORT)) {
            client.setNoDelay(true);
            client.setTimeout(1500);
            return true;
        }
        Serial.println("[COMMS] IP cacheada no responde. Redescubriendo...");
        cachedServerIP = IPAddress(0, 0, 0, 0);
    }

    IPAddress serverIP;
    for (int i = 0; i < 2; i++) {
        serverIP = MDNS.queryHost(SERVER_HOSTNAME);
        if (serverIP != IPAddress(0, 0, 0, 0)) break;
        Serial.printf("[COMMS] mDNS: buscando %s.local... (%d/2)\n", SERVER_HOSTNAME, i + 1);
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    if (serverIP == IPAddress(0, 0, 0, 0)) {
        serverIP = WiFi.gatewayIP();
        Serial.printf("[COMMS] mDNS sin respuesta. Probando gateway: %s\n", serverIP.toString().c_str());
    }

    if (serverIP == IPAddress(0, 0, 0, 0)) {
        Serial.println("[COMMS] Sin ruta al servidor.");
        return false;
    }

    Serial.printf("[COMMS] Conectando a %s...\n", serverIP.toString().c_str());
    if (client.connect(serverIP, SERVER_PORT)) {
        client.setNoDelay(true);
        client.setTimeout(1500);
        cachedServerIP = serverIP;
        return true;
    }

    IPAddress gw = WiFi.gatewayIP();
    if (gw != serverIP && gw != IPAddress(0, 0, 0, 0)) {
        Serial.printf("[COMMS] Reintentando con gateway: %s\n", gw.toString().c_str());
        if (client.connect(gw, SERVER_PORT)) {
            client.setNoDelay(true);
            client.setTimeout(1500);
            cachedServerIP = gw;
            return true;
        }
    }
    return false;
}

void sendPacket(uint8_t type, void* payload, uint16_t length) {
    uint8_t out_buf[128]; 
    PacketHeader header;
    header.type = type;
    header.length = length;
    
    memcpy(out_buf, &header, sizeof(PacketHeader));
    if (length > 0) memcpy(out_buf + sizeof(PacketHeader), payload, length);
    
    client.write(out_buf, sizeof(PacketHeader) + length);
}