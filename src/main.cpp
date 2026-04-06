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
            
            if (SystemManager::instance().currentState == STATE_WAIT_WIFI) {
                SystemManager::instance().changeState(STATE_SYNC);
            }
            break;
            
        case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
            Serial.println("[WIFI] Desconectado. Reconectando...");
            digitalWrite(PIN_LED, LOW); 
            
            // ATENCIÓN: No borramos las tareas con vTaskDelete. 
            // task_comms.cpp ya maneja su propia reconexión de forma limpia.
            
            SystemManager::instance().changeState(STATE_WAIT_WIFI);
            WiFi.reconnect();
            break;
    }
}

void setup() {
    // Desactiva protección de brownout
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    pinMode(PIN_LED, OUTPUT);
    
#if DEBUG_HARDWARE_TEST == 1
    Serial.println("--- MODO DEBUG HARDWARE ACTIVO ---");
    RadarHardware hw_test;
    hw_test.init();
    while(true) {
        Serial.println("Moviendo a 45 grados...");
        hw_test.moveToAngle(45.0);
        delay(1000);
        float dist = hw_test.getDistance();
        Serial.printf("Distancia: %.2f cm\n", dist);
        delay(1000);
        
        Serial.println("Moviendo a -45 grados...");
        hw_test.moveToAngle(-45.0);
        delay(1000);
        dist = hw_test.getDistance();
        Serial.printf("Distancia: %.2f cm\n", dist);
        delay(1000);
    }
#endif

    SystemManager::instance().init();
    
    WiFi.onEvent(WiFiEvent);
    WiFi.mode(WIFI_STA);
    
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    SystemManager::instance().changeState(STATE_WAIT_WIFI);
}

void loop() {
    SystemState current = SystemManager::instance().currentState;

    if (current == STATE_WAIT_WIFI) {
        static unsigned long lastBlink = 0;
        if (millis() - lastBlink > 500) {
            digitalWrite(PIN_LED, !digitalRead(PIN_LED));
            lastBlink = millis();
        }
    } else if (WiFi.status() == WL_CONNECTED) {
        digitalWrite(PIN_LED, HIGH); 
    }

    if (current == STATE_SYNC || current == STATE_RADAR) {
        if (hTaskComms == NULL) {
            Serial.println("[MAIN] Arrancando Tarea COMMS...");
            // Uso de macros de config.h y prioridad 2
            xTaskCreatePinnedToCore(TaskComms, "TaskComms", STACK_SIZE_COMMS, NULL, 2, &hTaskComms, CORE_NET);
        }
    }

    if (current == STATE_RADAR) {
        if (hTaskRadar == NULL) {
            Serial.println("[MAIN] Arrancando Tarea RADAR (Hardware)...");
            // Uso de macros de config.h y prioridad 3 (crítica para el motor)
            xTaskCreatePinnedToCore(TaskRadar, "TaskRadar", STACK_SIZE_RADAR, NULL, 3, &hTaskRadar, CORE_PHYS);
        }
    }

    delay(100);
}