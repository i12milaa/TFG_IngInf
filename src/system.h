#ifndef SYSTEM_H
#define SYSTEM_H

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include "task_radar.h" 

// FSM calcada de la pizarra del profesor
enum SystemState {
    CONFIGURACION,
    WAITING_FOR_CONNECTION,
    SYNC_CONTROL,
    RADAR
};

class SystemManager {
public:
    static SystemManager& instance() {
        static SystemManager instance;
        return instance;
    }

    void init();
    void changeState(SystemState newState);

    SystemState currentState;
    QueueHandle_t queueCommands;
    QueueHandle_t queueResults;
    uint8_t radarId;

    uint32_t t0_last_superframe;
    float current_angle_logic;
    bool sweep_direction_up;

    bool motorActive;  // true desde HELLO_ACK hasta homing completado
    bool justHomed;    // true justo después de homing; indica que el motor está en 0°

    bool motorDirInvert;   // perfil del nodo: true si las bobinas del motor están invertidas
    int  reedTriggerLevel; // perfil del nodo: HIGH (NC) o LOW (NO)

private:
    SystemManager() : currentState(CONFIGURACION), radarId(0),
                      t0_last_superframe(0), current_angle_logic(0.0), sweep_direction_up(true),
                      motorActive(false), justHomed(false),
                      motorDirInvert(false), reedTriggerLevel(HIGH) {}
};

#endif