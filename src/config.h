#ifndef CONFIG_H
#define CONFIG_H

#define DEBUG_HARDWARE_TEST 0

#define PIN_LED           2 
#define STACK_SIZE_COMMS  4096
#define STACK_SIZE_RADAR  4096

#define PIN_MOTOR_STEP    18 
#define PIN_MOTOR_DIR     19
#define PIN_MOTOR_ENABLE  -1  
#define PIN_REED_SWITCH   -1  

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