import socket
import struct
import time

HOST = '0.0.0.0'
PORT = 8080
SUPERFRAME_PERIOD_S = 3.5 # Ciclo largo para acomodar a dos radares

# PROTOCOLO
MSG_HELLO_REQ = 0xA0
MSG_HELLO_ACK = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_ANGLE_REQ = 0xC0
MSG_SLOT_ASSIGN = 0xC1
MSG_DATA_REPORT = 0xD0

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
            if not chunk: return None
            data += chunk
        except: return None
    return data

def main():
    print(f"[SERVER] Esperando 2 Radares en puerto {PORT}...")
    
    clients = [] # Lista de sockets
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((HOST, PORT))
        s.listen(2)
        
        # --- FASE DE CONEXIÓN (Esperamos 2 jugadores) ---
        next_id = 1
        while len(clients) < 2:
            conn, addr = s.accept()
            print(f"[SERVER] Conexión entrante de {addr}")
            
            # Handshake rápido
            conn.settimeout(2.0)
            header = recv_exact(conn, 3)
            if header and header[0] == MSG_HELLO_REQ:
                ack = struct.pack('<BHB', MSG_HELLO_ACK, 1, next_id) # Header + ID
                conn.sendall(ack)
                clients.append({'sock': conn, 'id': next_id, 'addr': addr})
                print(f"[SERVER] Radar ID {next_id} registrado.")
                next_id += 1
            else:
                print("[ERROR] Handshake inválido. Cerrando.")
                conn.close()
        
        print("\n=== ¡TODOS LISTOS! INICIANDO SISTEMA TDMA ===\n")
        seq = 0
        
        while True:
            t0 = time.time()
            print(f"--- TRAMA #{seq} ---")
            
            # 1. BROADCAST START (A todos)
            payload = struct.pack('<II', seq, int(t0*1000) & 0xFFFFFFFF)
            header = struct.pack('<BH', MSG_SUPERFRAME_START, len(payload))
            
            for c in clients:
                try: c['sock'].sendall(header + payload)
                except: print(f"[WARN] Error enviando START a ID {c['id']}")

            # 2. RECOLECTAR PETICIONES
            requests = []
            for c in clients:
                try:
                    c['sock'].settimeout(1.0)
                    h = recv_exact(c['sock'], 3)
                    if h and h[0] == MSG_ANGLE_REQ:
                        p_len = struct.unpack('<H', h[1:3])[0]
                        p = recv_exact(c['sock'], p_len)
                        rid, curr, req = struct.unpack('<Bff', p[:9])
                        requests.append({'client': c, 'angle': req})
                        print(f"[RX] ID {rid} pide {req}°")
                except:
                    print(f"[WARN] ID {c['id']} no pidió turno.")

            # 3. ASIGNAR SLOTS (Lógica TDMA)
            # Slot 0 = 800ms, Slot 1 = 1800ms
            current_slot = 0
            base_delay = 800
            slot_duration = 1000 
            
            for req in requests:
                delay = base_delay + (current_slot * slot_duration)
                
                # Enviar Assignment
                p_load = struct.pack('<BBIf', req['client']['id'], current_slot, delay, req['angle'])
                p_head = struct.pack('<BH', MSG_SLOT_ASSIGN, len(p_load))
                req['client']['sock'].sendall(p_head + p_load)
                
                print(f"[TX] ID {req['client']['id']} -> Slot {current_slot} (T+{delay}ms)")
                current_slot += 1

            # 4. ESPERAR REPORTES
            # Esperamos hasta el fin del ciclo para recibir todo
            elapsed = time.time() - t0
            wait_time = max(0.1, SUPERFRAME_PERIOD_S - elapsed)
            time.sleep(wait_time)
            
            # Leemos los buffers de todos
            for c in clients:
                c['sock'].setblocking(0) # Modo no bloqueante para ver si hay algo
                try:
                    h = recv_exact(c['sock'], 3)
                    if h and h[0] == MSG_DATA_REPORT:
                         p_len = struct.unpack('<H', h[1:3])[0]
                         p = recv_exact(c['sock'], p_len)
                         rid, ang, dist, ts = struct.unpack('<BffI', p[:13])
                         print(f"   >>> [DATO] ID {rid} :: {ang}° :: {dist:.1f}cm")
                except: pass
                c['sock'].setblocking(1)

            seq += 1

if __name__ == '__main__':
    main()