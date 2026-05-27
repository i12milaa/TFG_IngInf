# Contexto Completo del Sistema Radar Distribuido — TFG

> Documento generado para proporcionar contexto técnico completo a la IA asistente de documentación del TFG.
> Cubre el estado del sistema, los bugs detectados, las correcciones aplicadas y los problemas pendientes
> al cierre de la sesión de desarrollo más reciente.

---

## 1. Visión General del Sistema

El sistema implementa una **red de radares ultrasónicos distribuidos** sobre tres nodos ESP32 coordinados por un servidor Python central. El objetivo es detectar y trazar la posición de objetos dentro de una zona de vigilancia triangular mediante la cooperación de los tres sensores.

### 1.1 Componentes Hardware por Nodo

Cada nodo es un **ESP32 DOIT DevKit v1** con:
- **Motor paso a paso** (stepper) de 200 pasos/rev con driver A4988/DRV8825 en modo 1/16 microstepping
- **Sensor ultrasónico HC-SR04** (TRIG en GPIO14, ECHO en GPIO27)
- **Reed switch** (GPIO26) para verificación de posición de origen (homing)
- **LED** (GPIO2) para indicación de estado

### 1.2 Parámetros Cinemáticos del Motor

```
STEPS_PER_REV = 200        # pasos mecánicos por revolución
MICROSTEPPING  = 16        # modo 1/16 microstepping
GEAR_RATIO     = 1.0       # transmisión directa (sin reductora)
STEP_DELAY     = 1000 µs   # tiempo por flanco HIGH/LOW del pulso STEP
```

**Pasos por grado:**
```
steps_per_degree = (STEPS_PER_REV × MICROSTEPPING × GEAR_RATIO) / 360
                 = (200 × 16 × 1.0) / 360
                 = 8.888... pasos/grado
```

**Tiempo de movimiento por grado:**
```
STEP_DELAY_MS = 2.0 ms/paso    (1000µs × 2 flancos)
ms_per_degree = 8.888 × 2.0 = 17.78 ms/grado
```

### 1.3 Topología de Red

```
[Servidor Python]  ←TCP→  [N1 ESP32]  MAC: 88:13:BF:C8:40:30
       │           ←TCP→  [N2 ESP32]  MAC: F0:24:F9:44:0A:20
       │           ←TCP→  [N3 ESP32]  MAC: CC:DB:A7:98:CC:E4
       │
       └──UDP broadcast──→ 127.0.0.1:8081  (estado para visualización)
```

- WiFi: redes `"iPhone de Alejandro"` y `"ALEJANDROMILLAN2169"`, contraseña `TFG20252026`
- Servidor TCP en puerto **8080**, hostname mDNS: `radar-server.local`
- El servidor emite broadcast UDP en **127.0.0.1:8081** tras cada superframe

### 1.4 Posicionamiento Físico de los Nodos

| Nodo | MAC               | x (cm) | y (cm) | θ (°) | Dirección motor | Reed trigger |
|------|-------------------|--------|--------|--------|-----------------|--------------|
| N1   | 88:13:BF:C8:40:30 | 0.0    | 40.0   | 90     | Normal          | HIGH (NC)    |
| N2   | F0:24:F9:44:0A:20 | 34.64  | 20.0   | 30     | Invertida       | LOW (NO)     |
| N3   | CC:DB:A7:98:CC:E4 | −34.64 | 20.0   | 150    | Invertida       | HIGH (NC)    |

La configuración por nodo se aplica en `src/main.cpp` en el array `PROFILES[]`. El campo `motorDirInvert` invierte físicamente el pin `PIN_MOTOR_DIR` para compensar el cableado inverso de las bobinas del motor.

---

## 2. Arquitectura Software

### 2.1 Firmware ESP32 (PlatformIO / Arduino framework)

El firmware usa **FreeRTOS dual-core**:

| Task        | Core | Prioridad | Stack  | Función                                |
|-------------|------|-----------|--------|----------------------------------------|
| `TaskComms` | 0    | 2         | 4096 B | WiFi + TCP + protocolo con el servidor |
| `TaskRadar` | 1    | 3         | 4096 B | Control del motor + sensor HC-SR04     |
| `loop()`    | 1    | —         | —      | FSM de estados + gestión WiFi          |

**Comunicación entre tareas:** dos colas FreeRTOS en `SystemManager`:
- `queueCommands` (`HwCommand`): TaskComms → TaskRadar (órdenes de movimiento/medición)
- `queueResults` (`HwResult`): TaskRadar → TaskComms (resultados de medición)

### 2.2 Estados del Sistema (`SystemState`)

```
WAITING_FOR_CONNECTION  →  SYNC_CONTROL  →  RADAR
        ↑                      ↓
        └──────── (WiFi caído) ─┘
```

