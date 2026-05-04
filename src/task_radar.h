#ifndef TASK_RADAR_H
#define TASK_RADAR_H

#include <Arduino.h>

enum HwCmdType {
    HW_CMD_HOME,         // homing con reed switch → motor queda en 0°
    HW_CMD_SYNC_POS,     // sincroniza variables de tracking sin mover el motor
    HW_CMD_MOVE,         // mueve físicamente el motor a param grados
    HW_CMD_SCAN,
    HW_CMD_EXECUTE_SLOT
};

struct HwCommand {
    HwCmdType type;
    float param;
    uint32_t execution_time_ms; 
};

enum HwResType {
    HW_RES_MOVED,
    HW_RES_MEASURED,
    HW_RES_SLOT_DONE,
    HW_RES_HOME_DONE
};

struct HwResult {
    HwResType type;
    float value;
    float angle;
};

void TaskRadar(void *pvParameters);

class RadarHardware {
public:
    void init();
    void moveToAngle(float targetAngle);
    void goHome();
    void syncPosition(float angle);
    float getDistance();
    void step(bool direction);

private:
    float currentAngle = 0.0;
};

#endif