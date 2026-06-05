# THOR Vision

Sistema de vigilancia inteligente con análisis de escena en tiempo real usando **Nemotron** (LLM multimodal) corriendo en un **DGX Spark** remoto.

Corre sobre **Jetson NVIDIA** con Docker.

---

## ¿Qué hace?

- Captura streams RTSP de múltiples cámaras IP simultáneamente
- Analiza escenas con Nemotron (motion-gated: solo llama al LLM cuando hay movimiento)
- Dashboard web en tiempo real: grid de cámaras, estado, snapshots
- Chat IA: pregunta sobre lo que ven las cámaras en lenguaje natural
- Persistencia en SQLite: eventos, snapshots y conversaciones
- Retención automática configurable

## Arquitectura

```
Cámaras IP (RTSP)
      │
      ▼
 CaptureManager          ← un thread por cámara
      │
      ├──► FrameBuffer   ← buffer circular en memoria
      │
      ▼
 NemotronWorker          ← motion detection → análisis LLM
      │
      ├──► DetectionStore  ← estado en vivo (memoria)
      ├──► EventDB         ← persistencia SQLite
      └──► SnapshotManager ← JPGs en disco
      │
      ▼
 FastAPI :8080
      ├── /              → Dashboard (grid + chat)
      ├── /api/stream/{cam_id}  → MJPEG stream
      ├── /api/status    → estado de cámaras
      ├── /api/chat      → chat con Nemotron sobre las cámaras
      ├── /api/events    → historial de eventos
      ├── /api/snapshots → galería de snapshots
      └── /ws/detections → WebSocket tiempo real
```

## Requisitos

- Jetson NVIDIA (Orin / Thor o compatible) con JetPack 6.x
- Docker + NVIDIA Container Toolkit
- Acceso a un servidor con Nemotron corriendo en `/v1/chat/completions`
- Cámaras IP con stream RTSP

## Setup

### 1. Clonar y configurar

```bash
git clone https://github.com/Oxm-Tech/thor-vision.git
cd thor-vision
```

### 2. Configurar cámaras

```bash
cp config/cameras.example.yml config/cameras.yml
# Editar con las URLs RTSP y credenciales de tus cámaras
nano config/cameras.yml
```

### 3. Configurar settings

```bash
cp config/settings.example.yml config/settings.yml
# Ajustar si es necesario (puerto, resolución, etc.)
```

### 4. Configurar docker-compose

```bash
cp docker-compose.example.yml docker-compose.yml
# Editar la IP del servidor Nemotron
nano docker-compose.yml
```

### 5. Crear carpeta de datos

```bash
mkdir -p data/snapshots data/logs data/metadata
```

### 6. Levantar

```bash
make build
make up
```

Acceder en: `http://<IP_JETSON>:8080`

---

## Comandos disponibles (Makefile)

| Comando | Descripción |
|---|---|
| `make up` | Levantar en background |
| `make dev` | Levantar con logs en consola |
| `make down` | Detener |
| `make logs` | Ver logs en tiempo real |
| `make build` | Rebuildar imagen |
| `make status` | Estado del servicio + health check |
| `make cameras` | Ver estado de cámaras vía API |
| `make reload` | Reiniciar sin rebuildar |
| `make clean` | Eliminar contenedor e imagen |

---

## Variables de entorno principales

| Variable | Default | Descripción |
|---|---|---|
| `NEMOTRON_ENDPOINT` | — | URL del servidor LLM (requerido) |
| `NEMOTRON_MODEL` | `nemotron-omni` | Modelo a usar |
| `NEMOTRON_MIN_INTERVAL_S` | `30` | Cooldown mínimo entre análisis por cámara |
| `NEMOTRON_MAX_INTERVAL_S` | `120` | Heartbeat máximo sin movimiento |
| `NEMOTRON_MOTION_THRESHOLD` | `0.04` | Fracción de píxeles para disparar análisis |
| `SNAPSHOT_PERIODIC_S` | `600` | Snapshot programado cada N segundos |
| `RETENTION_MAX_EVENTS` | `200000` | Máximo de eventos en SQLite |
| `RETENTION_MAX_SNAPSHOT_GB` | `50` | Máximo de GB de snapshots en disco |
| `RETENTION_MAX_AGE_DAYS` | `30` | Días máximos de retención de snapshots |
| `LOG_LEVEL` | `INFO` | Nivel de logging |

---

## Estructura del proyecto

```
thor-vision/
├── app/
│   ├── main.py                  ← FastAPI app + lifespan
│   ├── config.py                ← carga cameras.yml + settings.yml
│   ├── api/
│   │   ├── routes_chat.py       ← POST /api/chat (Nemotron)
│   │   ├── routes_history.py    ← GET /api/events, /api/snapshots
│   │   ├── routes_status.py     ← GET /api/status, /api/cameras
│   │   ├── routes_stream.py     ← GET /api/stream/{cam_id} (MJPEG)
│   │   ├── routes_vision.py     ← GET /api/detections
│   │   └── routes_ws.py         ← WS /ws/detections
│   ├── capture/
│   │   ├── manager.py           ← gestiona todos los RTSPReaders
│   │   ├── rtsp_reader.py       ← thread de captura por cámara
│   │   └── frame_buffer.py      ← buffer circular de frames
│   ├── vision/
│   │   ├── nemotron_worker.py   ← motion detection + análisis LLM
│   │   ├── nemotron_analyzer.py ← cliente HTTP a Nemotron
│   │   ├── detection_store.py   ← estado en vivo de todas las cámaras
│   │   ├── face_db.py           ← base de datos de rostros conocidos
│   │   └── worker.py            ← worker genérico
│   ├── storage/
│   │   ├── db.py                ← EventDB (SQLite WAL)
│   │   ├── snapshot_manager.py  ← guarda JPGs en disco
│   │   └── retention.py         ← hilo de retención automática
│   ├── pipeline/
│   │   ├── vision_processor.py  ← procesador de visión
│   │   ├── passthrough.py       ← modo passthrough (sin inferencia)
│   │   └── base_processor.py    ← clase base
│   ├── utils/
│   │   ├── logger.py            ← configuración de logging
│   │   └── gpu_probe.py         ← detecta GPU disponible
│   └── dashboard/
│       └── templates/
│           └── index.html       ← SPA del dashboard
├── config/
│   ├── cameras.example.yml      ← plantilla de cámaras
│   └── settings.example.yml     ← plantilla de settings
├── scripts/
│   └── check_cameras.sh         ← verifica conectividad de cámaras
├── Dockerfile
├── docker-compose.example.yml
├── requirements.txt
├── Makefile
└── .env.example
```

---

## Persistencia

Los datos se guardan en `./data/` (montado en `/app/data` dentro del contenedor):

```
data/
├── events.db          ← SQLite WAL (eventos Nemotron + chat + snapshots index)
├── snapshots/
│   └── cam-01/
│       └── 20260605/
│           ├── 143022_alert.jpg
│           ├── 143100_periodic.jpg
│           └── 143242_people_change.jpg
├── logs/
└── metadata/
    └── faces.json     ← base de datos de rostros conocidos
```

---

Desarrollado por **OXM Tech** — [oxmtech.com](https://oxmtech.com)