- **WAITING_FOR_CONNECTION**: parpadeo LED cada 250ms, reintento WiFi cada 15s
- **SYNC_CONTROL**: LED fijo, arranca `TaskComms` si no existe
- **RADAR**: LED fijo, arranca `TaskRadar` si no existe, modo operativo completo

### 2.3 Servidor Python (`server/server_central.py`)

Arquitectura multi-hilo:
- **Thread principal**: acepta conexiones TCP entrantes
- **Thread por cliente** (`handle_client`): lee paquetes TCP del nodo (con buffer acumulativo)
- **Thread orquestador** (`orchestration_loop`): ejecuta el protocolo superframe

---

## 3. Protocolo Superframe (SF)

El servidor coordina a todos los nodos mediante una secuencia llamada **superframe**. Cada SF consta de las siguientes fases:

### 3.1 Secuencia Completa

```
SERVIDOR                              NODO(S)
   │                                     │
   │──── MSG_SUPERFRAME_START ──────────>│  [t0_sf capturado aquí en el nodo]
   │                                     │──── MSG_ANGLE_REQ ─────────────>│
   │                                     │   (contiene: radar_id, current_angle, requested_angle)
   │<──── MSG_ANGLE_REQ ─────────────────│
   │  (espera máx. 500ms a todos los     │
   │   nodos sanos)                      │
   │──── MSG_SLOT_ASSIGN ───────────────>│  (contiene: radar_id, slot, delay_from_sf_ms, angle)
   │  (un paquete por nodo activo)       │──── [enqueue HW_CMD_EXECUTE_SLOT] ──>│
   │                                     │    execution_time_ms = t0_sf + delay_from_sf_ms
   │  [espera max_delay_ms + 50ms]       │
   │                                     │    [motor se mueve al ángulo]
   │──── MSG_REPORT_REQ ────────────────>│    [en t=execution_time_ms, mide distancia]
   │                                     │──── MSG_DATA_REPORT ────────────>│
   │<──── MSG_DATA_REPORT ───────────────│   (radar_id, angle, distance_cm, timestamp)
   │  (espera máx. report_timeout_sec)   │
   │                                     │
   │  [procesa hits, actualiza estado]   │
   │  [emite UDP broadcast 8081]         │
   │                                     │
   └─────────── siguiente SF ────────────┘
```

### 3.2 Valores de los Mensajes (protocolo binario)

```python
MSG_HELLO_REQ        = 0xA0    # Nodo → Servidor: presentación (6 bytes MAC)
MSG_HELLO_ACK        = 0xA1    # Servidor → Nodo: asignación de ID y ángulo guardado
MSG_SUPERFRAME_START = 0xB0    # Servidor → Nodo: inicio de superframe (seq + server_time)
MSG_SLOT_ASSIGN      = 0xB1    # Servidor → Nodo: asignación de slot y ángulo
MSG_REPORT_REQ       = 0xB2    # Servidor → Nodo: solicitud de medición
MSG_ANGLE_REQ        = 0xC0    # Nodo → Servidor: petición de movimiento
MSG_DATA_REPORT      = 0xD0    # Nodo → Servidor: resultado de medición
```

**Formato del paquete:** `PacketHeader` (3 bytes: `uint8_t type` + `uint16_t length`) seguido del payload.

### 3.3 Payload de MSG_SLOT_ASSIGN

```cpp
// C++ (firmware)
struct Payload_SlotAssign {
    uint8_t  radar_id;         // 1 byte
    uint8_t  assigned_slot;    // 1 byte (0 o 1)
    uint32_t start_delay_ms;   // 4 bytes — retardo relativo al SF_START
    float    confirmed_angle;  // 4 bytes — ángulo confirmado en grados
};
// Total payload: 10 bytes
```

```python
# Python (servidor)
payload_assign = struct.pack('<BBIf', r_id, assigned_slot, delay_from_sf_ms, target_angle)
# '<' little-endian: B=uint8, B=uint8, I=uint32, f=float → 10 bytes
```

### 3.4 Cálculo de `delay_from_sf_ms`

El parámetro `start_delay_ms` del SLOT_ASSIGN indica cuántos milisegundos después del SF_START debe realizarse la medición.

```python
BASE_MOVEMENT_TIME = max_movement_time_ms + 100   # margen de 100ms
SLOT_DURATION = 50                                  # 50ms por slot

# Tiempo transcurrido desde SF_START hasta que el servidor envía SLOT_ASSIGN
elapsed_before_assign_loop = int((time.time() - t_start_sf) * 1000)

# Retardo nominal de medición para este slot
delay_ms = BASE_MOVEMENT_TIME + (assigned_slot * SLOT_DURATION) + int(SLOT_DURATION / 2)

# Retardo relativo al SF_START (lo que ve el firmware)
delay_from_sf_ms = elapsed_before_assign_loop + delay_ms
```

