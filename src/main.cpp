#include <Arduino.h>
#include <WiFi.h>
#include "config.h"
#include "system.h"
#include "task_comms.h"
#include "task_radar.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

TaskHandle_t hTaskComms = NULL;
TaskHandle_t hTaskRadar = NULL;

void WiFiEvent(WiFiEvent_t event) {
    switch(event) {
        case ARDUINO_EVENT_WIFI_STA_GOT_IP:
            Serial.print("[WIFI] Conectado! IP: ");
            Serial.println(WiFi.localIP());
            digitalWrite(PIN_LED, HIGH); 
            
            // FLECHA DE LA PIZARRA: <IP> -> Pasa a SYNC_CONTROL
            if (SystemManager::instance().currentState == WAITING_FOR_CONNECTION) {
                SystemManager::instance().changeState(SYNC_CONTROL);
            }
            break;
            
        case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
            Serial.println("[WIFI] Desconectado. Reconectando...");
            digitalWrite(PIN_LED, LOW); 
            
            // FLECHA DE LA PIZARRA: error IP -> Vuelve a WAITING_FOR_CONNECTION
            SystemManager::instance().changeState(WAITING_FOR_CONNECTION);
            WiFi.reconnect();
            break;
    }
}

void setup() {
    // Desactiva protección de brownout para evitar reinicios por picos del motor
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    pinMode(PIN_LED, OUTPUT);
    
#if DEBUG_HARDWARE_TEST == 1
    Serial.println("\n========================================");
    Serial.println("       MODO DEBUG HARDWARE");
    Serial.println("========================================");

    // Leer MAC (requiere modo STA aunque no haya conexión)
    WiFi.mode(WIFI_STA);
    String myMac = WiFi.macAddress();

    // Tabla que replica grid_config.json — actualiza si cambias posiciones
    struct NodeInfo { const char* mac; int id; float x; float y; float theta; };
    static const NodeInfo NODES[] = {
        {"F0:24:F9:44:0A:20", 1,  34.64f, 20.0f,  30.0f},
        {"88:13:BF:C8:40:30", 2,   0.0f,  40.0f,  90.0f},
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

        // ── Cabecera de identificación ────────────────────────────────────────
        Serial.println("\n========================================");
        if (myNode) {
            Serial.printf("  MAC   : %s\n", myMac.c_str());
            Serial.printf("  Nodo  : N%d\n", myNode->id);
            Serial.printf("  Pos   : x=%.2f  y=%.2f  theta=%.1f\n",
                myNode->x, myNode->y, myNode->theta);
        } else {
            Serial.printf("  MAC   : %s\n", myMac.c_str());
            Serial.println("  Nodo  : DESCONOCIDO (no esta en la tabla)");
        }
        Serial.println("========================================");

        // ── FASE 0a: diagnóstico raw del sensor ultrasónico ──────────────────
        Serial.println("\n[FASE 0a] Sensor ultrasonico - duracion bruta (10 disparos)");
        Serial.println("  Disparo | ECHO antes | Duracion (us) | Dist(cm) | Diagnostico");
        Serial.println("  --------|------------|---------------|----------|------------");
        for (int i = 0; i < 10; i++) {
            int echo_before = digitalRead(PIN_ECHO);

            digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(5);
            digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(12);
            digitalWrite(PIN_TRIG, LOW);
            long dur = pulseIn(PIN_ECHO, HIGH, 30000); // 30ms = ~5m

            const char* diag;
            float dist = 0.0f;
            if (dur == 0)       { diag = "TIMEOUT - sin eco (vacio o cable ECHO suelto)"; }
            else if (dur < 116) { diag = "DEMASIADO CORTO - objeto <2cm o TRIG/ECHO cruzados"; }
            else                { dist = dur / 58.0f; diag = "OK"; }

            Serial.printf("  %7d | %10d | %13ld | %8.2f | %s\n",
                i+1, echo_before, dur, dist, diag);
            delay(60);
        }
        Serial.println("  -> Si todos son TIMEOUT: comprueba VCC(5V), GND y pin ECHO(27).");
        Serial.println("  -> Si ECHO antes != 0: el pin 27 no esta a LOW en reposo (cortocircuito o pull-up).");

        // ── FASE 0b: reed switch en reposo (5s, mueve el iman para ver cambios) ──
        Serial.println("\n[FASE 0b] Estado reed switch (5 segundos)");
        for (int t = 0; t < 50; t++) {
            int raw = digitalRead(PIN_REED_SWITCH);
            Serial.printf("  raw=%d  %s\n", raw,
                (raw == REED_TRIGGER_LEVEL) ? "<-- ACTIVO (iman detectado)" : "inactivo");
            delay(100);
        }

        // ── FASE 1: barrido 0 -> +45 -> -45 -> 0 con sensor y reed ────────────
        // Pausa de 600ms en cada ángulo: motor quieto + consola sincronizada
        Serial.println("\n[FASE 1] Barrido con sensor de distancia y reed switch");
        Serial.println("  Angulo  | Dist(cm) | Reed");
        Serial.println("  --------|----------|------");

        {
            float barrido[] = {
                0,5,10,15,20,25,30,35,40,45,
                40,35,30,25,20,15,10,5,0,-5,-10,-15,-20,-25,-30,-35,-40,-45,
                -40,-35,-30,-25,-20,-15,-10,-5,0
            };
            for (float a : barrido) {
                Serial.printf("  -> %+.1f\n", a); Serial.flush();
                hw_test.moveToAngle(a);
                delay(50);
                float d = hw_test.getDistance();
                bool r = (digitalRead(PIN_REED_SWITCH) == REED_TRIGGER_LEVEL);
                Serial.printf("  %+6.1f  | %8.2f | %s\n", a, d, r ? "ACTIVO <--" : "---");
                Serial.flush();
            }
        }

        // ── FASE 2: homing desde +30° ──────────────────────────────────────────
        Serial.println("\n[FASE 2] Test homing desde +30°");
        Serial.printf("  HOMING_TRIGGER_OFFSET actual: %.2f grados\n", HOMING_TRIGGER_OFFSET);
        hw_test.moveToAngle(30.0f);
        delay(300);
        hw_test.goHome();
        Serial.println("  -> El sensor debe apuntar exactamente a 0°.");
        Serial.println("     Si no: pon en config.h el valor 'raw' que aparece en [HOME].");
        delay(1000);

        // ── FASE 3: homing desde -30° (verifica simetría) ─────────────────────
        Serial.println("\n[FASE 3] Test homing desde -30°");
        hw_test.moveToAngle(-30.0f);
        delay(300);
        hw_test.goHome();
        Serial.println("  -> Mismo criterio.");

        Serial.println("\n========================================");
        Serial.println("Repeticion en 5 segundos...");
        delay(5000);
    }
#endif

    SystemManager::instance().init();
    
    WiFi.onEvent(WiFiEvent);
    WiFi.mode(WIFI_STA);
    Serial.print("[ID] MAC de este nodo: ");
    Serial.println(WiFi.macAddress());
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    // Terminada la configuración de periféricos, pasamos a esperar red
    SystemManager::instance().changeState(WAITING_FOR_CONNECTION);
}

