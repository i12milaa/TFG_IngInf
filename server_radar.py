import socket
import struct
import time

# --- CONFIGURACIÓN ---
# Escuchar en todas las interfaces de red de tu PC
HOST = '0.0.0.0'  
PORT = 8080       

# --- DEFINICIÓN DEL PROTOCOLO (Coincide con comms_protocol.h) ---
MSG_HELLO_REQ  = 0xA0
MSG_HELLO_ACK  = 0xA1
MSG_GOTO_ANGLE = 0xB0
MSG_MOVE_DONE  = 0xB1
MSG_SCAN_REQ   = 0xC0
MSG_SCAN_RES   = 0xC1
MSG_HOME_REQ   = 0xD0

def main():
    print(f"[SERVER] Iniciando servidor en el puerto {PORT}...")
    
    # Crear socket TCP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[SERVER] Esperando conexión del ESP32...")
        
        # Bloquea hasta que el ESP32 se conecta
        conn, addr = s.accept()
        with conn:
            print(f"[SERVER] Conectado por: {addr}")

            # --- NUEVA LÍNEA: AUMENTAR PACIENCIA ---
            conn.settimeout(60.0) # Esperar hasta 60 segundos antes de dar error
            
            # --- FASE 1: HANDSHAKE (Esperar HELLO_REQ) ---
            header_data = conn.recv(3) # Leer cabecera (Type + Length)
            if not header_data: return
            
            msg_type, msg_len = struct.unpack('<BH', header_data)
            
            if msg_type == MSG_HELLO_REQ:
                print("[RX] Recibido HELLO_REQ. Enviando ID 1...")
                
                # Construir respuesta HELLO_ACK (ID = 1)
                # Header: Type(1B) + Len(2B) | Payload: ID(1B)
                payload = struct.pack('<B', 1) 
                header = struct.pack('<BH', MSG_HELLO_ACK, len(payload))
                conn.sendall(header + payload)
            else:
                print(f"[ERROR] Esperaba HELLO_REQ, llegó {hex(msg_type)}")
                return

            # --- FASE 2: BUCLE DE CONTROL ---
            try:
                while True:
                    print("\n--- MENÚ DE CONTROL RADAR ---")
                    print("1. Ir a Home")
                    print("2. Mover a ángulo")
                    print("3. Escanear distancia")
                    print("4. Salir")
                    opcion = input("Elige opción: ")

                    if opcion == '1': # HOME
                        header = struct.pack('<BH', MSG_HOME_REQ, 0)
                        conn.sendall(header)
                        print("[TX] Orden HOME enviada.")
                        esperar_respuesta(conn)

                    elif opcion == '2': # MOVER
                        angulo = float(input("Introduce ángulo (ej. 90.5): "))
                        payload = struct.pack('<f', angulo)
                        header = struct.pack('<BH', MSG_GOTO_ANGLE, len(payload))
                        conn.sendall(header + payload)
                        print(f"[TX] Mover a {angulo} enviado.")
                        esperar_respuesta(conn)

                    elif opcion == '3': # SCAN
                        header = struct.pack('<BH', MSG_SCAN_REQ, 0)
                        conn.sendall(header)
                        print("[TX] Orden SCAN enviada.")
                        esperar_respuesta(conn)

                    elif opcion == '4':
                        break
                        
            except ConnectionResetError:
                print("[SERVER] El ESP32 cerró la conexión.")
            except KeyboardInterrupt:
                print("[SERVER] Cerrando...")

def esperar_respuesta(conn):
    """Función bloqueante que espera la confirmación del ESP32"""
    print("   ...Esperando respuesta del ESP32...")
    
    # 1. Leer Cabecera
    header_data = conn.recv(3)
    if not header_data: return
    msg_type, msg_len = struct.unpack('<BH', header_data)
    
    # 2. Leer Payload (si hay)
    payload_data = b''
    if msg_len > 0:
        payload_data = conn.recv(msg_len)
        
    # 3. Procesar
    if msg_type == MSG_MOVE_DONE:
        angulo_actual = struct.unpack('<f', payload_data)[0]
        print(f"   [RX] MOVE_DONE. El radar está en: {angulo_actual:.2f}°")
        
    elif msg_type == MSG_SCAN_RES:
        distancia = struct.unpack('<f', payload_data)[0]
        print(f"   [RX] SCAN_RES. Distancia medida: {distancia:.2f} cm")
        
    else:
        print(f"   [RX] Mensaje desconocido: {hex(msg_type)}")

if __name__ == '__main__':
    main()