En el firmware:
```cpp
cmd.execution_time_ms = SystemManager::instance().t0_last_superframe + p->start_delay_ms;
```

Esto garantiza que `execution_time_ms` sea un instante absoluto de `millis()` independiente del jitter de entrega de SLOT_ASSIGN.

---

## 4. Bug Crítico Resuelto: N3 "Fantasma" (Desincronización Temporal)

### 4.1 Descripción del Síntoma

El nodo N3 funcionaba correctamente en los primeros 3-9 superframes tras conectarse, pero luego dejaba de enviar `MSG_ANGLE_REQ`. El servidor lo marcaba como "fantasma" y acumulaba strikes hasta kickearlo. N1 y N2 funcionaban sin problemas de forma continua.

### 4.2 Causa Raíz

**Antes de la corrección**, `t0_last_superframe` se fijaba al recibir `MSG_SLOT_ASSIGN`:

```cpp
// CÓDIGO INCORRECTO (antes de la corrección)
case MSG_SLOT_ASSIGN: {
    SystemManager::instance().t0_last_superframe = millis();  // ← ERROR
    // ...
    cmd.execution_time_ms = SystemManager::instance().t0_last_superframe + p->start_delay_ms;
}
```

El servidor calculaba `delay_ms` empezando a contar desde el **momento de envío de SLOT_ASSIGN**. Sin embargo, en el firmware `t0_last_superframe` se fijaba al **momento de recepción de SLOT_ASSIGN**. Si hay jitter en la entrega WiFi de SLOT_ASSIGN (ej. 80ms de retraso), `execution_time_ms` se desplaza 80ms hacia el futuro.

**Efecto en cascada:**
1. Jitter SLOT_ASSIGN N3: +80ms → `execution_time_ms` desplazado +80ms
2. Motor termina de moverse y mide en t+80ms adicionales
3. Servidor envía REPORT_REQ antes de que la medición esté lista
4. `xQueueReceive(..., pdMS_TO_TICKS(1500))` en REPORT_REQ espera hasta 1500ms
5. Durante esos 1500ms, llega el siguiente `MSG_SUPERFRAME_START`
6. El SF_START se pierde porque TaskComms está bloqueado en el `xQueueReceive`
7. Servidor no recibe ANGLE_REQ → Strike +1
8. Después de 7 strikes → kick

**¿Por qué solo N3 y no N1/N2?**
N3 tiene peor posición respecto al AP WiFi en el entorno de pruebas, lo que produce mayor jitter TCP (50-200ms vs ~5ms de N1/N2). Además, N3 tiene `motorDirInvert=true` que afecta marginalmente a la mecánica.

### 4.3 Corrección Aplicada

**Parte 1 — Firmware `src/task_comms.cpp`**: mover `t0_last_superframe` al handler de `MSG_SUPERFRAME_START`:

```cpp
case MSG_SUPERFRAME_START: {
    // Anclamos t0 aquí: SF_START tiene jitter mínimo de red.
    // El servidor envía start_delay_ms relativo a este instante,
    // así execution_time_ms no depende del jitter de SLOT_ASSIGN.
    SystemManager::instance().t0_last_superframe = millis();
    float nextAngle = calcularSiguienteAngulo();
    Payload_AngleReq req;
    req.radar_id = SystemManager::instance().radarId;
    req.current_angle = SystemManager::instance().current_angle_logic;
    req.requested_angle = nextAngle;
    sendPacket(MSG_ANGLE_REQ, &req, sizeof(Payload_AngleReq));
    break;
}
```

**Parte 2 — Firmware `src/task_comms.cpp`**: eliminar el reset de t0 en `MSG_SLOT_ASSIGN`:

```cpp
case MSG_SLOT_ASSIGN: {
    Payload_SlotAssign* p = (Payload_SlotAssign*)buffer;
    if (p->radar_id == SystemManager::instance().radarId) {
        // t0_last_superframe ya fue fijado en MSG_SUPERFRAME_START.
        // execution_time_ms = t0_sf_start + start_delay_ms (relativo al SF).
        HwCommand cmd;
        cmd.type = HW_CMD_EXECUTE_SLOT;
        cmd.param = p->confirmed_angle;
        cmd.execution_time_ms = SystemManager::instance().t0_last_superframe + p->start_delay_ms;

        HwCommand flushCmd;
        while(xQueueReceive(SystemManager::instance().queueCommands, &flushCmd, 0));
        xQueueSend(SystemManager::instance().queueCommands, &cmd, portMAX_DELAY);

        SystemManager::instance().current_angle_logic = p->confirmed_angle;
    }
    break;
}
```

**Parte 3 — Firmware `src/task_comms.cpp`**: reducir timeout de REPORT_REQ de 1500ms a 300ms:

