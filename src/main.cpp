// main.cpp
#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <esp_wifi.h>
#include "config.h"
#include "system.h"
#include "task_comms.h"
#include "task_radar.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

struct NodeProfile {
    const char* mac;
    uint8_t     nodeId;
    bool        motorDirInvert;
    int         reedTriggerLevel;  
};

static const NodeProfile PROFILES[] = {
    {"88:13:BF:C8:40:30",   1,  false,     HIGH},  
    {"F0:24:F9:44:0A:20",   2,  true,    LOW},  
    {"CC:DB:A7:98:CC:E4",   3,  true,    HIGH}, 
};

void applyNodeProfile() {
    String mac = WiFi.macAddress();
    Serial.println("\n========================================");
    for (const auto& p : PROFILES) {
        if (mac.equalsIgnoreCase(p.mac)) {
            SystemManager::instance().motorDirInvert   = p.motorDirInvert;
            SystemManager::instance().reedTriggerLevel = p.reedTriggerLevel;
            Serial.printf("  NODO  : N%d\n", p.nodeId);
            Serial.printf("  MAC   : %s\n", mac.c_str());
            Serial.printf("  Motor : %s\n", p.motorDirInvert ? "INVERTIDO" : "normal");
            Serial.printf("  Reed  : %s\n", p.reedTriggerLevel == HIGH ? "HIGH (NC)" : "LOW (NO)");
            Serial.println("========================================\n");
            return;
        }
    }
    Serial.printf("  NODO  : DESCONOCIDO\n");
    Serial.printf("  MAC   : %s\n", mac.c_str());
    Serial.println("  Añade esta MAC a PROFILES[] en main.cpp");
    Serial.println("========================================\n");
}

static const struct { const char* ssid; const char* pass; } KNOWN_NETWORKS[] = {
    {WIFI_SSID_1, WIFI_PASS_1},
    {WIFI_SSID_2, WIFI_PASS_2},
};
static volatile bool _wifi_reconnect_needed = false;

void tryConnectWiFi() {
    // Si ya está conectado o intentando conectar, no interrumpir.
    wl_status_t st = WiFi.status();
    if (st == WL_CONNECTED || st == WL_IDLE_STATUS) return;

    Serial.println("[WIFI] Escaneando redes...");
    int found = WiFi.scanNetworks();
    if (found <= 0) {
        Serial.printf("[WIFI] Sin redes (scan=%d). Reintentando más tarde.\n", found);
        return;
    }
    for (const auto& net : KNOWN_NETWORKS) {
        if (strlen(net.ssid) == 0) continue;
        for (int i = 0; i < found; i++) {
            if (WiFi.SSID(i).equals(net.ssid)) {
                Serial.printf("[WIFI] Red encontrada: %s. Conectando...\n", net.ssid);
                WiFi.scanDelete();
                WiFi.begin(net.ssid, net.pass);
                return;
            }
        }
    }
    WiFi.scanDelete();
    Serial.println("[WIFI] Ninguna red conocida en rango.");
}

TaskHandle_t hTaskComms = NULL;
TaskHandle_t hTaskRadar = NULL;

