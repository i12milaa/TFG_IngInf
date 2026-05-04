#ifndef COMMS_PROTOCOL_H
#define COMMS_PROTOCOL_H

#include <stdint.h>

#pragma pack(push, 1)

#define MSG_HELLO_REQ         0xA0
#define MSG_HELLO_ACK         0xA1
#define MSG_SUPERFRAME_START  0xB0
#define MSG_SLOT_ASSIGN       0xB1
#define MSG_REPORT_REQ        0xB2  
#define MSG_ANGLE_REQ         0xC0
#define MSG_DATA_REPORT       0xD0

struct PacketHeader {
    uint8_t type;
    uint16_t length;
};

struct Payload_HelloReq {
    uint8_t mac_address[6];
};

struct Payload_HelloAck {
    uint8_t assigned_id;
    float saved_angle; 
};

struct Payload_SuperFrame {
    uint32_t sequence_number;
    uint32_t server_time;
};

struct Payload_AngleReq {
    uint8_t radar_id;
    float current_angle;
    float requested_angle;
};

struct Payload_SlotAssign {
    uint8_t radar_id;
    uint8_t assigned_slot;
    uint32_t start_delay_ms;
    float confirmed_angle;
};

struct Payload_DataReport {
    uint8_t radar_id;
    float angle;
    float distance_cm;
    uint32_t measure_timestamp;
};

#pragma pack(pop)

#endif