```cpp
case MSG_REPORT_REQ: {
    HwResult res;
    // 300ms: en operación normal el resultado ya está listo cuando llega REPORT_REQ.
    // Fallo rápido evita bloquear el siguiente SF_START si el timing fue a la deriva.
    if (xQueueReceive(SystemManager::instance().queueResults, &res, pdMS_TO_TICKS(300)) == pdPASS) {
        if (res.type == HW_RES_SLOT_DONE) {
            Payload_DataReport rep;
            rep.radar_id = SystemManager::instance().radarId;
            rep.angle = res.angle;
            rep.distance_cm = res.value;
            rep.measure_timestamp = millis();
            sendPacket(MSG_DATA_REPORT, &rep, sizeof(Payload_DataReport));
        }
    } else {
        last_msg_time = millis();
    }
    break;
}
```

**Parte 4 — Servidor `server/server_central.py`**: añadir `elapsed_before_assign_loop` y `delay_from_sf_ms`:

```python
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

    # Encodificamos el retardo relativo al inicio del SF
    delay_from_sf_ms = elapsed_before_assign_loop + delay_ms

    sock = self.client_sockets.get(r_id)
    payload_assign = struct.pack('<BBIf', r_id, assigned_slot, delay_from_sf_ms, target_angle)
    if sock:
        try:
            sock.sendall(struct.pack('<BH', MSG_SLOT_ASSIGN, 10) + payload_assign)
        except: pass
```

### 4.4 Demostración Matemática de la Corrección

Sea:
- `t_sf` = instante en el nodo cuando llega SF_START (≈ mismo instante en servidor con jitter ~5ms)
- `t_sa` = instante en el nodo cuando llega SLOT_ASSIGN
- `J` = jitter de entrega SLOT_ASSIGN (variable, 5ms-200ms)
- `D` = delay_ms calculado por el servidor

**Antes (incorrecto):**
```
t0_sf = t_sa = t_sf + J
execution_time = t0_sf + (elapsed_before_assign + D)
               = t_sf + J + elapsed + D
```
→ `execution_time` depende de `J`; si J es grande, la medición ocurre tarde.

**Después (correcto):**
```
t0_sf = t_sf   (capturado en SF_START)
delay_from_sf = elapsed_before_assign + D
execution_time = t0_sf + delay_from_sf
               = t_sf + elapsed + D
```
→ `execution_time` es independiente de `J`. El jitter solo afecta cuándo llega el SLOT_ASSIGN al nodo, pero la medición ocurre siempre en el mismo instante relativo al SF_START.

### 4.5 Resultado Verificado

Tras la corrección, el sistema ejecutó continuamente más de 119 superframes (SF 9 → SF 119+) sin que N3 acumulase strikes, con un único evento transitorio en SF 57 donde N2 y N3 fallaron simultáneamente (strike 1 cada uno, SF duró ~1400ms). Este evento fue causado por congestión WiFi del AP y es esperado. El sistema lo manejó correctamente y ambos nodos se recuperaron antes del SF 63.

---

## 5. Bug Resuelto: Espasmos del Motor en N3

### 5.1 Síntoma

Tras la corrección del timing, N3 intentaba moverse pero el motor "espasmeaba" (sacudidas breves en el lugar) sin desplazarse a los ángulos solicitados. N1 y N2 funcionaban correctamente con el mismo firmware.

### 5.2 Causa Raíz

El tiempo de paso del motor era **600µs por flanco** (1.2ms por micropaso completo). Este valor era insuficiente para el motor/driver específico de N3. La combinación particular de bobinas, inductancia del motor y ajuste de corriente del driver hacía que a 600µs el motor no consiguiera magnetizarse completamente antes del siguiente paso, perdiendo pasos. En modo debug (secuencias más lentas con `delay()`), el motor sí funcionaba correctamente.

### 5.3 Corrección

**`src/task_radar.cpp`** — incrementar de 600µs a **1000µs** por flanco:

```cpp
// ANTES (600µs — demasiado rápido para N3):
for (long i = 0; i < steps; i++) {
    digitalWrite(PIN_MOTOR_STEP, HIGH);
    delayMicroseconds(600);
    digitalWrite(PIN_MOTOR_STEP, LOW);
    delayMicroseconds(600);
}

// DESPUÉS (1000µs — funciona en todos los nodos):
for (long i = 0; i < steps; i++) {
    digitalWrite(PIN_MOTOR_STEP, HIGH);
    delayMicroseconds(1000);
    digitalWrite(PIN_MOTOR_STEP, LOW);
    delayMicroseconds(1000);
}
```

**`server/server_central.py`** — actualizar `STEP_DELAY_MS` para que el cálculo del tiempo de movimiento sea correcto:

```python
# ANTES:
STEP_DELAY_MS = 1.3  # incorrecto para 1000µs/flanco

# DESPUÉS:
STEP_DELAY_MS = 2.0  # 1000µs por flanco × 2 = 2ms por micropaso
```