void WiFiEvent(WiFiEvent_t event) {
    switch(event) {
        case ARDUINO_EVENT_WIFI_STA_GOT_IP:
            Serial.print("[WIFI] Conectado! IP: ");
            Serial.println(WiFi.localIP());
            MDNS.begin("esp-radar");
            if (SystemManager::instance().currentState == WAITING_FOR_CONNECTION) {
                SystemManager::instance().changeState(SYNC_CONTROL);
            }
            break;

        case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
            Serial.println("[WIFI] Desconectado.");
            SystemManager::instance().changeState(WAITING_FOR_CONNECTION);
            _wifi_reconnect_needed = true;
            break;
    }
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(115200);
    pinMode(PIN_LED, OUTPUT);

    WiFi.mode(WIFI_STA);
    applyNodeProfile();

#if DEBUG_HARDWARE_TEST == 1
    Serial.println("\n========================================");
    Serial.println("       MODO DEBUG HARDWARE");
    Serial.println("========================================");

    String myMac = WiFi.macAddress();
    struct NodeInfo { const char* mac; int id; float x; float y; float theta; };
    static const NodeInfo NODES[] = {
        {"F0:24:F9:44:0A:20", 2,  34.64f, 20.0f,  30.0f},
        {"88:13:BF:C8:40:30", 1,   0.0f,  40.0f,  90.0f},
        {"CC:DB:A7:98:CC:E4", 3, -34.64f, 20.0f, 150.0f},
    };
    const NodeInfo* myNode = nullptr;
    for (const NodeInfo& n : NODES) {
        if (myMac.equalsIgnoreCase(n.mac)) { myNode = &n; break; }
    }

    RadarHardware hw_test;
    hw_test.init();
    delay(500);

    while (true) {
        Serial.println("\n========================================");
        if (myNode) {
            Serial.printf("  MAC   : %s\n", myMac.c_str());
            Serial.printf("  Nodo  : N%d\n", myNode->id);
            Serial.printf("  Pos   : x=%.2f  y=%.2f  theta=%.1f\n",
                myNode->x, myNode->y, myNode->theta);
        } else {
            Serial.printf("  MAC   : %s\n", myMac.c_str());
            Serial.println("  Nodo  : DESCONOCIDO");
        }
        Serial.printf("  Perfil: motorInv=%d  reed=%s\n",
            SystemManager::instance().motorDirInvert,
            SystemManager::instance().reedTriggerLevel == HIGH ? "HIGH(NC)" : "LOW(NO)");
        Serial.println("========================================");

        Serial.println("\n[FASE 0a] Sensor ultrasonico - duracion bruta (10 disparos)");
        Serial.println("  Disparo | ECHO antes | Duracion (us) | Dist(cm) | Diagnostico");
        Serial.println("  --------|------------|---------------|----------|------------");
        for (int i = 0; i < 10; i++) {
            int echo_before = digitalRead(PIN_ECHO);
            digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(5);
            digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(12);
            digitalWrite(PIN_TRIG, LOW);
            long dur = pulseIn(PIN_ECHO, HIGH, 30000);
            const char* diag;
            float dist = 0.0f;
            if (dur == 0)       { diag = "TIMEOUT - sin eco (vacio o cable ECHO suelto)"; }
            else if (dur < 116) { diag = "DEMASIADO CORTO - objeto <2cm o TRIG/ECHO cruzados"; }
            else                { dist = dur / 58.0f; diag = "OK"; }
            Serial.printf("  %7d | %10d | %13ld | %8.2f | %s\n",
                i+1, echo_before, dur, dist, diag);
            delay(60);
        }

        Serial.println("\n[FASE 0b] Estado reed switch (5 segundos)");
        for (int t = 0; t < 50; t++) {
            int raw = digitalRead(PIN_REED_SWITCH);
            Serial.printf("  raw=%d  %s\n", raw,
                (raw == SystemManager::instance().reedTriggerLevel) ? "<-- ACTIVO" : "inactivo");
            delay(100);
        }

        Serial.println("\n[FASE 1] Barrido con sensor y reed");
        Serial.println("  Angulo  | Dist(cm) | Reed");
        Serial.println("  --------|----------|------");
        {
            float barrido[] = {
                0,5,10,15,20,25,30,35,40,45,
                40,35,30,25,20,15,10,5,0,-5,-10,-15,-20,-25,-30,-35,-40,-45,
                -40,-35,-30,-25,-20,-15,-10,-5,0
            };
            for (float a : barrido) {
                hw_test.moveToAngle(a);
                delay(50);
                float d = hw_test.getDistance();
                bool r = (digitalRead(PIN_REED_SWITCH) == SystemManager::instance().reedTriggerLevel);
                Serial.printf("  %+6.1f  | %8.2f | %s\n", a, d, r ? "ACTIVO <--" : "---");
                Serial.flush();
            }
        }

        Serial.println("\n[FASE 2] Test homing desde +30°");
        hw_test.moveToAngle(30.0f); delay(300);
        hw_test.goHome();
        delay(1000);

        Serial.println("\n[FASE 3] Test homing desde -30°");
        hw_test.moveToAngle(-30.0f); delay(300);
        hw_test.goHome();

        Serial.println("\nRepeticion en 5 segundos...");
        delay(5000);
    }
#endif

    SystemManager::instance().init();

    Serial.print("[ID] MAC: ");
    Serial.println(WiFi.macAddress());

    WiFi.setSleep(false);
    esp_wifi_set_ps(WIFI_PS_NONE);
    WiFi.setAutoReconnect(true);   // el stack WiFi reconecta solo sin que el código intervenga
    WiFi.persistent(false);        // no guardar credenciales en flash en cada begin()
    WiFi.setTxPower(WIFI_POWER_19_5dBm); // potencia máxima

    WiFi.onEvent(WiFiEvent);
    SystemManager::instance().changeState(WAITING_FOR_CONNECTION);
    tryConnectWiFi();
}

void loop() {
    SystemState current = SystemManager::instance().currentState;

    // LED: parpadeo = sin WiFi, encendido fijo = WiFi conectado
    static unsigned long lastBlink = 0;
    if (current == WAITING_FOR_CONNECTION) {
        if (millis() - lastBlink > 250) {
            digitalWrite(PIN_LED, !digitalRead(PIN_LED));
            lastBlink = millis();
        }
    } else {
        digitalWrite(PIN_LED, HIGH);
    }

    switch (current) {
        case CONFIGURACION:
            break;

        case WAITING_FOR_CONNECTION: {
            static unsigned long lastTry = 0;
            if (_wifi_reconnect_needed || millis() - lastTry > 15000) {
                _wifi_reconnect_needed = false;
                lastTry = millis();
                tryConnectWiFi();
            }
            break;
        }

        case SYNC_CONTROL: {
            if (hTaskComms == NULL) {
                Serial.println("[FSM] Arrancando TaskComms");
                xTaskCreatePinnedToCore(TaskComms, "TaskComms", STACK_SIZE_COMMS, NULL, 2, &hTaskComms, CORE_NET);
            }
            break;
        }

        case RADAR:
            if (hTaskRadar == NULL) {
                Serial.println("[FSM] Arrancando TaskRadar");
                xTaskCreatePinnedToCore(TaskRadar, "TaskRadar", STACK_SIZE_RADAR, NULL, 3, &hTaskRadar, CORE_PHYS);
            }
            break;
    }

    vTaskDelay(pdMS_TO_TICKS(100));
}