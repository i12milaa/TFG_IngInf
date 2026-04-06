import socket
import struct
import threading
import time
import math
import json
import os

HOST = '0.0.0.0'
PORT = 8080
CONFIG_FILE = 'grid_config.json'

MSG_HELLO_REQ        = 0xA0
MSG_HELLO_ACK        = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_SLOT_ASSIGN      = 0xB1
MSG_REPORT_REQ       = 0xB2
MSG_ANGLE_REQ        = 0xC0
MSG_DATA_REPORT      = 0xD0

class ArbitroServer:
    def __init__(self):
        self.clients = {}         
        self.client_sockets = {}  
        self.requests = {}        
        self.reports_received = set() 
        self.lock = threading.Lock()
        self.seq = 0
        self.running = True
        self.grid = self.load_grid()

    def load_grid(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_grid(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.grid, f, indent=4)

    def calculate_global_coords(self, radar_id, local_angle, distance):
        cfg = next((r for r in self.grid.values() if r["id"] == radar_id), None)
        if not cfg or distance <= 0: return None
        
        global_angle = math.radians(cfg["theta"] + local_angle)
        obj_x = cfg["x"] + distance * math.cos(global_angle)
        obj_y = cfg["y"] + distance * math.sin(global_angle)
        return (obj_x, obj_y)

    def handle_client(self, conn, addr):
        radar_id = None
        conn.settimeout(15.0) 
        try:
            while self.running:
                header_data = conn.recv(3)
                if not header_data: break
                
                msg_type, msg_length = struct.unpack('<BH', header_data)
                
                payload = b''
                if msg_length > 0:
                    payload = conn.recv(msg_length)
                    while len(payload) < msg_length:
                        payload += conn.recv(msg_length - len(payload))

                if msg_type == MSG_HELLO_REQ:
                    mac_bytes = struct.unpack('<6B', payload[:6])
                    mac_str = ":".join([f"{b:02X}" for b in mac_bytes])
                    
                    with self.lock:
                        if mac_str in self.grid:
                            radar_id = self.grid[mac_str]["id"]
                        else:
                            radar_id = len(self.grid) + 1
                            self.grid[mac_str] = {"id": radar_id, "x": 0.0, "y": 0.0, "theta": 90.0}
                            self.save_grid()
                            
                        self.clients[conn] = radar_id
                        self.client_sockets[radar_id] = conn
                    
                    print(f"[SYS] Conectado MAC {mac_str} -> ID {radar_id}")
                    conn.sendall(struct.pack('<BHB', MSG_HELLO_ACK, 1, radar_id))

                elif msg_type == MSG_ANGLE_REQ:
                    r_id, curr_angle, req_angle = struct.unpack('<Bff', payload)
                    with self.lock: self.requests[r_id] = req_angle

                elif msg_type == MSG_DATA_REPORT:
                    r_id, angle, dist, ts = struct.unpack('<BffI', payload)
                    
                    with self.lock:
                        if r_id in self.requests:
                            self.reports_received.add(r_id)

                    if dist < 0:
                        continue
                    if dist == 0:
                        continue
                    if dist > 50.0:
                        continue

                    coords = self.calculate_global_coords(r_id, angle, dist)
                    if coords:
                        if dist <= 10.0:
                            estado = "🔴 DEFCON 1"
                        elif dist <= 20.0:
                            estado = "🟡 DEFCON 2"
                        elif dist <= 30.0:
                            estado = "🟢 DEFCON 3"
                        else:
                            estado = "🔵 VALLA VIRTUAL"
                        
                        print(f"  -> [N{r_id}] {estado} | Ángulo: {angle:5.1f}° | Dist: {dist:5.1f}cm | Coord: ({coords[0]:.1f}, {coords[1]:.1f})")

        except socket.timeout:
            pass
        except Exception:
            pass
        finally:
            with self.lock:
                if conn in self.clients: del self.clients[conn]
                if radar_id in self.client_sockets: del self.client_sockets[radar_id]
                if radar_id in self.requests: del self.requests[radar_id]
                if radar_id in self.reports_received: self.reports_received.discard(radar_id)
            conn.close()

    def orchestration_loop(self):
        while self.running:
            with self.lock:
                num_clients = len(self.client_sockets)
                
            if num_clients == 0:
                time.sleep(0.5)
                continue

            t_start_sf = time.time()
            server_time = int(t_start_sf * 1000) & 0xFFFFFFFF
            payload_sf = struct.pack('<II', self.seq, server_time)
            
            print(f"\n[=== SF {self.seq} ===]")
            
            with self.lock:
                self.requests.clear()
                self.reports_received.clear()
                for r_id, sock in list(self.client_sockets.items()):
                    try:
                        sock.sendall(struct.pack('<BH', MSG_SUPERFRAME_START, 8) + payload_sf)
                    except:
                        pass
            
            # FASE 2: PETICIONES (Se amplía la paciencia a 1 segundo para compensar lag de TCP)
            timeout = 0
            while self.running:
                with self.lock:
                    if len(self.requests) >= len(self.client_sockets):
                        break
                time.sleep(0.01)
                timeout += 1
                if timeout > 100: 
                    break

            with self.lock:
                active_reqs = dict(self.requests)

            if not active_reqs:
                continue

            slots_assigned = {}
            used_angles = {}
            max_delay_ms = 0

            BASE_MOVEMENT_TIME = 100 
            SLOT_DURATION = 100

            for r_id, target_angle in active_reqs.items():
                cfg = next((r for r in self.grid.values() if r["id"] == r_id), None)
                global_angle = (cfg["theta"] + target_angle) % 360 if cfg else target_angle
                
                assigned_slot = 0
                for assigned_id, slot in slots_assigned.items():
                    if slot == assigned_slot:
                        global_assigned = used_angles[assigned_id]
                        diff = abs((global_angle - global_assigned + 180) % 360 - 180)
                        son_extremos = (r_id == 1 and assigned_id == 3) or (r_id == 3 and assigned_id == 1)
                        
                        if diff < 30.0 and not son_extremos:
                            assigned_slot += 1
                            if assigned_slot > 1: assigned_slot = 1
                            break
                
                slots_assigned[r_id] = assigned_slot
                used_angles[r_id] = global_angle
                
                delay_ms = BASE_MOVEMENT_TIME + (assigned_slot * SLOT_DURATION) + int(SLOT_DURATION / 2)
                if delay_ms > max_delay_ms: max_delay_ms = delay_ms
                
                payload_assign = struct.pack('<BBIf', r_id, assigned_slot, delay_ms, target_angle)
                sock = self.client_sockets.get(r_id)
                if sock:
                    try:
                        sock.sendall(struct.pack('<BH', MSG_SLOT_ASSIGN, 10) + payload_assign)
                    except:
                        pass
            
            # FASE 3: EJECUCIÓN (Se amplía la pausa dinámica para garantizar llegada del hardware)
            time.sleep((max_delay_ms + 150) / 1000.0)

            # FASE 4: REPORT (Se amplía la paciencia a 1.5 segundos)
            packet_req = struct.pack('<BH', MSG_REPORT_REQ, 0)
            with self.lock:
                for r_id, sock in list(self.client_sockets.items()):
                    try:
                        sock.sendall(packet_req)
                    except:
                        pass

            timeout = 0
            while self.running:
                with self.lock:
                    if len(self.reports_received) >= len(self.requests):
                        break
                time.sleep(0.01)
                timeout += 1
                if timeout > 150: 
                    break

            t_end_sf = time.time()
            self.seq += 1

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.settimeout(1.0) 
        server.listen(5)
        print(f"[SYS] Árbitro Iniciado - Puerto {PORT}")
        threading.Thread(target=self.orchestration_loop, daemon=True).start()
        try:
            while self.running:
                try:
                    conn, addr = server.accept()
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            self.running = False
        finally:
            server.close()

if __name__ == "__main__":
    ArbitroServer().start()