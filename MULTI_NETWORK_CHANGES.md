# Cambios necesarios para soporte multi-red

## Objetivo
Permitir que los nodos ESP32 se conecten al servidor en cualquier entorno (casa, universidad, Mac, Windows) sin reflashear el firmware.

## Arquitectura propuesta

```
[ESP32 x3] --WiFi--> [Red compartida] <---> [Servidor Python]
```

La red compartida puede ser:
- Hotspot del PC (Windows/Mac)
- Router WiFi (casa, universidad)
- Hotspot del móvil (iPhone/Android)

---

## Cambio 1 — WiFiMulti en ESP32 (src/main.cpp + src/config.h)

Permite guardar múltiples redes y conectarse a la disponible.

### config.h
```cpp
// Reemplazar:
#define WIFI_SSID  "nombre"
#define WIFI_PASS  "pass"

// Por:
#define WIFI_SSID_1  "iPhone de Alejandro"   // hotspot móvil
#define WIFI_PASS_1  "TFG20252026"
#define WIFI_SSID_2  "ALEJANDROMILLAN2169"   // hotspot PC
#define WIFI_PASS_2  "TFG20252026"
// Añadir más si hace falta
```

### main.cpp
```cpp
#include <WiFiMulti.h>
WiFiMulti wifiMulti;

// En setup(), ANTES de wifiMulti.run():
SystemManager::instance().changeState(WAITING_FOR_CONNECTION);  // CRÍTICO: debe ir antes
wifiMulti.addAP(WIFI_SSID_1, WIFI_PASS_1);
if (strlen(WIFI_SSID_2) > 0) wifiMulti.addAP(WIFI_SSID_2, WIFI_PASS_2);
wifiMulti.run(10000);

// En WiFiEvent DISCONNECTED, reemplazar WiFi.reconnect() por:
wifiMulti.run(5000);
```

### Problema conocido
`wifiMulti.run()` puede tardar varios segundos en escanear. Si el estado `WAITING_FOR_CONNECTION` no está seteado antes de llamar a `run()`, el evento `GOT_IP` no transiciona a `SYNC_CONTROL` y el LED queda parpadeando indefinidamente aunque haya WiFi.

---

## Cambio 2 — Descubrimiento del servidor por mDNS

Elimina la dependencia de una IP fija en el firmware.

### config.h
```cpp
// Reemplazar:
#define SERVER_IP  "192.168.137.1"

// Por:
#define SERVER_HOSTNAME  "radar-server"
```

### task_comms.cpp
```cpp
#include <ESPmDNS.h>

bool connectToServer() {
    WiFi.setSleep(false);
    IPAddress serverIP;

    // 1. Intentar mDNS
    for (int i = 0; i < 5; i++) {
        serverIP = MDNS.queryHost(SERVER_HOSTNAME);
        if (serverIP != IPAddress(0,0,0,0)) break;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

    // 2. Fallback: si mDNS devuelve 0, probar gateway (= servidor en hotspot)
    if (serverIP == IPAddress(0,0,0,0))
        serverIP = WiFi.gatewayIP();

    if (!client.connect(serverIP, SERVER_PORT)) {
        // 3. Fallback: si mDNS devolvió IP pero no conecta, probar gateway
        IPAddress gw = WiFi.gatewayIP();
        if (gw != serverIP) client.connect(gw, SERVER_PORT);
    }
    // ...
}
```

### main.cpp — iniciar mDNS tras conectar
```cpp
case ARDUINO_EVENT_WIFI_STA_GOT_IP:
    MDNS.begin("esp-radar");
    // ...
```

### server_central.py — anunciar hostname
```python
pip install zeroconf

from zeroconf import Zeroconf, ServiceInfo
# Registrar radar-server.local con TODAS las IPs locales
# (excluir 127.x.x.x y 169.254.x.x)
zc_info = ServiceInfo(
    "_radar._tcp.local.",
    "radar-server._radar._tcp.local.",
    addresses=[inet_aton(ip) for ip in local_ips],
    port=PORT,
    server="radar-server.local."
)
zc.register_service(zc_info)
```

### Problema conocido en Windows con múltiples interfaces
Windows genera adaptadores virtuales con IPs `169.254.x.x` (Hyper-V, VirtualBox, etc.).
El ESP32 puede recibir una de esas IPs vía mDNS y fallar al conectar.
**Solución**: filtrar `169.254.x.x` al registrar en zeroconf.

---

## Cambio 3 — LED refleja estado del sistema

| Estado              | Patrón LED        |
|---------------------|-------------------|
| Sin WiFi            | Parpadeo rápido (250ms) |
| WiFi OK, sin servidor | Parpadeo lento (1000ms) |
| Operativo           | Fijo encendido    |

---

## Resumen de dependencias adicionales

| Componente | Librería necesaria |
|---|---|
| ESP32 | `ESPmDNS` (incluida en Arduino ESP32) |
| ESP32 | `WiFiMulti` (incluida en Arduino ESP32) |
| Servidor Python | `pip install zeroconf` |

---

## Configuración de red por escenario

### Hotspot Windows
- Hotspot activo con SSID y contraseña que coincidan con config.h
- Banda: 2.4 GHz obligatorio
- Servidor anuncia en 192.168.137.1

### Hotspot Mac (requiere Ethernet o tethering USB)
- System Settings → Sharing → Internet Sharing
- Nombre red = SSID en config.h
- Servidor anuncia en IP asignada por Mac

### Hotspot iPhone
- Ajustes → General → Información → Nombre = SSID en config.h
- Personal Hotspot → Contraseña = PASS en config.h
- Máxima Compatibilidad ON (fuerza 2.4 GHz)

### Router WiFi (más genérico)
- Todos en la misma red
- mDNS funciona directamente
- No requiere hotspot
