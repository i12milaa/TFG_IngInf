#include "system.h"
#include "config.h"

void SystemManager::init() {
    Serial.begin(115200);
    delay(500);
    Serial.println("[SYSTEM] Iniciando gestor del sistema...");

    queueCommands = xQueueCreate(10, sizeof(HwCommand));
    if (queueCommands == NULL) {
        Serial.println("[ERROR] No se pudo crear queueCommands");
        while(1);
    }

    queueResults = xQueueCreate(10, sizeof(HwResult));
    if (queueResults == NULL) {
        Serial.println("[ERROR] No se pudo crear queueResults");
        while(1);
    }

    Serial.println("[SYSTEM] Colas FreeRTOS iniciadas.");
    
    // Asignamos el estado inicial de la pizarra
    currentState = CONFIGURACION;
}

void SystemManager::changeState(SystemState newState) {
    if (currentState != newState) {
        Serial.printf("[SYSTEM] Cambio de estado: %d -> %d\n", currentState, newState);
        currentState = newState;
    }
}