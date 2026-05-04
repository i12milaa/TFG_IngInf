#ifndef CONFIG_H
#define CONFIG_H

#define DEBUG_HARDWARE_TEST 0

#define PIN_LED           2 
#define STACK_SIZE_COMMS  4096
#define STACK_SIZE_RADAR  4096

#define PIN_MOTOR_STEP    18
#define PIN_MOTOR_DIR     19
#define PIN_MOTOR_ENABLE  -1
#define MOTOR_DIR_INVERT  1  // Pon 1 si el motor se mueve al revés
#define PIN_REED_SWITCH   26

// HIGH = interruptor NC (abierto cuando el imán pasa — lo que describes).
// LOW  = interruptor NO (cerrado cuando el imán pasa — el más común).
// Ajústalo si el DEBUG muestra el estado al revés.
#define REED_TRIGGER_LEVEL HIGH

// Ángulo (en grados) al que el reed se activa respecto al 0° lógico.
// Déjalo en 0.0 para el primer flash; el DEBUG te dirá el valor real.
#define HOMING_TRIGGER_OFFSET 0.0f

// Velocidad del motor durante el homing (µs por flanco).
// Más lento que en operación normal para no saltarse el trigger.
#define HOMING_STEP_US    700

#define PIN_TRIG          14
#define PIN_ECHO          27

#define STEPS_PER_REV     200 
#define MICROSTEPPING     16   
#define GEAR_RATIO        1.0 

#define CORE_NET          0   
#define CORE_PHYS         1   

#define RADAR_MIN_ANGLE    -45.0   
#define RADAR_MAX_ANGLE    45.0    
#define RADAR_STEP_ANGLE   5.0

#define WIFI_SSID         "ALEJANDROMILLAN2169"
#define WIFI_PASS         "TFG20252026"
#define SERVER_IP         "192.168.137.1" 
#define SERVER_PORT       8080

#endif