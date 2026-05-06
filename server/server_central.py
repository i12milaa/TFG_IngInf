import socket
import struct
import threading
import time
import math
import json
import os

try:
    from zeroconf import Zeroconf, ServiceInfo
    _ZEROCONF_OK = True
except ImportError:
    _ZEROCONF_OK = False
    print("[WARN] Instala zeroconf para mDNS:  pip install zeroconf")

def _get_all_local_ips():
    ips = []
    try:
        import ifaddr
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and not ip.ip.startswith('127.') and not ip.ip.startswith('169.254.'):
                    ips.append(ip.ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect(('10.254.254.254', 1))
            ips = [s.getsockname()[0]]
            s.close()
        except Exception:
            ips = ['127.0.0.1']
    return ips

HOST = '0.0.0.0'
PORT = 8080

_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_HERE, 'config', 'grid_config.json')
STATE_FILE  = os.path.join(_HERE, 'config', 'radar_state.json')

MSG_HELLO_REQ        = 0xA0
MSG_HELLO_ACK        = 0xA1
MSG_SUPERFRAME_START = 0xB0
MSG_SLOT_ASSIGN      = 0xB1
MSG_REPORT_REQ       = 0xB2
MSG_ANGLE_REQ        = 0xC0
MSG_DATA_REPORT      = 0xD0

SWEEP_ANGLE_TOTAL = 90.0
A_MAX = SWEEP_ANGLE_TOTAL / 2.0
A_MIN = -A_MAX
DIRTY_MARGIN = 15.0
TRACK_MARGIN = 15.0
TRACK_LIMIT_DIST = 10.0
MAX_MISSES = 3
STEP_ANGLE = 5.0
STEAL_MARGIN = 2.0
TRACK_LOCK_DURATION = 6

MOTOR_STEPS_REV = 200
MICROSTEPPING = 16
GEAR_RATIO = 1.0
STEP_DELAY_MS = 2.0  # 1000µs por flanco × 2 = 2ms por micropaso