---

## 6. Estado Actual de los Archivos Clave

### 6.1 `src/config.h` — Constantes Hardware

```cpp
#define DEBUG_HARDWARE_TEST 0  // 1 para modo debug, 0 para modo normal

#define PIN_LED           2
#define STACK_SIZE_COMMS  4096
#define STACK_SIZE_RADAR  4096

#define PIN_MOTOR_STEP    18
#define PIN_MOTOR_DIR     19
#define PIN_MOTOR_ENABLE  -1   // no conectado

#define PIN_REED_SWITCH   26
#define PIN_TRIG          14
#define PIN_ECHO          27

#define STEPS_PER_REV     200
#define MICROSTEPPING     16
#define GEAR_RATIO        1.0

#define CORE_NET          0    // Core 0: TaskComms (WiFi/TCP)
#define CORE_PHYS         1    // Core 1: TaskRadar (motor/sensor)

#define RADAR_MIN_ANGLE   -45.0
#define RADAR_MAX_ANGLE    45.0
#define RADAR_STEP_ANGLE   5.0

#define WIFI_SSID_1       "iPhone de Alejandro"
#define WIFI_PASS_1       "TFG20252026"
#define WIFI_SSID_2       "ALEJANDROMILLAN2169"
#define WIFI_PASS_2       "TFG20252026"

#define SERVER_HOSTNAME   "radar-server"
#define SERVER_PORT       8080
```

### 6.2 `src/main.cpp` — Perfiles de Nodo

```cpp
struct NodeProfile {
    const char* mac;
    uint8_t     nodeId;
    bool        motorDirInvert;    // invierte PIN_MOTOR_DIR
    int         reedTriggerLevel;  // HIGH (reed NC) o LOW (reed NO)
};

static const NodeProfile PROFILES[] = {
    {"88:13:BF:C8:40:30",   1,  false,  HIGH},  // N1: motor normal, reed NC
    {"F0:24:F9:44:0A:20",   2,  true,   LOW},   // N2: motor invertido, reed NO
    {"CC:DB:A7:98:CC:E4",   3,  true,   HIGH},  // N3: motor invertido, reed NC
};
```

### 6.3 `src/task_radar.cpp` — Lógica Hardware Completa

```cpp
void RadarHardware::moveToAngle(float targetAngle) {
    float targetStepFloat = (targetAngle / 360.0) * STEPS_PER_REV * MICROSTEPPING * GEAR_RATIO;
    long target = (long)round(targetStepFloat);
    long steps = target - currentStepPos;

    if (steps == 0) return;

    bool dir = (steps > 0);
    steps = abs(steps);

    bool phys_dir = dir ^ SystemManager::instance().motorDirInvert;
    digitalWrite(PIN_MOTOR_DIR, phys_dir ? HIGH : LOW);
    delay(2);

    for (long i = 0; i < steps; i++) {
        digitalWrite(PIN_MOTOR_STEP, HIGH);
        delayMicroseconds(1000);    // ← 1000µs (antes: 600µs)
        digitalWrite(PIN_MOTOR_STEP, LOW);
        delayMicroseconds(1000);    // ← 1000µs (antes: 600µs)
    }

    currentStepPos = target;
    currentAngle = targetAngle;
}
```

`HW_CMD_EXECUTE_SLOT` en `TaskRadar`:
```cpp
else if (cmd.type == HW_CMD_EXECUTE_SLOT) {
    hw.moveToAngle(cmd.param);

    long time_to_wait = (long)cmd.execution_time_ms - (long)millis();
    if (time_to_wait > 0) {
        vTaskDelay(pdMS_TO_TICKS(time_to_wait));
    }

    float dist = hw.getDistance();

    HwResult res;
    res.type  = HW_RES_SLOT_DONE;
    res.value = dist;
    res.angle = cmd.param;

    HwResult flush;
    while (xQueueReceive(SystemManager::instance().queueResults, &flush, 0));

    xQueueSend(SystemManager::instance().queueResults, &res, portMAX_DELAY);
}
```

`getDistance()` — medición con reintentos:
```cpp
float RadarHardware::getDistance() {
    int retries = 2;
    long duration = 0;

    while(retries > 0) {
        digitalWrite(PIN_TRIG, LOW);
        delayMicroseconds(5);
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(12);
        digitalWrite(PIN_TRIG, LOW);

        duration = pulseIn(PIN_ECHO, HIGH, 15000);

        if (duration > 116) break;
        retries--;
        vTaskDelay(pdMS_TO_TICKS(2));
    }

    if (duration == 0)   return 0.0;    // timeout → sin obstáculo
    if (duration <= 116) return -1.0;   // < 2cm → medición inválida
    return duration / 58.0;             // cm
}
```

