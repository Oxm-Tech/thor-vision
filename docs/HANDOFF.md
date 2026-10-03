# Guía de traspaso: THOR Vision

Para quien continúe el desarrollo. Complementa `README.md` (qué es), `INTEGRATION.md` (contrato de API y datos) y `CHANGELOG.md` (qué trae cada versión; el dashboard muestra la misma fuente en la barra inferior).

## 1. Qué hace, en una línea por etapa

1. **Captura** (`app/capture/`): un hilo RTSP por cámara con GStreamer + NVDEC (fallback FFmpeg), resolución nativa, buffer circular y *pre-roll* de 6 s en memoria. El movimiento lo informa la propia cámara por SUNAPI (Hanwha).
2. **Visión** (`app/vision/worker.py`, `app/pipeline/vision_processor.py`): YOLOv8s detecta personas y objetos (autos, motos, perros, bolsas…) y InsightFace los rostros, a 0.5 fps, 2 fps con movimiento y 4 fps buscando un rostro.
3. **Visitas e identidad** (`app/vision/visits.py`): cada persona seguida en una cámara es una visita; los rostros se agrupan en *sujetos*. Cada sujeto tiene una categoría: `revisar` (por defecto), `empleado` o `invitado`.
4. **Semántica** (`app/vision/vlm_worker.py`, `vlm_analyzer.py`, `scenes.py`): un modelo de visión-lenguaje (Qwen vía gateway) describe la escena con un prompt por cámara (`config/scenes.yml`) y su resultado se valida y sanea. Alertas, horarios, mascotas y personas conocidas se definen ahí.
5. **Almacenamiento** (`app/storage/`): SQLite `data/events.db` más JPEG en disco; retención automática (`rotate()`).
6. **Salida**: FastAPI (dashboard, API, WebSocket) y el **Vision Agent** (Morphic auto-hospedado) que consulta esos mismos datos con DeepSeek.

## 2. Dónde vive cada cosa

| Pieza | Dónde |
|---|---|
| Código de thor-vision | `app/` (en el servidor se monta de solo lectura; un cambio de código se aplica con `docker restart thor-vision`) |
| Configuración de cámaras | `config/cameras.yml` (**secreto**, nunca al repo; plantilla en `cameras.example.yml`) |
| Prompts por cámara y reglas de alerta | `config/scenes.yml` |
| Skills de IA editables | `config/skills/report.md` y `chat.md` (se leen en cada uso, sin reiniciar) |
| Variables de entorno | `docker-compose.yml` real (**secreto**: trae llaves); plantilla en `docker-compose.example.yml` |
| Datos | `data/` (base, capturas, recortes de mascotas); nunca al repo |
| Vision Agent | repo `miurla/morphic` con un parche propio de THOR (identidad, español, búsqueda contra `/searxng/search`, filtro de tokens de DeepSeek); puerto 3200 |
| Notas de cada release | `app/release_notes.json` y `app/version.py` |

## 3. Operación

- **Reinicio**: `docker restart thor-vision`. Las 10 cámaras tardan 100 a 150 s en volver a `live`; comprobar con `GET /api/health`. Un cambio en `docker-compose.yml` exige `docker compose up -d`.
- **Gateway de modelos**: puede responder `503 capacity busy` en horario laboral. Los análisis reintentan; los entrenamientos y trabajos largos deben correr de madrugada.
- **Cámaras**: movimiento por `SUNAPI eventstatus`; snapshot por `video.cgi` (falla en las de 5 MP). Los rótulos de nombre, fecha y hora se graban en la imagen de la propia cámara.
- **Datos biométricos**: rostros y cuerpos de personas sin nombre caducan a 30 días, invitados a 90, empleados nunca. No exportarlos ni subirlos a servicios externos.
- **Comprobaciones antes de subir**: `ruff check app --select F,E9` (un nombre sin definir en una rama poco usada falla en silencio; `py_compile` no lo detecta) y revisar que no queden llaves ni IPs en el diff. El CI y gitleaks lo repiten.

## 4. Convenciones

- Cada cambio de código deja un respaldo `*.bak-<etiqueta>-<fecha>` antes de editar en el servidor, y se sincroniza al repo en una rama propia con PR.
- Las funciones nuevas llevan interruptor por variable de entorno cuando afectan el flujo en vivo (por ejemplo `YOLO_OBJECTS_ENABLED`, `PARKED_CAMS`, `PET_COLLECT`).
- Los tipos guardados en la base conservan sus nombres históricos (`type="nemotron"`) por compatibilidad; renombrarlos requiere una migración.
- Una falla del modelo nunca debe puntuarse como cero en un benchmark: se reintenta o se aborta.

## 5. Estado actual y qué sigue

El estado de cada línea de trabajo y su criterio de aceptación están en [`ROADMAP.md`](ROADMAP.md). Lo inmediato es el videoportero, la consolidación de personas duplicadas y el reporte de asistencia.

## Calidad y CI (fiabilidad)

El CI (`.github/workflows/ci.yml`) corre cuatro cosas, todas reproducibles en local:

- **Pruebas de contrato** (`tests/`, `pip install -r requirements-dev.txt && pytest -q tests`): cubren lo que ya fallo en produccion (saneador del VLM, ventana de historia del chat, emparejamiento de vehiculos, fusion de huecos de asistencia, geometria de visitas). Cada falla real nueva deberia dejar su prueba.
- **Trinquete de excepciones** (`scripts/ruff_ratchet.py`, base en `.ci/ruff-baseline.json`): los `except` genericos o silenciosos esconden fallos; la deuda actual esta fijada y solo puede bajar. Tras limpiar algunos: `python scripts/ruff_ratchet.py --update`.
- **Reglas ast-grep** (`rules/`, `ast-grep scan`): llamadas HTTP sin `timeout` y consumidores de `get_recent_frames()` sin tope propio (causa de la recaida de `context_length_exceeded`).
- Ruff (`F,E9`), plantillas Jinja y gitleaks, como antes.

## Versionado y releases (automático)

- **Fuente única:** `app/release_notes.json`. De ahí salen `app/version.py` (la versión), el CHANGELOG y las notas que muestra el dashboard.
- **Para sacar una versión:** agregar la entrada al inicio de `release_notes.json`, correr `python scripts/release.py write` (regenera `CHANGELOG.md`), abrir el PR y, al fusionar, crear el tag `vX.Y.Z`.
- El CI falla si el CHANGELOG está desfasado; al subir el tag, `.github/workflows/release.yml` verifica que coincida con la versión y publica el GitHub Release con esas notas.
- **Commit desplegado:** antes de copiar `app/` a Thor, `python scripts/stamp_build.py` escribe `app/build_info.json` (ignorado por git); `/api/version` lo devuelve y el pie del dashboard lo muestra al pasar el cursor sobre la versión.
- Gobierno con Jira y COBIT: `docs/COBIT-JIRA.md`. Evaluación de JetPack: `docs/JETPACK-7.2.1.md`.