void loop() {
    SystemState current = SystemManager::instance().currentState;

    switch (current) {
        case CONFIGURACION:
            // Todo se inicializa en el setup()
            break;

        case WAITING_FOR_CONNECTION: {
            // Parpadea: Buscando Wi-Fi
            static unsigned long lastBlink = 0;
            if (millis() - lastBlink > 500) {
                digitalWrite(PIN_LED, !digitalRead(PIN_LED));
                lastBlink = millis();
            }
            break;
        }

        case SYNC_CONTROL:
            digitalWrite(PIN_LED, HIGH); // Fijo: Wi-Fi OK, buscando servidor TCP
            if (hTaskComms == NULL) {
                Serial.println("[FSM] Entrando en SYNC_CONTROL: Arrancando TaskComms");
                xTaskCreatePinnedToCore(TaskComms, "TaskComms", STACK_SIZE_COMMS, NULL, 2, &hTaskComms, CORE_NET);
            }
            break;

        case RADAR:
            digitalWrite(PIN_LED, HIGH); // Fijo: Conectado a Python y escaneando
            if (hTaskRadar == NULL) {
                Serial.println("[FSM] Entrando en RADAR: Arrancando TaskRadar");
                xTaskCreatePinnedToCore(TaskRadar, "TaskRadar", STACK_SIZE_RADAR, NULL, 3, &hTaskRadar, CORE_PHYS);
            }
            break;
    }

    // Relajar el Watchdog del Core 1
    vTaskDelay(pdMS_TO_TICKS(100)); 
}