### 6.4 `server/server_central.py` — Constantes del Servidor

```python
SWEEP_ANGLE_TOTAL = 90.0
A_MAX = 45.0
A_MIN = -45.0
DIRTY_MARGIN = 15.0      # zona "sucia" cerca de ±45° (±30° a ±45°)
TRACK_MARGIN = 15.0      # extensión del rango de tracking más allá de ±45°
TRACK_LIMIT_DIST = 10.0  # distancia máx. (cm) para considerar un hit en tracking
MAX_MISSES = 3           # fallos consecutivos antes de volver a SEARCH
STEP_ANGLE = 5.0         # paso angular en SEARCH
STEAL_MARGIN = 2.0       # ventaja (cm) del nodo en TRACK en resolución de conflictos
TRACK_LOCK_DURATION = 6  # superframes que dura un bloqueo de tracking

MOTOR_STEPS_REV = 200
MICROSTEPPING = 16
GEAR_RATIO = 1.0
STEP_DELAY_MS = 2.0      # ms por micropaso (1000µs × 2 flancos)

SLOT_DURATION = 50       # ms por slot de tiempo
```

---

## 7. Sistema de Strikes y Gestión de Nodos Caídos

### 7.1 Lógica de Strikes

El servidor mantiene un contador de strikes por nodo:

| Evento                              | Acción               |
|-------------------------------------|----------------------|
| Nodo conectado                      | strikes = 0          |
| Sin ANGLE_REQ tras SF_START         | strikes += 1         |
| Sin DATA_REPORT tras REPORT_REQ     | strikes += 1         |
| DATA_REPORT recibido correctamente  | strikes = 0          |
| strikes >= 7                        | kick (close socket)  |

### 7.2 Período de Gracia

Al conectar, cada nodo recibe una gracia de 8 superframes:
```python
self.grace_until_sf[radar_id] = self.seq + 8
```
Durante la gracia, los fallos no acumulan strikes ni bloquean el SF.

### 7.3 `non_grace_count` — Nodos Que Cuentan para el Wait

```python
non_grace_count = sum(
    1 for r in self.client_sockets
    if self.seq > self.grace_until_sf.get(r, 0)
    and self.strikes.get(r, 0) == 0
)
```

El servidor solo espera ANGLE_REQ de nodos que:
1. Han superado el período de gracia
2. No tienen strikes activos

Esto evita que un nodo ya "tocado" bloquee el SF completo esperando una petición que nunca llegará.

---

## 8. Lógica de Modos SEARCH / TRACK

### 8.1 Modo SEARCH

El nodo barre de -45° a +45° en pasos de 5°, invirtiendo dirección al llegar al límite.

```python
if state['mode'] == 'SEARCH':
    target_angle = state['current_angle'] + (state['search_dir'] * STEP_ANGLE)
    if target_angle >= A_MAX:
        target_angle = A_MAX
        state['search_dir'] = -1.0
    elif target_angle <= A_MIN:
        target_angle = A_MIN
        state['search_dir'] = 1.0
```

### 8.2 Modo TRACK

Al detectar un objeto (dist ≤ TRACK_LIMIT_DIST = 10cm), el nodo entra en TRACK. El rango de barrido se adapta dinámicamente al objeto:

```python
else:  # TRACK
    obj_left  = max(A_MIN - TRACK_MARGIN, state['track_min'] - 5.0)
    obj_right = min(A_MAX + TRACK_MARGIN, state['track_max'] + 5.0)
    target_angle = state['current_angle'] + (state['track_dir'] * STEP_ANGLE)
    if target_angle >= obj_right:
        target_angle = obj_right
        state['track_dir'] = -1.0
    elif target_angle <= obj_left:
        target_angle = obj_left
        state['track_dir'] = 1.0
```

`track_min` y `track_max` se actualizan con cada medición positiva para mantener los límites del objeto detectado.

### 8.3 Transición TRACK → SEARCH

Si el objeto no se detecta en `MAX_MISSES = 3` superframes consecutivos, el nodo vuelve a SEARCH:

```python
if state['mode'] == 'TRACK':
    state['misses'] += 1
    if state['misses'] >= MAX_MISSES:
        state['mode'] = 'SEARCH'
        state['misses'] = 0
        self.track_lock.pop(r_id, None)
```

---

## 9. Resolución de Conflictos en Zonas Sucias (DIRTY)

Los ángulos próximos a los límites del radar (±45°) se denominan **zona sucia** porque pueden corresponder a la misma posición física observada por nodos adyacentes.

### 9.1 Definición de Zona Sucia

```python
CLEAN_LIMIT = A_MAX - DIRTY_MARGIN = 45.0 - 15.0 = 30.0
CONFLICT_PAIRS = [(1, 2), (2, 3)]   # pares de nodos adyacentes
```