class ArbitroServer:
    def __init__(self):
        self.clients = {}
        self.client_sockets = {}
        self.requests = {}
        self.reports_received = set()
        self.latest_reports = {}
        self.track_states = {}
        self.strikes = {}
        self.grace_until_sf = {}
        self.track_lock = {}
        self.lock = threading.Lock()
        self.seq = 0
        self.current_phase = 0 
        self.running = True
        self.grid = self.load_grid()
        self.track_states = self.load_state() 
        self._last_save_time = 0
        self._save_debounce_interval = 2 
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_buffers = {} # Buffer por cliente

    def load_grid(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_grid(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.grid, f, indent=4)

    def load_state(self):
        if os.path.exists(STATE_FILE):
            print("\n==================================================")
            print("💾 ATENCIÓN: Se ha detectado una sesión anterior.")
            print("==================================================")
            ans = input("¿Deseas reanudar las posiciones de los radares? (s/n): ")
            
            if ans.lower() == 's':
                try:
                    with open(STATE_FILE, 'r') as f:
                        data = json.load(f)
                        print("[SYS] Memoria cargada. IMPORTANTE: Los radares NO deben haberse movido a mano.")
                        return {int(k): v for k, v in data.items()}
                except Exception as e:
                    print(f"[ERR] No se pudo cargar el estado: {e}")
            else:
                print("[SYS] Memoria descartada. Asumiendo que has centrado los radares a mano (0º).")
                try:
                    os.remove(STATE_FILE)
                except:
                    pass
        return {}

    def save_state(self):
        print(f"\n[SYS] Guardando estado de radares en {STATE_FILE}...")
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.track_states, f, indent=4)
            print("[SYS] Estado guardado correctamente.")
        except Exception as e:
            print(f"[ERR] Error al guardar el estado: {e}")

    def calculate_global_coords(self, radar_id, local_angle, distance):
        cfg = next((r for r in self.grid.values() if r["id"] == radar_id), None)
        if not cfg or distance <= 0: return None
        global_angle = math.radians(cfg["theta"] + local_angle)
        obj_x = cfg["x"] + distance * math.cos(global_angle)
        obj_y = cfg["y"] + distance * math.sin(global_angle)
        return (obj_x, obj_y)

    def calcular_trilateracion(self, id1, d1, id2, d2):
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
                'current_angle': 0.0,
                'track_min': 0.0,
                'track_max': 0.0
            }
        state = self.track_states[r_id]
        state.setdefault('track_min', 0.0)
        state.setdefault('track_max', 0.0)
        return state

    def remove_client(self, conn, r_id):
        if conn in self.clients: del self.clients[conn]
        if conn in self.client_buffers: del self.client_buffers[conn]
        if r_id in self.client_sockets: del self.client_sockets[r_id]
        if r_id in self.requests: del self.requests[r_id]
        if r_id in self.reports_received: self.reports_received.discard(r_id)
        if r_id in self.grace_until_sf: del self.grace_until_sf[r_id]
        if r_id in self.track_lock: del self.track_lock[r_id]
        try: conn.close()
        except: pass

    def handle_client(self, conn, addr):
        conn.settimeout(0.5) 
        radar_id = None
        self.client_buffers[conn] = b''
        last_activity = time.time()
        
        try:
            while self.running:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    last_activity = time.time()
                    with self.lock:
                        self.client_buffers[conn] += data
                except socket.timeout:
                    if time.time() - last_activity > 15.0:
                        break
                    continue
                except Exception:
                    break

                with self.lock:
                    buffer = self.client_buffers[conn]
                    while len(buffer) >= 3:
                        msg_type, msg_length = struct.unpack('<BH', buffer[:3])
                        
                        if len(buffer) < 3 + msg_length:
                            break 
                            
                        payload = buffer[3:3+msg_length]
                        buffer = buffer[3+msg_length:]
                        
                        if msg_type == MSG_HELLO_REQ:
                            if len(payload) < 6: continue
                            mac_bytes = struct.unpack('<6B', payload[:6])
                            mac_str = ":".join([f"{b:02X}" for b in mac_bytes])
                            
                            saved_angle = 0.0 
                            
                            if mac_str in self.grid:
                                radar_id = self.grid[mac_str]["id"]
                            else:
                                radar_id = len(self.grid) + 1
                                self.grid[mac_str] = {"id": radar_id, "x": 0.0, "y": 0.0, "theta": 90.0}
                                now = time.time()
                                if now - self._last_save_time > self._save_debounce_interval:
                                    self.save_grid()
                                    self._last_save_time = now
                                    
                            if radar_id in self.track_states:
                                saved_angle = self.track_states[radar_id]['current_angle']
                                
                            self.clients[conn] = radar_id
                            self.client_sockets[radar_id] = conn
                            self.strikes[radar_id] = 0
                            self.grace_until_sf[radar_id] = self.seq + 8
                            
                            print(f"[SYS] Conectado MAC {mac_str} -> ID {radar_id} (Reanudando en {saved_angle}º)")
                            try:
                                conn.sendall(struct.pack('<BHBf', MSG_HELLO_ACK, 5, radar_id, saved_angle))
                            except: pass

                        elif msg_type == MSG_ANGLE_REQ:
                            if self.current_phase == 1: 
                                r_id, curr_angle, req_angle = struct.unpack('<Bff', payload[:9])
                                self.requests[r_id] = True

                        elif msg_type == MSG_DATA_REPORT:
                            if len(payload) < 13: continue
                            r_id, angle, dist, ts = struct.unpack('<BffI', payload[:13])
                            
                            if self.current_phase == 4 and r_id in self.requests:
                                self.reports_received.add(r_id)
                                self.latest_reports[r_id] = {'angle': angle, 'dist': dist}
                                self.strikes[r_id] = 0

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
                                
                    self.client_buffers[conn] = buffer

        except Exception:
            pass
        finally:
            with self.lock:
                self.remove_client(conn, radar_id)

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
                expected_nodes = list(self.client_sockets.keys()) 
                socks_to_send = list(self.client_sockets.items())

            for r_id, sock in socks_to_send:
                try: sock.sendall(struct.pack('<BH', MSG_SUPERFRAME_START, 8) + payload_sf)
                except: pass
            
            with self.lock:
                # Solo esperamos a nodos sanos: pasada la grace Y sin strikes activos.
                non_grace_count = sum(
                    1 for r in self.client_sockets
                    if self.seq > self.grace_until_sf.get(r, 0)
                    and self.strikes.get(r, 0) == 0
                )

            t_wait_req = time.time()
            while self.running:
                with self.lock:
                    if non_grace_count == 0 or len(self.requests) >= non_grace_count: break
                if time.time() - t_wait_req > 0.5: break
                time.sleep(0.01)

            with self.lock:
                active_reqs = list(self.requests.keys())
                self.current_phase = 2 

            for r_id in expected_nodes:
                if r_id not in active_reqs:
                    if r_id not in self.client_sockets:
                        continue
                    if self.seq <= self.grace_until_sf.get(r_id, 0):
                        continue
                    self.strikes[r_id] = self.strikes.get(r_id, 0) + 1
                    print(f"  [WARN] Nodo {r_id} fantasma (sin petición). Strike {self.strikes[r_id]}/7")
                    if self.strikes[r_id] >= 7:
                        print(f"  [KICK] Nodo {r_id} atascado en inicio. Forzando cierre...")
                        with self.lock:
                            sock = self.client_sockets.get(r_id)
                            if sock: self.remove_client(sock, r_id)

            if not active_reqs:
                time.sleep(0.2)
                self.seq += 1
                continue

            slots_assigned = {}
            used_angles = {}
            max_movement_time_ms = 0
            SLOT_DURATION = 50

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
                    obj_left  = max(A_MIN - TRACK_MARGIN, state['track_min'] - 5.0)
                    obj_right = min(A_MAX + TRACK_MARGIN, state['track_max'] + 5.0)
                    target_angle = state['current_angle'] + (state['track_dir'] * STEP_ANGLE)
                    if target_angle >= obj_right:
                        target_angle = obj_right
                        state['track_dir'] = -1.0
                    elif target_angle <= obj_left:
                        target_angle = obj_left
                        state['track_dir'] = 1.0

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

            BASE_MOVEMENT_TIME = max_movement_time_ms + 100
            max_delay_ms = 0

            # Tiempo transcurrido desde SF_START para que el firmware pueda anclar execution_time al inicio del SF
            elapsed_before_assign_loop = int((time.time() - t_start_sf) * 1000)

            for r_id in active_reqs:
                state = self.get_state(r_id)
                assigned_slot = slots_assigned[r_id]
                target_angle = state['current_angle']

                delay_ms = BASE_MOVEMENT_TIME + (assigned_slot * SLOT_DURATION) + int(SLOT_DURATION / 2)
                if delay_ms > max_delay_ms: max_delay_ms = delay_ms

                # Encodificamos el retardo relativo al inicio del SF para que el firmware
                # pueda anclarse al instante de recepción de SF_START (sin jitter de SLOT_ASSIGN)
                delay_from_sf_ms = elapsed_before_assign_loop + delay_ms

                sock = self.client_sockets.get(r_id)
                payload_assign = struct.pack('<BBIf', r_id, assigned_slot, delay_from_sf_ms, target_angle)
                if sock:
                    try:
                        sock.sendall(struct.pack('<BH', MSG_SLOT_ASSIGN, 10) + payload_assign)
                        print(f"  -> N{r_id} Asignado: {target_angle:5.1f}° (Slot {assigned_slot}, Centro en {delay_ms}ms desde asignación) | Modo: {state['mode']}")
                    except: pass
            
            time.sleep((max_delay_ms + 50) / 1000.0)

            packet_req = struct.pack('<BH', MSG_REPORT_REQ, 0)
            with self.lock:
                self.current_phase = 4
                self.reports_received.clear()
                self.latest_reports.clear()
                socks_to_send = [(r, self.client_sockets[r]) for r in active_reqs if r in self.client_sockets]
                
            for r_id, sock in socks_to_send:
                try: sock.sendall(packet_req)
                except: pass

            report_timeout_sec = (max_delay_ms + 400) / 1000.0
            t_wait_rep = time.time()
            while self.running:
                with self.lock:
                    connected_reqs = [r for r in active_reqs if r in self.client_sockets]
                    if len(self.reports_received) >= len(connected_reqs): break
                if time.time() - t_wait_rep > report_timeout_sec: break
                time.sleep(0.01)

            time.sleep(0.05)

            for r_id in active_reqs:
                if r_id not in self.client_sockets:
                    continue
                if r_id not in self.reports_received:
                    if self.seq <= self.grace_until_sf.get(r_id, 0):
                        continue
                    self.strikes[r_id] = self.strikes.get(r_id, 0) + 1
                    print(f"  [WARN] Nodo {r_id} no responde. Strike {self.strikes[r_id]}/7")
                    if self.strikes[r_id] >= 7:
                        print(f"  [KICK] Nodo {r_id} atascado en medición. Forzando cierre...")
                        with self.lock:
                            sock = self.client_sockets.get(r_id)
                            if sock: self.remove_client(sock, r_id)
                else:
                    self.strikes[r_id] = 0

            hits = {r_id: data for r_id, data in self.latest_reports.items() if 0 < data['dist'] <= TRACK_LIMIT_DIST}

            trilat_results = {}
            if 1 in hits and 2 in hits:
                pos_tri = self.calcular_trilateracion(1, hits[1]['dist'], 2, hits[2]['dist'])
                if pos_tri:
                    trilat_results['N1-N2'] = {'x': round(pos_tri[0], 1), 'y': round(pos_tri[1], 1)}
                    print(f"  [TRILAT] N1-N2: ({pos_tri[0]:.1f}, {pos_tri[1]:.1f})")
            if 2 in hits and 3 in hits:
                pos_tri = self.calcular_trilateracion(2, hits[2]['dist'], 3, hits[3]['dist'])
                if pos_tri:
                    trilat_results['N2-N3'] = {'x': round(pos_tri[0], 1), 'y': round(pos_tri[1], 1)}
                    print(f"  [TRILAT] N2-N3: ({pos_tri[0]:.1f}, {pos_tri[1]:.1f})")

            CLEAN_LIMIT = A_MAX - DIRTY_MARGIN 
            CONFLICT_PAIRS = [(1, 2), (2, 3)]  

            winners = set()
            losers = set()

            for (na, nb) in CONFLICT_PAIRS:
                na_conflict = (na in hits and hits[na]['angle'] > 0 and abs(hits[na]['angle']) > CLEAN_LIMIT)
                nb_conflict = (nb in hits and hits[nb]['angle'] < 0 and abs(hits[nb]['angle']) > CLEAN_LIMIT)

                if na_conflict and nb_conflict:
                    na_locked = self.seq <= self.track_lock.get(na, 0)
                    nb_locked = self.seq <= self.track_lock.get(nb, 0)

                    if na_locked and not nb_locked:
                        winner, loser = na, nb
                        print(f"  [CONFLICTO] N{na}/N{nb}: N{na} mantiene bloqueo (hasta SF {self.track_lock[na]}) | {hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm")
                    elif nb_locked and not na_locked:
                        winner, loser = nb, na
                        print(f"  [CONFLICTO] N{na}/N{nb}: N{nb} mantiene bloqueo (hasta SF {self.track_lock[nb]}) | {hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm")
                    else:
                        state_a = self.get_state(na)
                        state_b = self.get_state(nb)
                        eff_da = hits[na]['dist'] - (STEAL_MARGIN if state_a['mode'] == 'TRACK' else 0)
                        eff_db = hits[nb]['dist'] - (STEAL_MARGIN if state_b['mode'] == 'TRACK' else 0)
                        if eff_da <= eff_db:
                            winner, loser = na, nb
                        else:
                            winner, loser = nb, na
                        print(f"  [CONFLICTO] N{na}/N{nb}: N{winner} gana ({hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm)")

                    winners.add(winner)
                    losers.add(loser)
                    self.track_lock[winner] = self.seq + TRACK_LOCK_DURATION

            for r_id in hits:
                if r_id not in winners and r_id not in losers:
                    winners.add(r_id)

            for r_id in active_reqs:
                state = self.get_state(r_id)
                if r_id in winners:
                    a = hits[r_id]['angle']
                    if state['mode'] == 'SEARCH' or state['misses'] > 0:
                        if state['mode'] == 'SEARCH':
                            state['track_dir'] = state['search_dir']
                        state['track_min'] = a
                        state['track_max'] = a
                    else:
                        prev_min = state['track_min']
                        prev_max = state['track_max']
                        state['track_min'] = min(state['track_min'], a)
                        state['track_max'] = max(state['track_max'], a)
                        if a > prev_max and state['track_dir'] == -1.0:
                            state['track_dir'] = 1.0
                        elif a < prev_min and state['track_dir'] == 1.0:
                            state['track_dir'] = -1.0
                    state['mode'] = 'TRACK'
                    state['misses'] = 0
                elif r_id in losers:
                    state['mode'] = 'SEARCH'
                    state['misses'] = 0
                    self.track_lock.pop(r_id, None)
                else:
                    if state['mode'] == 'TRACK':
                        state['misses'] += 1
                        if state['misses'] >= MAX_MISSES:
                            state['mode'] = 'SEARCH'
                            state['misses'] = 0
                            self.track_lock.pop(r_id, None)

            ui_state = {
                "seq": self.seq,
                "radars": {r: self.get_state(r) for r in self.client_sockets.keys()},
                "hits": hits,
                "trilat": trilat_results
            }
            try:
                self.udp_sock.sendto(json.dumps(ui_state).encode(), ('127.0.0.1', 8081))
            except: pass

            t_end_sf = time.time()
            print(f"  [DURACIÓN SF {self.seq}] {int((t_end_sf - t_start_sf)*1000)} ms")
            self.seq += 1

    def start(self):
        zc = None
        zc_info = None
        if _ZEROCONF_OK:
            local_ips = _get_all_local_ips()
            zc = Zeroconf()
            zc_info = ServiceInfo(
                "_radar._tcp.local.",
                "radar-server._radar._tcp.local.",
                addresses=[socket.inet_aton(ip) for ip in local_ips],
                port=PORT,
                server="radar-server.local."
            )
            zc.register_service(zc_info)
            print(f"[mDNS] radar-server.local -> {', '.join(local_ips)}")

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
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\n[SYS] Servidor detenido por el usuario (Ctrl+C).")
        finally:
            self.running = False
            self.save_state()
            server.close()
            if zc and zc_info:
                zc.unregister_service(zc_info)
                zc.close()

if __name__ == "__main__":
    ArbitroServer().start()