#ifndef CONFIG_H
#define CONFIG_H

#define DEBUG_HARDWARE_TEST 0  // 1 para activar, 0 para modo normal

#define PIN_LED           2 
#define STACK_SIZE_COMMS  4096
#define STACK_SIZE_RADAR  4096

#define PIN_MOTOR_STEP    18
#define PIN_MOTOR_DIR     19
#define PIN_MOTOR_ENABLE  -1
#define MOTOR_DIR_INVERT  0  // Ya no se usa — ver perfiles en main.cpp
#define PIN_REED_SWITCH   26

// REED_TRIGGER_LEVEL ya no se usa aquí — ver perfiles en main.cpp

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

// Lista de redes WiFi — el nodo se conecta a la primera que encuentre disponible
#define WIFI_SSID_1       "iPhone de Alejandro"
#define WIFI_PASS_1       "TFG20252026"
#define WIFI_SSID_2       "ALEJANDROMILLAN2169"   // Red de casa: pon aquí el SSID
#define WIFI_PASS_2       "TFG20252026"   // Red de casa: pon aquí la contraseña

#define SERVER_HOSTNAME   "radar-server"
#define SERVER_PORT       8080

#endif