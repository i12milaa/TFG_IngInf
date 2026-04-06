import socket
import struct
import time

HOST = '0.0.0.0'
PORT = 8080
SUPERFRAME_PERIOD_S = 3.5 

THRESHOLD_CONFLICT_RIGHT = 30.0
THRESHOLD_CONFLICT_LEFT  = -30.0

MSG_HELLO_REQ = 0xA0
MSG_HELLO_ACK = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_ANGLE_REQ = 0xC0
MSG_SLOT_ASSIGN = 0xC1
MSG_DATA_REPORT = 0xD0

def recv_exact(sock, n):
    data = b''
    start_t = time.time()
    while len(data) < n:
        # Timeout de seguridad interno para no quedarse colgado eternamente
        if time.time() - start_t > 3.0: return None
        try:
            chunk = sock.recv(n - len(data))
            if not chunk: return None
            data += chunk
        except socket.timeout: return None
        except OSError: return None
    return data

def check_interference(angle_left, angle_right):
    left_invading = (angle_left > THRESHOLD_CONFLICT_RIGHT)
    right_invading = (angle_right < THRESHOLD_CONFLICT_LEFT)
    return left_invading and right_invading

def main():
    print(f"[CIRCLE SERVER] Geometría robusta activada.")
    print(f"Conflictos: Izq > {THRESHOLD_CONFLICT_RIGHT}º Y Der < {THRESHOLD_CONFLICT_LEFT}º")
    
    clients = {} 
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Permite reiniciar el servidor rápido sin error "Address already in use"
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        s.bind((HOST, PORT))
        s.listen(6)
        s.settimeout(0.1) # Non-blocking accept para poder gestionar el bucle

        print("Esperando conexiones...")
        next_id = 1
        
        # Bucle infinito del servidor
        seq = 0
        while True:
            # --- GESTIÓN DE CONEXIONES NUEVAS (SIN BLOQUEAR EL CICLO) ---
            try:
                conn, addr = s.accept()
                conn.settimeout(2.0)
                try:
                    h = recv_exact(conn, 3)
                    if h and h[0] == MSG_HELLO_REQ:
                        ack = struct.pack('<BHB', MSG_HELLO_ACK, 1, next_id) 
                        conn.sendall(ack)
                        clients[next_id] = {'sock': conn, 'errors': 0}
                        print(f" -> [NUEVO] Radar {next_id} conectado desde {addr}")
                        next_id += 1
                except Exception as e:
                    print(f"[ERR] Fallo en handshake: {e}")
                    conn.close()
            except socket.timeout:
                pass # No hay nadie nuevo, seguimos
            except Exception as e:
                print(f"[ERR] Server accept: {e}")

            # Solo arrancamos tramas si hay gente conectada
            if len(clients) == 0:
                time.sleep(1)
                continue

            # --- LIMPIEZA DE BUFFERS ---
            active_ids = list(clients.keys())
            for rid in active_ids:
                try:
                    clients[rid]['sock'].setblocking(0)
                    while clients[rid]['sock'].recv(4096): pass
                    clients[rid]['sock'].setblocking(1)
                except: pass # Si falla aquí, fallará luego y lo cazaremos

            t0 = time.time()
            print(f"--- TRAMA #{seq} (Clientes: {len(clients)}) ---")
            
            # 1. BROADCAST START
            payload = struct.pack('<II', seq, int(t0*1000) & 0xFFFFFFFF)
            header = struct.pack('<BH', MSG_SUPERFRAME_START, len(payload))
            
            # Lista de "muertos" a eliminar
            to_remove = []

            for rid in active_ids:
                try: 
                    clients[rid]['sock'].sendall(header + payload)
                except Exception as e:
                    print(f"[DISCONNECT] Radar {rid} perdió conexión (Send Start).")
                    clients[rid]['sock'].close()
                    to_remove.append(rid)
            
            # Eliminar muertos
            for rid in to_remove: del clients[rid]
            active_ids = list(clients.keys()) # Actualizar lista

            # 2. RECIBIR PETICIONES
            requests_received = {} 
            for rid in active_ids:
                try:
                    sock = clients[rid]['sock']
                    sock.settimeout(2.5) # Muy pacientes
                    h = recv_exact(sock, 3)
                    if h and h[0] == MSG_ANGLE_REQ:
                        p_len = struct.unpack('<H', h[1:3])[0]
                        p = recv_exact(sock, p_len)
                        if p:
                            _, _, req_angle = struct.unpack('<Bff', p[:9])
                            requests_received[rid] = req_angle
                            print(f"[RX] Radar {rid} pide {req_angle:.1f}°")
                            clients[rid]['errors'] = 0 # Reset contador errores
                        else:
                            raise Exception("Payload incompleto")
                    else:
                        print(f"[WARN] Radar {rid} silencio o basura.")
                        clients[rid]['errors'] += 1
                except Exception as e:
                    print(f"[WARN] Radar {rid} timeout/error: {e}")
                    clients[rid]['errors'] += 1
            
            # Auto-kick: Si un radar falla 5 veces seguidas, lo echamos
            for rid in active_ids:
                if clients[rid]['errors'] > 5:
                    print(f"[KICK] Radar {rid} eliminado por inactividad.")
                    clients[rid]['sock'].close()
                    del clients[rid]

            # 3. LÓGICA DE SOLAPAMIENTO
            slot_assignments = {}
            current_ids = sorted(requests_received.keys())
            
            for current_id in current_ids:
                current_angle = requests_received[current_id]
                my_slot = 0 
                
                prev_id = current_id - 1
                if prev_id in requests_received:
                    prev_angle = requests_received[prev_id]
                    if check_interference(prev_angle, current_angle):
                        print(f"   [ALERTA] CHOQUE: R{prev_id}({prev_angle}°) vs R{current_id}({current_angle}°)")
                        neighbor_slot = slot_assignments.get(prev_id, 0)
                        my_slot = 1 if neighbor_slot == 0 else 0
                    else:
                        print(f"   [OK] Paralelo: R{prev_id} y R{current_id}")

                slot_assignments[current_id] = my_slot

            # 4. ENVIAR ÓRDENES
            for rid, slot in slot_assignments.items():
                if rid not in clients: continue # Por si acaso fue kickeado
                
                delay = 800 + (slot * 1000)
                angle = requests_received.get(rid, 0)
                p_load = struct.pack('<BBIf', rid, slot, delay, angle)
                p_head = struct.pack('<BH', MSG_SLOT_ASSIGN, len(p_load))
                try: 
                    clients[rid]['sock'].sendall(p_head + p_load)
                    print(f"[TX] Radar {rid} -> Slot {slot}")
                except: 
                    print(f"[ERR] Fallo enviando orden a Radar {rid}")

            # Esperar fin de ciclo
            elapsed = time.time() - t0
            time.sleep(max(0.1, SUPERFRAME_PERIOD_S - elapsed))
            seq += 1

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nServidor detenido.")