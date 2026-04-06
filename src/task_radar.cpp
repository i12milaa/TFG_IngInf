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
        // Bucle infinito a la espera de un comando en la cola compartida (API interna)
        if (xQueueReceive(SystemManager::instance().queueCommands, &cmd, portMAX_DELAY) == pdPASS) {
            
            if (cmd.type == HW_CMD_EXECUTE_SLOT) {
                // 1. Ejecutar movimiento físico lo antes posible
                hw.moveToAngle(cmd.param);

                // 2. Temporizar la lectura en el centro de su slot (según mandó el servidor)
                long time_to_wait = (long)cmd.execution_time_ms - (long)millis();
                if (time_to_wait > 0) {
                    vTaskDelay(pdMS_TO_TICKS(time_to_wait));
                }

                // 3. Tomar lectura ultrasónica
                float dist = hw.getDistance();

                // 4. Preparar resultado y vaciar lecturas antiguas por seguridad
                HwResult res;
                res.type = HW_RES_SLOT_DONE;
                res.value = dist;
                res.angle = cmd.param;

                HwResult flush;
                while(xQueueReceive(SystemManager::instance().queueResults, &flush, 0));
                
                // Enviar a la cola para la tarea de comunicaciones
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

    if (PIN_MOTOR_ENABLE != -1) {
        pinMode(PIN_MOTOR_ENABLE, OUTPUT);
        digitalWrite(PIN_MOTOR_ENABLE, LOW);
    }

    currentStepPos = 0;
    currentAngle = 0.0;
}

void RadarHardware::moveToAngle(float targetAngle) {
    float targetStepFloat = (targetAngle / 360.0) * STEPS_PER_REV * MICROSTEPPING * GEAR_RATIO;
    long target = (long)round(targetStepFloat);
    long steps = target - currentStepPos;

    if (steps == 0) return;

    bool dir = (steps > 0);
    steps = abs(steps);

    digitalWrite(PIN_MOTOR_DIR, dir ? HIGH : LOW);
    delay(2);

    for (long i = 0; i < steps; i++) {
        digitalWrite(PIN_MOTOR_STEP, HIGH);
        delayMicroseconds(1000);
        digitalWrite(PIN_MOTOR_STEP, LOW);
        delayMicroseconds(1000);
        
        // Ceder control brevemente cada 10 pasos para evitar reinicios por Watchdog
        if (i % 10 == 0) vTaskDelay(pdMS_TO_TICKS(1));
    }

    currentStepPos = target;
    currentAngle = targetAngle;
}

void RadarHardware::goHome() {
    currentAngle = 0.0;
    currentStepPos = 0;
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

        duration = pulseIn(PIN_ECHO, HIGH, 10000); // Timeout 10ms (suficiente para ~1.7m max)

        if (duration > 116) break;
        retries--;
        delay(2);
    }

    if (duration <= 116) return -1.0;
    return duration / 58.0;
}