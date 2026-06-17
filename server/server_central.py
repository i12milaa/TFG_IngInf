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
CONFIG_FILE   = os.path.join(_HERE, 'config', 'grid_config.json')
STATE_FILE    = os.path.join(_HERE, 'config', 'radar_state.json')
VIZ_SETTINGS  = os.path.join(_HERE, '..', 'tools', 'visualizer_settings.json')

def _load_thresholds():
    """Lee todos los umbrales DEFCON del visualizador. Devuelve (d1, d2, d3, valla)."""
    try:
        with open(VIZ_SETTINGS, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return (float(d.get('defcon1', 20.0)), float(d.get('defcon2', 35.0)),
                    float(d.get('defcon3', 50.0)), float(d.get('valla',   65.0)))
    except Exception:
        return (20.0, 35.0, 50.0, 65.0)

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
DIRTY_MARGIN = 30.0
MAX_MISSES = 3
STEP_ANGLE = 2.5
TRACK_LOCK_DURATION = 6
TRACK_ENTRY_UNSET = 10**9  # Centinela: nodo no ha detectado nada en esta sesión
TRILAT_MAX_DIST_RATIO = 2.0  # Máx cociente entre distancias para considerar mismo objeto

MOTOR_STEPS_REV = 200
MICROSTEPPING = 16
GEAR_RATIO = 1.0
STEP_DELAY_MS = 2.4  # 1200µs por flanco × 2 = 2.4ms por micropaso (sincronizado con NORMAL_STEP_US en config.h)

RECONNECT_WARN_SECS = 30  # aviso si un nodo kickeado no reconecta en este tiempo

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
        self.kick_count = {}       # cuántas veces ha sido kickeado cada nodo en la sesión
        self.kick_time = {}        # timestamp del último KICK por nodo (para aviso de no-reconexión)
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
        self.defcon1_limit, self.defcon2_limit, self.defcon3_limit, self.valla_limit = _load_thresholds()

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

    def _save_state_silent(self):
        """Guardado silencioso periódico — sin salida por consola."""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.track_states, f)
        except Exception:
            pass

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
                'edge_flips': 0,
                'track_entry_sf': TRACK_ENTRY_UNSET,
                'current_angle': 0.0,
            }
        state = self.track_states[r_id]
        if 'edge_flips' not in state:
            state['edge_flips'] = 0
        if 'track_entry_sf' not in state or state['track_entry_sf'] == 0:
            state['track_entry_sf'] = TRACK_ENTRY_UNSET
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

    def _do_kick(self, r_id, reason: str):
        """Centraliza el KICK: registra contador, timestamp, y cierra el socket."""
        self.kick_count[r_id] = self.kick_count.get(r_id, 0) + 1
        self.kick_time[r_id] = time.time()
        n = self.kick_count[r_id]
        print(f"  [KICK #{n}] Nodo {r_id} {reason}. Forzando cierre...")
        sock = self.client_sockets.get(r_id)
        if sock:
            self.remove_client(sock, r_id)

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

                            kicks = self.kick_count.get(radar_id, 0)
                            reconnect_info = f" [reconexión tras KICK #{kicks}]" if kicks > 0 else ""
                            if radar_id in self.kick_time:
                                del self.kick_time[radar_id]
                            print(f"[SYS] Conectado MAC {mac_str} -> ID {radar_id} (Reanudando en {saved_angle}º){reconnect_info}")
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
                                if 0 < dist <= self.valla_limit:
                                    coords = self.calculate_global_coords(r_id, angle, dist)
                                    entry = {'angle': angle, 'dist': dist}
                                    if coords:
                                        entry['gx'] = round(coords[0], 1)
                                        entry['gy'] = round(coords[1], 1)
                                    self.latest_reports[r_id] = entry
                                self.strikes[r_id] = 0

                            if dist <= 0 or dist > self.valla_limit:
                                if dist < 0: print(f"  [N{r_id}] ⚫ MEDICIÓN INVÁLIDA")
                                continue
                                
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

            print(f"\n── SF {self.seq} {'─'*44}")

            # Aviso si un nodo kickeado lleva demasiado tiempo sin reconectar.
            now = time.time()
            with self.lock:
                for r_id, t_kick in list(self.kick_time.items()):
                    if r_id not in self.client_sockets and now - t_kick > RECONNECT_WARN_SECS:
                        elapsed = int(now - t_kick)
                        kicks = self.kick_count.get(r_id, 1)
                        print(f"[CRIT] SF{self.seq} Nodo {r_id} sin reconectar {elapsed}s (KICK #{kicks}) — posible fallo hardware.")
                        # Actualizar timestamp para no repetir el aviso cada SF
                        self.kick_time[r_id] = now

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
                    print(f"[WARN] SF{self.seq} Nodo {r_id} sin petición. Strike {self.strikes[r_id]}/7")
                    if self.strikes[r_id] >= 7:
                        with self.lock:
                            self._do_kick(r_id, "atascado en inicio")

            if not active_reqs:
                time.sleep(0.2)
                self.seq += 1
                continue

            CLEAN_LIMIT = A_MAX - DIRTY_MARGIN
            slots_assigned = {}
            used_angles = {}
            used_local_angles = {}
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
                    target_angle = state['current_angle'] + (state['track_dir'] * STEP_ANGLE)
                    if target_angle >= A_MAX:
                        target_angle = A_MAX
                        state['track_dir'] = -1.0
                    elif target_angle <= A_MIN:
                        target_angle = A_MIN
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
                        # Par adyacente con ambos en zona sucia → slots forzosamente distintos
                        is_conflict_pair = (
                            (r_id == 1 and assigned_id == 2) or (r_id == 2 and assigned_id == 1) or
                            (r_id == 2 and assigned_id == 3) or (r_id == 3 and assigned_id == 2)
                        )
                        local_assigned = used_local_angles.get(assigned_id, 0.0)
                        if is_conflict_pair and abs(target_angle) > CLEAN_LIMIT and abs(local_assigned) > CLEAN_LIMIT:
                            assigned_slot = (assigned_slot + 1) % 2
                            break
                        global_assigned = used_angles[assigned_id]
                        diff = abs((global_angle - global_assigned + 180) % 360 - 180)
                        son_extremos = (r_id == 1 and assigned_id == 3) or (r_id == 3 and assigned_id == 1)
                        if diff < 30.0 and not son_extremos:
                            assigned_slot = (assigned_slot + 1) % 2
                            break

                slots_assigned[r_id] = assigned_slot
                used_angles[r_id] = global_angle
                used_local_angles[r_id] = target_angle

            BASE_MOVEMENT_TIME = max_movement_time_ms + 100
            max_delay_ms = 0
            sf_summary = {}  # {r_id: {'mode': ..., 'angle': ..., 'slot': ...}}

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
                    except: pass

                sf_summary[r_id] = {
                    'mode':  state['mode'],
                    'angle': target_angle,
                    'slot':  assigned_slot,
                }
            
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
                    print(f"[WARN] SF{self.seq} Nodo {r_id} no responde. Strike {self.strikes[r_id]}/7")
                    if self.strikes[r_id] >= 7:
                        with self.lock:
                            self._do_kick(r_id, "atascado en medición")
                else:
                    self.strikes[r_id] = 0

            self.defcon1_limit, self.defcon2_limit, self.defcon3_limit, self.valla_limit = _load_thresholds()
            track_threshold = self.defcon1_limit
            hits = {r_id: data for r_id, data in self.latest_reports.items() if 0 < data['dist'] <= track_threshold}

            trilat_results = {}
            # Posición combinada: AMBOS en zona sucia (cualquier DEFCON)
            for pair_key, na, nb in [('N1-N2', 1, 2), ('N2-N3', 2, 3)]:
                da = self.latest_reports.get(na)
                db = self.latest_reports.get(nb)
                if (da and db
                        and 'gx' in da and 'gx' in db
                        and da['angle'] > CLEAN_LIMIT
                        and db['angle'] < -CLEAN_LIMIT
                        and max(da['dist'], db['dist']) / min(da['dist'], db['dist']) <= TRILAT_MAX_DIST_RATIO):
                    mx = (da['gx'] + db['gx']) / 2.0
                    my = (da['gy'] + db['gy']) / 2.0
                    trilat_results[pair_key] = {'x': round(mx, 1), 'y': round(my, 1)}
                    print(f"[TRILAT] SF{self.seq} {pair_key}: ({mx:.1f}, {my:.1f})")

            CONFLICT_PAIRS = [(1, 2), (2, 3)]

            winners = set()
            losers = set()

            for (na, nb) in CONFLICT_PAIRS:
                na_dirty = na in hits and hits[na]['angle'] > CLEAN_LIMIT
                nb_dirty = nb in hits and hits[nb]['angle'] < -CLEAN_LIMIT
                if na_dirty and nb_dirty:
                    state_a = self.get_state(na)
                    state_b = self.get_state(nb)
                    na_locked = self.seq <= self.track_lock.get(na, 0)
                    nb_locked = self.seq <= self.track_lock.get(nb, 0)

                    if na_locked and not nb_locked:
                        winner, loser = na, nb
                        print(f"[CONF] SF{self.seq} N{na}/N{nb}: N{na} bloqueo hasta SF{self.track_lock[na]} | {hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm")
                    elif nb_locked and not na_locked:
                        winner, loser = nb, na
                        print(f"[CONF] SF{self.seq} N{na}/N{nb}: N{nb} bloqueo hasta SF{self.track_lock[nb]} | {hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm")
                    else:
                        # Sin bloqueo activo: gana el que primero detectó el objeto en esta sesión
                        entry_a = state_a.get('track_entry_sf', TRACK_ENTRY_UNSET)
                        entry_b = state_b.get('track_entry_sf', TRACK_ENTRY_UNSET)
                        if entry_a <= entry_b:
                            winner, loser = na, nb
                        else:
                            winner, loser = nb, na
                        sf_str = str(min(entry_a, entry_b)) if min(entry_a, entry_b) < TRACK_ENTRY_UNSET else '?'
                        print(f"[CONF] SF{self.seq} N{na}/N{nb}: N{winner} gana (1er TRACK SF{sf_str}) | {hits[na]['dist']:.1f} vs {hits[nb]['dist']:.1f} cm")

                    winners.add(winner)
                    losers.add(loser)
                    self.track_lock[winner] = self.seq + TRACK_LOCK_DURATION

            for r_id in hits:
                if r_id not in winners and r_id not in losers:
                    winners.add(r_id)

            MAX_EDGE_FLIPS = 5

            for r_id in active_reqs:
                state = self.get_state(r_id)
                if r_id in winners:
                    if state['mode'] == 'SEARCH':
                        state['track_dir'] = state['search_dir']
                        # Solo registrar la primera detección del objeto en esta sesión
                        if state['track_entry_sf'] >= TRACK_ENTRY_UNSET:
                            state['track_entry_sf'] = self.seq
                    state['mode'] = 'TRACK'
                    state['misses'] = 0
                    state['edge_flips'] = 0
                elif r_id in losers:
                    # Perdedor: vuelve a SEARCH; track_entry_sf se conserva (mismo objeto)
                    state['mode'] = 'SEARCH'
                    state['misses'] = 0
                    state['edge_flips'] = 0
                    self.track_lock.pop(r_id, None)
                else:
                    if state['mode'] == 'TRACK':
                        if r_id in self.latest_reports:
                            # Medida válida pero fuera de DEFCON1 → borde del objeto.
                            # No revertir si ya estamos en el límite: el límite ya invirtió
                            # track_dir en el bucle de asignación; revertirlo aquí lo dejaría
                            # igual que antes, congelando el motor en ±A_MAX.
                            if abs(state['current_angle']) < A_MAX:
                                state['track_dir'] *= -1.0
                            state['misses'] = 0
                            state['edge_flips'] += 1
                            if state['edge_flips'] >= MAX_EDGE_FLIPS:
                                # Demasiados rebotes → objeto de fondo, objeto perdido
                                state['mode'] = 'SEARCH'
                                state['misses'] = 0
                                state['edge_flips'] = 0
                                state['track_entry_sf'] = TRACK_ENTRY_UNSET
                                self.track_lock.pop(r_id, None)
                        else:
                            # Sin medida (> valla o timeout) → miss real
                            if state['misses'] == 0:
                                state['track_dir'] *= -1.0
                            state['misses'] += 1
                            state['edge_flips'] = 0
                            if state['misses'] >= MAX_MISSES:
                                state['mode'] = 'SEARCH'
                                state['misses'] = 0
                                state['track_entry_sf'] = TRACK_ENTRY_UNSET
                                self.track_lock.pop(r_id, None)

            detections = {r_id: data for r_id, data in self.latest_reports.items()
                          if 0 < data['dist']}
            ui_state = {
                "seq": self.seq,
                "radars": {r: self.get_state(r) for r in self.client_sockets.keys()},
                "hits": hits,
                "detections": detections,
                "trilat": trilat_results
            }
            try:
                self.udp_sock.sendto(json.dumps(ui_state).encode(), ('127.0.0.1', 8081))
            except: pass

            t_end_sf = time.time()
            sf_ms = int((t_end_sf - t_start_sf) * 1000)

            # ── Tabla de estado por nodo ──────────────────────────────────────
            D1, D2, D3 = self.defcon1_limit, self.defcon2_limit, self.defcon3_limit
            for r_id in sorted(expected_nodes):
                if r_id in sf_summary:
                    info    = sf_summary[r_id]
                    mode    = 'TRACK ' if info['mode'] == 'TRACK' else 'SEARCH'
                    angle   = f"{info['angle']:+6.1f}°"
                    slot    = f"Sl.{info['slot']}"
                    rep     = self.latest_reports.get(r_id)
                    if rep:
                        d = rep['dist']
                        xy = f"  ({rep['gx']:.1f}, {rep['gy']:.1f})" if 'gx' in rep else ''
                        if   d <= D1: det = f"🔴 DEFCON 1  {d:5.1f}cm{xy}"
                        elif d <= D2: det = f"🟡 DEFCON 2  {d:5.1f}cm{xy}"
                        elif d <= D3: det = f"🟢 DEFCON 3  {d:5.1f}cm{xy}"
                        else:         det = f"🔵 VALLA     {d:5.1f}cm"
                    else:
                        det = "·  —"
                    print(f"  N{r_id} │ {mode}  {slot}  {angle} │ {det}")
                else:
                    # Nodo conectado pero sin petición este SF
                    print(f"  N{r_id} │ ???  sin petición")

            lento = f"  ⚠ LENTO" if sf_ms > 600 else ""
            pendientes = [r for r in self.kick_time if r not in self.client_sockets]
            ausentes   = f"  ⚠ sin reconectar: N{pendientes}" if pendientes else ""
            print(f"  {sf_ms}ms{lento}{ausentes}")

            self.seq += 1

            # Guardado periódico: asegura que el estado es reciente incluso si el
            # proceso es terminado abruptamente (terminate() no ejecuta finally).
            if self.seq % 15 == 0:
                self._save_state_silent()

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
                    # TCP keepalive: detecta conexiones medio-certas sin esperar 15s de
                    # inactividad. Útil cuando el ESP32 se cuelga sin cerrar el socket.
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    if hasattr(socket, 'TCP_KEEPIDLE'):
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)   # inicio tras 5s sin actividad
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)  # sonda cada 3s
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)    # 3 fallos → cierre
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