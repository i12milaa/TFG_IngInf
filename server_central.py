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

# Parámetros de Geometría y Tracking
SWEEP_ANGLE_TOTAL = 90.0
A_MAX = SWEEP_ANGLE_TOTAL / 2.0
A_MIN = -A_MAX
DIRTY_MARGIN = 15.0
TRACK_MARGIN = 15.0
TRACK_LIMIT_DIST = 20.0
MAX_MISSES = 3
STEP_ANGLE = 5.0
STEAL_MARGIN = 2.0 

# Física del Motor
MOTOR_STEPS_REV = 200
MICROSTEPPING = 16
GEAR_RATIO = 1.0
STEP_DELAY_MS = 2.2 

class ArbitroServer:
    def __init__(self):
        self.clients = {}         
        self.client_sockets = {}  
        self.requests = {}        
        self.reports_received = set() 
        self.latest_reports = {}   
        self.track_states = {}     
        self.lock = threading.Lock()
        self.seq = 0
        self.current_phase = 0 
        self.running = True
        self.grid = self.load_grid()
        self._last_save_time = 0
        self._save_debounce_interval = 2 
        # Socket para enviar datos a la interfaz gráfica
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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

    def calcular_trilateracion(self, id1, d1, id2, d2):
        """Calcula la intersección de dos circunferencias (Validación Híbrida)"""
        cfg1 = next((r for r in self.grid.values() if r["id"] == id1), None)
        cfg2 = next((r for r in self.grid.values() if r["id"] == id2), None)
        if not cfg1 or not cfg2: return None
        
        x1, y1 = cfg1["x"], cfg1["y"]
        x2, y2 = cfg2["x"], cfg2["y"]
        d = math.hypot(x2 - x1, y2 - y1)
        
        if d > d1 + d2 or d < abs(d1 - d2) or d == 0: return None 
            
        a = (d1**2 - d2**2 + d**2) / (2 * d)
        h = math.sqrt(max(0, d1**2 - a**2))
        x3 = x1 + a * (x2 - x1) / d
        y3 = y1 + a * (y2 - y1) / d
        
        iy = y3 + h * (x2 - x1) / d
        if iy > y1 and iy > y2:
            return (x3 - h * (y2 - y1) / d, iy)
        else:
            return (x3 + h * (y2 - y1) / d, y3 - h * (x2 - x1) / d)

    def calculate_movement_time(self, current_angle, target_angle):
        diff = abs(target_angle - current_angle)
        steps = (diff / 360.0) * MOTOR_STEPS_REV * MICROSTEPPING * GEAR_RATIO
        return int(steps * STEP_DELAY_MS)

    def get_state(self, r_id):
        if r_id not in self.track_states:
            self.track_states[r_id] = {
                'mode': 'SEARCH',
                'search_dir': 1.0,
                'track_dir': 1.0,
                'misses': 0,
                'current_angle': 0.0
            }
        return self.track_states[r_id]

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
                    if len(payload) < 6: continue
                    mac_bytes = struct.unpack('<6B', payload[:6])
                    mac_str = ":".join([f"{b:02X}" for b in mac_bytes])
                    
                    with self.lock:
                        if mac_str in self.grid:
                            radar_id = self.grid[mac_str]["id"]
                        else:
                            radar_id = len(self.grid) + 1
                            self.grid[mac_str] = {"id": radar_id, "x": 0.0, "y": 0.0, "theta": 90.0}
                            now = time.time()
                            if now - self._last_save_time > self._save_debounce_interval:
                                self.save_grid()
                                self._last_save_time = now
                            
                        self.clients[conn] = radar_id
                        self.client_sockets[radar_id] = conn
                    
                    print(f"[SYS] Conectado MAC {mac_str} -> ID {radar_id}")
                    conn.sendall(struct.pack('<BHH', MSG_HELLO_ACK, 2, radar_id))

                elif msg_type == MSG_ANGLE_REQ:
                    with self.lock:
                        if self.current_phase == 1: 
                            if len(payload) >= 9:
                                r_id, curr_angle, req_angle = struct.unpack('<Bff', payload)
                                self.requests[r_id] = True
                            else:
                                r_id, curr_angle, req_angle = struct.unpack('<Bff', payload)
                                self.requests[r_id] = True

                elif msg_type == MSG_DATA_REPORT:
                    if len(payload) < 13: continue
                    r_id, angle, dist, ts = struct.unpack('<BffI', payload)
                    
                    with self.lock:
                        if self.current_phase == 4 and r_id in self.requests:
                            self.reports_received.add(r_id)
                            self.latest_reports[r_id] = {'angle': angle, 'dist': dist}

                    if dist <= 0 or dist > 50.0:
                        if dist < 0: print(f"  -> [N{r_id}] ⚫ MEDICIÓN INVÁLIDA")
                        elif dist == 0: print(f"  -> [N{r_id}] ⚪ SIN OBSTÁCULO")
                        else: print(f"  -> [N{r_id}] ⚪ SIN OBSTÁCULO (>50cm): {dist:.1f}cm")
                        continue

                    coords = self.calculate_global_coords(r_id, angle, dist)
                    if coords:
                        if dist <= 10.0: estado = "🔴 DEFCON 1"
                        elif dist <= 20.0: estado = "🟡 DEFCON 2"
                        elif dist <= 30.0: estado = "🟢 DEFCON 3"
                        else: estado = "🔵 VALLA VIRTUAL"
                        print(f"  -> [N{r_id}] {estado} | Ángulo: {angle:5.1f}° | Dist: {dist:5.1f}cm | Coord: ({coords[0]:.1f}, {coords[1]:.1f})")

        except socket.timeout:
            pass
        except Exception:
            pass
        finally:
            with self.lock:
                if conn in self.clients: del self.clients[conn]
                if radar_id in self.client_sockets: del self.client_sockets[radar_id]
                if radar_id is not None and radar_id in self.requests: del self.requests[radar_id]
                if radar_id is not None and radar_id in self.reports_received: self.reports_received.discard(radar_id)
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
                self.current_phase = 1
                self.requests.clear()
                self.reports_received.clear()
                self.latest_reports.clear()
                for r_id, sock in list(self.client_sockets.items()):
                    try: sock.sendall(struct.pack('<BH', MSG_SUPERFRAME_START, 8) + payload_sf)
                    except: pass
            
            timeout = 0
            while self.running:
                with self.lock:
                    if len(self.requests) >= len(self.client_sockets): break
                time.sleep(0.01)
                timeout += 1
                if timeout > 50: break # Mantenemos tu timeout original

            with self.lock:
                active_reqs = list(self.requests.keys())
                self.current_phase = 2 

            if not active_reqs:
                self.seq += 1
                continue

            slots_assigned = {}
            used_angles = {}
            max_movement_time_ms = 0
            SLOT_DURATION = 100

            for r_id in active_reqs:
                state = self.get_state(r_id)
                
                if state['mode'] == 'SEARCH':
                    target_angle = state['current_angle'] + (state['search_dir'] * STEP_ANGLE)
                    if target_angle >= A_MAX:
                        target_angle = A_MAX
                        state['search_dir'] = -1.0
                    elif target_angle <= A_MIN:
                        target_angle = A_MIN
                        state['search_dir'] = 1.0
                else:
                    target_angle = state['current_angle'] + (state['track_dir'] * STEP_ANGLE)
                    if target_angle >= (A_MAX + TRACK_MARGIN):
                        target_angle = A_MAX + TRACK_MARGIN
                        state['track_dir'] = -1.0
                        state['misses'] += 1 
                    elif target_angle <= (A_MIN - TRACK_MARGIN):
                        target_angle = A_MIN - TRACK_MARGIN
                        state['track_dir'] = 1.0
                        state['misses'] += 1 

                mov_time = self.calculate_movement_time(state['current_angle'], target_angle)
                if mov_time > max_movement_time_ms:
                    max_movement_time_ms = mov_time

                state['current_angle'] = target_angle

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

            BASE_MOVEMENT_TIME = max_movement_time_ms + 50 
            max_delay_ms = 0

            for r_id in active_reqs:
                state = self.get_state(r_id)
                assigned_slot = slots_assigned[r_id]
                target_angle = state['current_angle']
                
                delay_ms = BASE_MOVEMENT_TIME + (assigned_slot * SLOT_DURATION) + int(SLOT_DURATION / 2)
                if delay_ms > max_delay_ms: max_delay_ms = delay_ms
                
                sock = self.client_sockets.get(r_id)
                payload_assign = struct.pack('<BBIf', r_id, assigned_slot, delay_ms, target_angle)
                if sock:
                    try:
                        sock.sendall(struct.pack('<BH', MSG_SLOT_ASSIGN, 10) + payload_assign)
                        print(f"  -> N{r_id} Asignado: {target_angle:5.1f}° (Slot {assigned_slot}, Centro en {delay_ms}ms) | Modo: {state['mode']}")
                    except: pass
            
            time.sleep((max_delay_ms + 150) / 1000.0)

            packet_req = struct.pack('<BH', MSG_REPORT_REQ, 0)
            with self.lock:
                self.current_phase = 4
                self.reports_received.clear()
                self.latest_reports.clear()
                for r_id in active_reqs: 
                    sock = self.client_sockets.get(r_id)
                    if sock:
                        try: sock.sendall(packet_req)
                        except: pass

            timeout = 0
            while self.running:
                with self.lock:
                    if len(self.reports_received) >= len(self.requests): break
                time.sleep(0.01)
                timeout += 1
                if timeout > 50: break # Mantenemos tu timeout original

            hits = {r_id: data for r_id, data in self.latest_reports.items() if 0 < data['dist'] <= TRACK_LIMIT_DIST}

            # VALIDACIÓN DE TRILATERACIÓN (Se imprime en consola si hay solape)
            if 1 in hits and 2 in hits:
                pos_tri = self.calcular_trilateracion(1, hits[1]['dist'], 2, hits[2]['dist'])
                if pos_tri: print(f"  [VALIDACIÓN] Trilateración N1-N2: ({pos_tri[0]:.1f}, {pos_tri[1]:.1f})")
            if 2 in hits and 3 in hits:
                pos_tri = self.calcular_trilateracion(2, hits[2]['dist'], 3, hits[3]['dist'])
                if pos_tri: print(f"  [VALIDACIÓN] Trilateración N2-N3: ({pos_tri[0]:.1f}, {pos_tri[1]:.1f})")

            clean_hits = []
            overlap_left = []  
            overlap_right = [] 

            for r_id, data in hits.items():
                a = data['angle']
                cfg = next((r for r in self.grid.values() if r["id"] == r_id), None)
                if not cfg: continue
                global_a = (cfg["theta"] + a) % 360
                
                if 95 <= global_a <= 140:
                    overlap_left.append(r_id)
                elif 40 <= global_a <= 85:
                    overlap_right.append(r_id)
                else:
                    clean_hits.append(r_id)

            winners = set(clean_hits)
            losers = set()

            def resolve_conflict(conflict_list):
                if not conflict_list: return
                if len(conflict_list) == 1:
                    winners.add(conflict_list[0])
                    return
                
                best_id = None
                best_dist = 9999.0
                
                for c_id in conflict_list:
                    dist = hits[c_id]['dist']
                    state = self.get_state(c_id)
                    if state['mode'] == 'TRACK': dist -= STEAL_MARGIN
                    
                    if dist < best_dist:
                        best_dist = dist
                        best_id = c_id
                
                winners.add(best_id)
                for c_id in conflict_list:
                    if c_id != best_id: losers.add(c_id)

            resolve_conflict(overlap_left)
            resolve_conflict(overlap_right)

            for r_id in active_reqs:
                state = self.get_state(r_id)
                if r_id in winners:
                    if state['mode'] == 'SEARCH': state['track_dir'] = state['search_dir'] 
                    state['mode'] = 'TRACK'
                    state['misses'] = 0
                elif r_id in losers:
                    state['mode'] = 'SEARCH'
                    state['misses'] = 0
                else:
                    if state['mode'] == 'TRACK':
                        state['misses'] += 1
                        state['track_dir'] *= -1.0 
                        if state['misses'] >= MAX_MISSES:
                            state['mode'] = 'SEARCH'
                            state['misses'] = 0

            # ENVÍO UDP A PYGAME
            ui_state = {
                "seq": self.seq,
                "radars": {r: self.get_state(r) for r in self.client_sockets.keys()},
                "hits": hits
            }
            try:
                self.udp_sock.sendto(json.dumps(ui_state).encode(), ('127.0.0.1', 8081))
            except: pass

            t_end_sf = time.time()
            print(f"  [DURACIÓN SF {self.seq}] {int((t_end_sf - t_start_sf)*1000)} ms")
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
                    # AÑADE ESTA LÍNEA EXACTAMENTE AQUÍ:
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            self.running = False
        finally:
            server.close()

if __name__ == "__main__":
    ArbitroServer().start()