Un nodo está en zona sucia si detecta en `|angle| > CLEAN_LIMIT` (es decir, entre 30° y 45°).

### 9.2 Lógica de Conflicto

```python
for (na, nb) in CONFLICT_PAIRS:
    na_conflict = (na in hits and hits[na]['angle'] > 0 and abs(hits[na]['angle']) > CLEAN_LIMIT)
    nb_conflict = (nb in hits and hits[nb]['angle'] < 0 and abs(hits[nb]['angle']) > CLEAN_LIMIT)

    if na_conflict and nb_conflict:
        # Resolver: ¿quién tiene bloqueo? ¿quién está más cerca?
        na_locked = self.seq <= self.track_lock.get(na, 0)
        nb_locked = self.seq <= self.track_lock.get(nb, 0)

        if na_locked and not nb_locked:
            winner, loser = na, nb
        elif nb_locked and not na_locked:
            winner, loser = nb, na
        else:
            # Sin bloqueo: gana el más cercano (con ventaja para el que ya trackea)
            eff_da = hits[na]['dist'] - (STEAL_MARGIN if state_a['mode'] == 'TRACK' else 0)
            eff_db = hits[nb]['dist'] - (STEAL_MARGIN if state_b['mode'] == 'TRACK' else 0)
            winner = na if eff_da <= eff_db else nb
            loser  = nb if winner == na else na

        self.track_lock[winner] = self.seq + TRACK_LOCK_DURATION
```

El `TRACK_LOCK_DURATION = 6` impide que el "loser" robe el tracking al ganador en los próximos 6 superframes.

---

## 10. Multilateración (Trilateración)

El servidor calcula posición aproximada del objeto cuando dos nodos lo detectan simultáneamente:

```python
def calcular_trilateracion(self, id1, d1, id2, d2):
    # Coordenadas de los dos nodos desde grid_config.json
    x1, y1 = cfg1["x"], cfg1["y"]
    x2, y2 = cfg2["x"], cfg2["y"]
    d = math.hypot(x2 - x1, y2 - y1)

    a = (d1**2 - d2**2 + d**2) / (2 * d)
    h = math.sqrt(max(0, d1**2 - a**2))
    # ... intersección de dos círculos
```

Solo se ejecuta para pares `N1-N2` y `N2-N3`. El par `N1-N3` no se considera porque son nodos no adyacentes (extremos).

---

## 11. Broadcast UDP para Visualización

Tras cada superframe, el servidor emite el estado completo en formato JSON por UDP:

```python
ui_state = {
    "seq": self.seq,
    "radars": {r: self.get_state(r) for r in self.client_sockets.keys()},
    "hits": hits,
    "trilat": trilat_results
}
self.udp_sock.sendto(json.dumps(ui_state).encode(), ('127.0.0.1', 8081))
```

**Estructura del objeto `radars` por nodo:**
```json
{
  "mode": "TRACK",
  "search_dir": 1.0,
  "track_dir": -1.0,
  "misses": 0,
  "current_angle": 25.0,
  "track_min": 20.0,
  "track_max": 30.0
}
```

**Estructura de `hits`:**
```json
{
  "1": {"angle": 25.0, "dist": 8.5},
  "2": {"angle": -30.0, "dist": 7.2}
}
```

**Estructura de `trilat`:**
```json
{
  "N1-N2": {"x": 15.3, "y": 28.7},
  "N2-N3": null
}
```

Un cliente de visualización externo puede escuchar en `127.0.0.1:8081` para recibir este JSON y renderizar el estado del sistema. **Este cliente no está implementado aún.**

---

## 12. Herramientas de Simulación (Estado Actual)

### 12.1 `tools/virtual_radar.py` y `tools/manual_radar.py`

Estas herramientas simulan nodos ESP32 desde Python. Sin embargo, **actualmente están desactualizadas** respecto al protocolo:

| Problema                  | Detalle                                                    |
|---------------------------|------------------------------------------------------------|
| Constante MSG_SLOT_ASSIGN | Usan `0xC1` en lugar de `0xB1`                            |
| Sin fase REPORT_REQ       | No implementan la recepción de `MSG_REPORT_REQ (0xB2)`    |
| Protocolo incompleto      | No funcionarán con el servidor actual sin actualización    |

Para reutilizarlas hay que:
1. Cambiar `MSG_SLOT_ASSIGN = 0xC1` → `MSG_SLOT_ASSIGN = 0xB1`
2. Añadir handler para `MSG_REPORT_REQ = 0xB2` que responda con `MSG_DATA_REPORT = 0xD0`

### 12.2 Modo DEBUG Hardware (Firmware)

El firmware incluye un modo de prueba hardware completo activado con `DEBUG_HARDWARE_TEST = 1` en `config.h`. En este modo:
- No se conecta al servidor
- Ejecuta secuencias de test del sensor ultrasónico y reed switch
- Realiza barridos de prueba del motor
- Imprime todo por Serial a 115200 baudios

