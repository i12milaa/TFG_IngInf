import socket
import struct
import time

# --- CONFIGURACIÓN DE TIEMPOS AJUSTADA ---
HOST = '0.0.0.0'
PORT = 8080

# AUMENTAMOS el ciclo total para dar margen a la WiFi
SUPERFRAME_PERIOD_S = 3.0 

# REDUCIMOS el retardo de disparo para que termine antes
# Antes 1000ms -> Ahora 800ms. El radar dispara antes y tiene más tiempo para enviar el dato.
SLOT_DELAY_MS       = 800 

MSG_HELLO_REQ        = 0xA0
MSG_HELLO_ACK        = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_ANGLE_REQ        = 0xC0
MSG_SLOT_ASSIGN      = 0xC1
MSG_DATA_REPORT      = 0xD0

def recv_exact(sock, n_bytes):
    """Lee EXACTAMENTE n_bytes o devuelve None si timeout"""
    data = b''
    start_t = time.time()
    while len(data) < n_bytes:
        try:
            # Timeout dinámico restante
            remaining = max(0.1, sock.gettimeout() - (time.time() - start_t))
            sock.settimeout(remaining)
            
            chunk = sock.recv(n_bytes - len(data))
            if not chunk: return None
            data += chunk
        except socket.timeout:
            return None
        except Exception:
            return None
    return data

def empty_socket_buffer(conn):
    """Limpia la basura antes de empezar"""
    conn.setblocking(0) # No bloqueante
    try:
        while conn.recv(4096): pass
    except:
        pass
    conn.setblocking(1) # Volver a bloqueante

def main():
    print(f"[ARBITER] Iniciando servidor en {PORT} (Ciclo: {SUPERFRAME_PERIOD_S}s)...")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("[ARBITER] Esperando conexión del Radar...")
        
        conn, addr = s.accept()
        conn.settimeout(1.0) 
        
        with conn:
            print(f"[ARBITER] Radar conectado: {addr}")
            radar_id = 1
            
            # --- HANDSHAKE ---
            try:
                header = recv_exact(conn, 3)
                if header and header[0] == MSG_HELLO_REQ:
                    ack_payload = struct.pack('<B', radar_id)
                    ack_header = struct.pack('<BH', MSG_HELLO_ACK, len(ack_payload))
                    conn.sendall(ack_header + ack_payload)
                    print("[ARBITER] Handshake completado.")
                    time.sleep(1.0) 
                else:
                    print(f"[ERROR] Handshake fallido.")
                    return
            except Exception as e:
                print(f"[ERROR] {e}")
                return

            seq_number = 0

            # --- BUCLE INFINITO ---
            while True:
                # 1. Limpieza agresiva de buffer al inicio de ciclo
                empty_socket_buffer(conn)
                
                cycle_start_time = time.time()
                print(f"\n--- SUPERTRAMA #{seq_number} (T=0) ---")

                # 2. ENVIAR START
                sf_payload = struct.pack('<II', seq_number, int(cycle_start_time*1000) & 0xFFFFFFFF)
                sf_header = struct.pack('<BH', MSG_SUPERFRAME_START, len(sf_payload))
                try:
                    conn.sendall(sf_header + sf_payload)
                except:
                    print("[ERROR] Conexión perdida enviando START")
                    break

                # 3. ESCUCHAR PETICIONES (Ventana AMPLIA de 1.5s)
                requested_angle = 0.0
                got_request = False
                
                # Damos mucho tiempo para que el ESP32 responda, incluso con lag
                conn.settimeout(1.5) 
                
                header = recv_exact(conn, 3)
                
                if header:
                    packet_type = header[0]
                    if packet_type == MSG_ANGLE_REQ:
                        payload_len = struct.unpack('<H', header[1:3])[0]
                        payload = recv_exact(conn, payload_len)
                        if payload:
                            rid, curr, req = struct.unpack('<Bff', payload[:9])
                            print(f"[RX] Radar {rid} quiere ir a {req:.1f}°")
                            requested_angle = req
                            got_request = True
                    else:
                        # Si llega otra cosa (ej. un dato viejo), lo ignoramos y seguimos
                        print(f"[WARN] Paquete fuera de lugar en fase REQ: {hex(packet_type)}")
                else:
                    print("[WARN] Nadie pidió turno (Timeout).")

                # 4. ASIGNAR SLOT
                if got_request:
                    assigned_slot = 0 
                    delay_ms = SLOT_DELAY_MS 
                    
                    sa_payload = struct.pack('<BBIf', radar_id, assigned_slot, delay_ms, requested_angle)
                    sa_header = struct.pack('<BH', MSG_SLOT_ASSIGN, len(sa_payload))
                    conn.sendall(sa_header + sa_payload)
                    print(f"[TX] Slot asignado: T+{delay_ms}ms")

                    # 5. ESPERAR REPORTE (Hasta el fin del ciclo)
                    # Calculamos cuánto tiempo queda de ciclo real
                    elapsed = time.time() - cycle_start_time
                    time_left = max(0.1, SUPERFRAME_PERIOD_S - elapsed - 0.1)
                    conn.settimeout(time_left)
                    
                    header = recv_exact(conn, 3)
                    if header:
                        packet_type = header[0]
                        if packet_type == MSG_DATA_REPORT:
                             payload_len = struct.unpack('<H', header[1:3])[0]
                             payload = recv_exact(conn, payload_len)
                             if payload:
                                 rid, ang, dist, ts = struct.unpack('<BffI', payload[:13])
                                 print(f"   >>> [DATO] Radar {rid} en {ang:.1f}° midió {dist:.2f}cm")
                        elif packet_type == MSG_ANGLE_REQ:
                             # AUTO-RECUPERACIÓN:
                             # Si recibimos una petición AQUÍ, es que el ESP32 se saltó el reporte
                             # y ya está pidiendo para el siguiente ciclo.
                             print(f"[WARN] El radar se saltó el reporte y pidió nuevo turno (0xC0).")
                        else:
                             print(f"[WARN] Esperaba DATA, llegó {hex(packet_type)}")
                    else:
                        print("   [FAIL] Timeout esperando reporte.")

                # Mantener el ritmo exacto
                elapsed = time.time() - cycle_start_time
                time_to_sleep = SUPERFRAME_PERIOD_S - elapsed
                if time_to_sleep > 0:
                    time.sleep(time_to_sleep)
                
                seq_number += 1

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ARBITER] Servidor detenido.")