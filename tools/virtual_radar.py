import socket
import struct
import time
import math

# --- CONFIGURACIÓN SIMULADA ---
SERVER_IP = '127.0.0.1' # Localhost (se conecta al mismo PC)
SERVER_PORT = 8080

# Identificadores de protocolo (Igual que en C++)
MSG_HELLO_REQ        = 0xA0
MSG_HELLO_ACK        = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_ANGLE_REQ        = 0xC0
MSG_SLOT_ASSIGN      = 0xC1
MSG_DATA_REPORT      = 0xD0

def main():
    print(f"[VIRTUAL] Iniciando Radar Simulado...")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_IP, SERVER_PORT))
    except ConnectionRefusedError:
        print("[ERROR] No encuentro el servidor. ¿Está encendido?")
        return

    # --- HANDSHAKE ---
    # Enviar HELLO
    print("[VIRTUAL] Enviando HELLO...")
    s.sendall(struct.pack('<BH', MSG_HELLO_REQ, 0))
    
    # Recibir ACK
    header = s.recv(3)
    if header[0] == MSG_HELLO_ACK:
        payload = s.recv(1) # ID es 1 byte
        my_id = struct.unpack('<B', payload)[0]
        print(f"[VIRTUAL] ¡Conectado! Soy el Radar ID: {my_id}")
    else:
        print("[ERROR] Handshake fallido")
        return

    # Estado interno simulado
    current_angle = 0.0
    direction_up = True
    
    # --- BUCLE PRINCIPAL ---
    while True:
        try:
            # 1. Esperar START (Header 3 bytes + Payload 8 bytes)
            data = s.recv(11) 
            if not data: break
            if data[0] != MSG_SUPERFRAME_START: continue

            print(f"\n[VIRTUAL] Nueva trama recibida.")
            
            # 2. Calcular movimiento simulado (0 -> 90 -> 0)
            req_angle = current_angle + 10.0 if direction_up else current_angle - 10.0
            if req_angle >= 90: direction_up = False
            if req_angle <= 0: direction_up = True
            
            # 3. Enviar PETICIÓN
            # Payload: ID(1) + Curr(4) + Req(4)
            payload = struct.pack('<Bff', my_id, current_angle, req_angle)
            header = struct.pack('<BH', MSG_ANGLE_REQ, len(payload))
            s.sendall(header + payload)
            print(f"[VIRTUAL] Pido ir a {req_angle}°")

            # 4. Esperar ASIGNACIÓN
            # Header(3) + Payload(1+1+4+4 = 10)
            data = s.recv(13)
            if data and data[0] == MSG_SLOT_ASSIGN:
                # Payload offset 3
                assigned_slot, delay_ms = struct.unpack('<BI', data[4:9])
                print(f"[VIRTUAL] Slot asignado: {assigned_slot}. Esperando {delay_ms}ms...")
                
                # SIMULAR ESPERA MECÁNICA
                time.sleep(delay_ms / 1000.0)
                
                # 5. Enviar REPORTE
                # Simulamos una distancia basada en el ángulo (seno) para que haga un dibujo bonito
                simulated_dist = 50 + (30 * math.sin(math.radians(req_angle)))
                
                rep_payload = struct.pack('<BffI', my_id, req_angle, simulated_dist, int(time.time()*1000) & 0xFFFFFFFF)
                rep_header = struct.pack('<BH', MSG_DATA_REPORT, len(rep_payload))
                s.sendall(rep_header + rep_payload)
                print(f"[VIRTUAL] Reporte enviado (Dist: {simulated_dist:.1f}cm)")
                
                current_angle = req_angle

        except Exception as e:
            print(f"[ERROR] {e}")
            break

if __name__ == '__main__':
    main()