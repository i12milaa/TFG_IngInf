#include "task_radar.h"
#include "config.h"
#include "system.h"
#include <math.h>

RadarHardware hw;
static long currentStepPos = 0;

void TaskRadar(void *pvParameters) {
    hw.init();
    HwCommand cmd;

    for (;;) {
        if (xQueueReceive(SystemManager::instance().queueCommands, &cmd, portMAX_DELAY) == pdPASS) {

            if (cmd.type == HW_CMD_HOME) {
                hw.goHome();

                HwResult flush;
                while (xQueueReceive(SystemManager::instance().queueResults, &flush, 0));

                HwResult res;
                res.type = HW_RES_HOME_DONE;
                res.angle = 0.0f;
                res.value = 0.0f;
                xQueueSend(SystemManager::instance().queueResults, &res, portMAX_DELAY);
            }

            else if (cmd.type == HW_CMD_SYNC_POS) {
                hw.syncPosition(cmd.param);

                HwResult flush;
                while (xQueueReceive(SystemManager::instance().queueResults, &flush, 0));

                HwResult res;
                res.type = HW_RES_MOVED;
                res.angle = cmd.param;
                res.value = 0.0f;
                xQueueSend(SystemManager::instance().queueResults, &res, portMAX_DELAY);
            }

            else if (cmd.type == HW_CMD_MOVE) {
                hw.moveToAngle(cmd.param);

                HwResult res;
                res.type = HW_RES_MOVED;
                res.angle = cmd.param;
                res.value = 0.0f;
                xQueueSend(SystemManager::instance().queueResults, &res, portMAX_DELAY);
            }

            else if (cmd.type == HW_CMD_EXECUTE_SLOT) {
                hw.moveToAngle(cmd.param);

                long time_to_wait = (long)cmd.execution_time_ms - (long)millis();
                if (time_to_wait > 0) {
                    vTaskDelay(pdMS_TO_TICKS(time_to_wait));
                }

                float dist = hw.getDistance();

                HwResult res;
                res.type = HW_RES_SLOT_DONE;
                res.value = dist;
                res.angle = cmd.param;

                HwResult flush;
                while (xQueueReceive(SystemManager::instance().queueResults, &flush, 0));

                xQueueSend(SystemManager::instance().queueResults, &res, portMAX_DELAY);
            }
        }
    }
}

void RadarHardware::init() {
    pinMode(PIN_MOTOR_STEP, OUTPUT);
    pinMode(PIN_MOTOR_DIR, OUTPUT);
    pinMode(PIN_TRIG, OUTPUT);
    pinMode(PIN_ECHO, INPUT);
    pinMode(PIN_REED_SWITCH, INPUT_PULLUP);

    if (PIN_MOTOR_ENABLE != -1) {
        pinMode(PIN_MOTOR_ENABLE, OUTPUT);
        digitalWrite(PIN_MOTOR_ENABLE, LOW);
    }

    currentStepPos = 0;
    currentAngle = 0.0f;
}

void RadarHardware::moveToAngle(float targetAngle) {
    float targetStepFloat = (targetAngle / 360.0) * STEPS_PER_REV * MICROSTEPPING * GEAR_RATIO;
    long target = (long)round(targetStepFloat);
    long steps = target - currentStepPos;

#if DEBUG_HARDWARE_TEST == 1
    Serial.printf("  [MOV] %.1f->%.1f  pasos=%ld  stepPos %ld->%ld\n",
        currentAngle, targetAngle, steps, currentStepPos, target);
    Serial.flush();
#endif

    if (steps == 0) return;

    bool dir = (steps > 0);
    steps = abs(steps);

    bool phys_dir = dir ^ (bool)MOTOR_DIR_INVERT;
    digitalWrite(PIN_MOTOR_DIR, phys_dir ? HIGH : LOW);
    delay(2);

    for (long i = 0; i < steps; i++) {
        digitalWrite(PIN_MOTOR_STEP, HIGH);
        delayMicroseconds(400); // VOLVEMOS A 400us PARA EVITAR PÉRDIDA DE PASOS
        digitalWrite(PIN_MOTOR_STEP, LOW);
        delayMicroseconds(400); // VOLVEMOS A 400us PARA EVITAR PÉRDIDA DE PASOS
        
        if (i % 20 == 0) vTaskDelay(pdMS_TO_TICKS(1));
    }

    currentStepPos = target;
    currentAngle = targetAngle;
}

void RadarHardware::goHome() {
    Serial.printf("[HOME] Volviendo a 0° desde %.2f° via tracking de pasos.\n", currentAngle);

    moveToAngle(0.0f);

    // Verificacion con reed switch: si esta instalado y calibrado debe estar activo en 0°.
    // No bloquea el homing — es solo un indicador de salud del sistema.
    delay(50);
    bool reed_ok = (digitalRead(PIN_REED_SWITCH) == REED_TRIGGER_LEVEL);
    if (reed_ok) {
        Serial.println("[HOME] Reed activo en 0° — posicion verificada por reed.");
    } else {
        Serial.println("[HOME] Reed no activo en 0° — sin verificacion (reed no instalado o desplazamiento fisico acumulado).");
    }

    Serial.println("[HOME] Homing completado.");
}

void RadarHardware::syncPosition(float angle) {
    currentAngle = angle;
    float targetStepFloat = (angle / 360.0) * STEPS_PER_REV * MICROSTEPPING * GEAR_RATIO;
    currentStepPos = (long)round(targetStepFloat);
}

float RadarHardware::getDistance() {
    int retries = 2;
    long duration = 0;

    while(retries > 0) {
        digitalWrite(PIN_TRIG, LOW);
        delayMicroseconds(5);
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(12);
        digitalWrite(PIN_TRIG, LOW);

        duration = pulseIn(PIN_ECHO, HIGH, 15000); 

        if (duration > 116) break;
        retries--;
        vTaskDelay(pdMS_TO_TICKS(2));
    }

    // NUEVO: Si el timeout salta (duration 0), significa que no hay obstáculos a < 2.5m
    if (duration == 0) return 0.0; 
    
    // Si la lectura es absurdamente pequeña (< 2cm), sí es un error del sensor
    if (duration <= 116) return -1.0; 
    
    return duration / 58.0;
}