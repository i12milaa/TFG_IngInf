import socket
import struct
import time
import math

SERVER_IP = '127.0.0.1'
SERVER_PORT = 8080

MSG_HELLO_REQ = 0xA0
MSG_HELLO_ACK = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_ANGLE_REQ = 0xC0
MSG_SLOT_ASSIGN = 0xC1
MSG_DATA_REPORT = 0xD0

def main():
    # 1. PREGUNTAR ÁNGULO AL USUARIO
    print("--- RADAR VIRTUAL MANUAL ---")
    angle_input = input("Introduce el ángulo fijo para este radar (0-90): ")
    current_angle = float(angle_input)
    
    print(f"[VIRTUAL] Iniciando simulador fijo en {current_angle}°...")
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((SERVER_IP, SERVER_PORT))
    except:
        print("[ERROR] Enciende el servidor primero.")
        return

    # HANDSHAKE
    s.sendall(struct.pack('<BH', MSG_HELLO_REQ, 0))
    header = s.recv(3)
    if header[0] == MSG_HELLO_ACK:
        payload = s.recv(1)
        my_id = struct.unpack('<B', payload)[0]
        print(f"[VIRTUAL] Conectado. Soy ID: {my_id}")
    
    while True:
        try:
            # ESPERAR START
            data = s.recv(11) 
            if not data: break
            if data[0] != MSG_SUPERFRAME_START: continue

            print(f"\n[VIRTUAL] Trama recibida.")
            
            # PEDIR SIEMPRE EL MISMO ÁNGULO
            payload = struct.pack('<Bff', my_id, current_angle, current_angle)
            header = struct.pack('<BH', MSG_ANGLE_REQ, len(payload))
            s.sendall(header + payload)
            print(f"[VIRTUAL] Pido ir a {current_angle}°")

            # ESPERAR ASIGNACIÓN
            data = s.recv(13)
            if data and data[0] == MSG_SLOT_ASSIGN:
                assigned_slot, delay_ms = struct.unpack('<BI', data[4:9])
                print(f"[VIRTUAL] Me han dado el Slot: {assigned_slot} (Espera {delay_ms}ms)")
                
                # Simular espera
                time.sleep(delay_ms / 1000.0)
                
                # ENVIAR REPORTE
                sim_dist = 50.0 # Distancia inventada
                rep = struct.pack('<BffI', my_id, current_angle, sim_dist, 0)
                s.sendall(struct.pack('<BH', MSG_DATA_REPORT, len(rep)) + rep)
                print(f"[VIRTUAL] Reporte enviado.")

        except Exception as e:
            print(e)
            break

if __name__ == '__main__':
    main()