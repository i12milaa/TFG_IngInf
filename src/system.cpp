#include "system.h"
#include "config.h"

void SystemManager::init() {
    Serial.begin(115200);
    // Esperar un poco a que el serial estabilice
    delay(500);
    Serial.println("[SYSTEM] Iniciando gestor del sistema...");

    // 1. Crear Cola de Comandos (Red -> Hardware)
    // Caben 10 comandos. Si se llena, la red espera.
    queueCommands = xQueueCreate(10, sizeof(HwCommand));
    if (queueCommands == NULL) {
        Serial.println("[ERROR] No se pudo crear queueCommands");
        while(1); // Bloqueo de seguridad
    }

    // 2. Crear Cola de Resultados (Hardware -> Red)
    queueResults = xQueueCreate(10, sizeof(HwResult));
    if (queueResults == NULL) {
        Serial.println("[ERROR] No se pudo crear queueResults");
        while(1);
    }

    Serial.println("[SYSTEM] Colas FreeRTOS iniciadas.");
    
    // Estado inicial
    currentState = STATE_CONFIG;
}

void SystemManager::changeState(SystemState newState) {
    if (currentState != newState) {
        Serial.printf("[SYSTEM] Cambio de estado: %d -> %d\n", currentState, newState);
        currentState = newState;
    }
}