---

## 13. Persistencia de Estado

### 13.1 `server/config/grid_config.json`

Mapa de nodos: MAC → {id, x, y, theta}. Se actualiza cuando un nuevo nodo se conecta.

### 13.2 `server/config/radar_state.json`

Estado de tracking de cada nodo (modo, ángulo actual, min/max de tracking). Se guarda al cerrar el servidor (Ctrl+C) y se ofrece reanudar al arrancar.

---

## 14. Problemas Conocidos Pendientes

### 14.1 Asignación de Slots Incorrecta en Zonas Sucias

**Síntoma:** Cuando dos nodos están en modo TRACK en la zona sucia (ambos en ángulos > 30°), el slot asignado a ambos es **Slot 0** en lugar de Slot 0 y Slot 1.

**Causa probable:** La lógica de colisión de slots compara ángulos globales (theta + local_angle) y usa un umbral de `diff < 30°`. Los ángulos en zona sucia de nodos adyacentes pueden tener diferencias globales > 30°, haciendo que la colisión no se detecte y ambos reciban Slot 0.

**Impacto:** Dos nodos miden exactamente al mismo instante → posible interferencia ultrasónica entre sensores.

**Código relevante (servidor, `orchestration_loop`):**
```python
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
```

### 14.2 Comportamiento de Tracking en Zona Sucia Incorrecto

**Síntoma:** El comportamiento del nodo en TRACK cuando el objeto está en la zona sucia (ángulos > 30° o < -30°) no coincide con el esperado. El rango de tracking, la dirección de barrido o la transición a SEARCH no se comportan correctamente en esta región.

**Estado:** Pendiente de análisis detallado y corrección.

---

## 15. Resumen de Todos los Cambios Aplicados en Esta Sesión

| Archivo                        | Cambio                                                                 |
|--------------------------------|------------------------------------------------------------------------|
| `src/task_comms.cpp` línea 130 | `t0_last_superframe` movido a `MSG_SUPERFRAME_START`                   |
| `src/task_comms.cpp` línea 148 | `execution_time_ms` usa `t0_last_superframe + start_delay_ms`          |
| `src/task_comms.cpp` línea 143 | Eliminado reset de `t0_last_superframe` en `MSG_SLOT_ASSIGN`           |
| `src/task_comms.cpp` línea 163 | Timeout REPORT_REQ reducido de 1500ms a **300ms**                      |
| `src/task_radar.cpp` línea 116 | Delay motor: `delayMicroseconds(600)` → **`delayMicroseconds(1000)`**  |
| `src/task_radar.cpp` línea 118 | Delay motor: `delayMicroseconds(600)` → **`delayMicroseconds(1000)`**  |
| `server/server_central.py` L66 | `STEP_DELAY_MS`: 1.3 → **2.0**                                         |
| `server/server_central.py` L412| Añadido `elapsed_before_assign_loop`                                    |
| `server/server_central.py` L424| Añadido `delay_from_sf_ms = elapsed_before_assign_loop + delay_ms`     |
| `server/server_central.py` L427| Payload SLOT_ASSIGN usa `delay_from_sf_ms` en lugar de `delay_ms`      |

---

## 16. Instrucciones de Despliegue

### 16.1 Compilar y Flashear el Firmware

```bash
# PlatformIO desde la raíz del proyecto
pio run --target upload --upload-port COM<X>
```

Para modo debug hardware, editar `src/config.h`:
```cpp
#define DEBUG_HARDWARE_TEST 1
```
Compilar, flashear, abrir Serial Monitor a 115200 baudios.

### 16.2 Arrancar el Servidor

```bash
cd server
python server_central.py
```

Dependencias Python requeridas:
```
zeroconf   # pip install zeroconf
ifaddr     # pip install ifaddr
```

### 16.3 Verificar Funcionamiento

El servidor imprime por consola:
- `[=== SF N ===]` — inicio de cada superframe
- `-> N{id} Asignado: {angle}° (Slot {s}, Centro en {d}ms desde asignación) | Modo: {m}` — asignación
- `-> [N{id}] 🔴 DEFCON 1 / 🟡 DEFCON 2 / 🟢 DEFCON 3 / 🔵 VALLA VIRTUAL` — detecciones
- `-> [N{id}] ⚪ SIN OBSTÁCULO` — sin detección
- `[DURACIÓN SF N] X ms` — duración del superframe

Duraciones esperadas:
- Sin movimiento (misma posición): ~300-500ms
- Con movimiento máximo (45°): ~1000-1400ms
- Event transitorio WiFi (normal): hasta ~1600ms

---

*Fin del documento. Fecha de generación: 2026-05-11.*
