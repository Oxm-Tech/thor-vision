import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from app.config import load_config
from app.capture.manager import CaptureManager
from app.api.routes_stream  import router as stream_router
from app.api.routes_status  import router as status_router
from app.api.routes_ws      import router as ws_router
from app.api.routes_vision  import router as vision_router
from app.api.routes_chat    import router as chat_router
from app.api.routes_history import router as history_router
from app.utils.logger import setup_logging

setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("THOR Vision starting...")
    config  = load_config()
    manager = CaptureManager(config)
    manager.start()

    app.state.config          = config
    app.state.capture_manager = manager

    # ── DetectionStore — compartido por YOLO y Nemotron ──────────────────
    from app.vision.detection_store import DetectionStore
    detection_store = DetectionStore()
    app.state.detection_store = detection_store

    # ── Persistencia: SQLite + snapshots ──────────────────────────────────
    from app.storage import EventDB, SnapshotManager, start_retention_thread

    db = EventDB("/app/data/events.db")
    app.state.db = db

    snapshots = SnapshotManager(
        base_path   = "/app/data/snapshots",
        db          = db,
        frame_width = config.global_cfg.frame_width,
    )
    app.state.snapshots = snapshots

    retention_stop = start_retention_thread(
        db=db, snapshots=snapshots,
        interval_s        = float(os.environ.get("RETENTION_INTERVAL_S",      "3600")),
        max_events        = int(  os.environ.get("RETENTION_MAX_EVENTS",      "200000")),
        max_snapshot_bytes= int(  os.environ.get("RETENTION_MAX_SNAPSHOT_GB", "50")) * 1024**3,
        max_age_days      = int(  os.environ.get("RETENTION_MAX_AGE_DAYS",    "30")),
    )
    app.state.retention_stop = retention_stop

    # ── YOLO + InsightFace — bboxes rápidos (paralelo a Nemotron) ─────────
    from app.vision.face_db            import FaceDB
    from app.pipeline.vision_processor import VisionModels
    from app.vision.worker             import VisionQueue, VisionWorker

    face_db = FaceDB(
        db_path                = "/app/data/metadata/faces.json",
        recognition_threshold  = 0.40,
    )
    vision_models = VisionModels(device="cuda:0", yolo_conf=0.25)
    vision_models.setup()

    vision_queue = VisionQueue(
        store    = detection_store,
        face_db  = face_db,
        models   = vision_models,
    )
    vision_queue.start()

    app.state.face_db       = face_db
    app.state.vision_models = vision_models

    yolo_workers = []
    for cam in config.enabled_cameras:
        buf = manager._buffers.get(cam.id)
        if buf is not None:
            w = VisionWorker(
                cam_id       = cam.id,
                buffer       = buf,
                vision_queue = vision_queue,
                fps          = 0.5,
            )
            w.start()
            yolo_workers.append(w)

    app.state.yolo_workers = yolo_workers
    logger.info("YOLO pipeline: %d workers, 1 serial queue", len(yolo_workers))

    # ── Nemotron workers — análisis semántico motion-gated ────────────────
    from app.vision.nemotron_analyzer import NemotronAnalyzer
    from app.vision.nemotron_worker   import NemotronWorker

    nemotron_endpoint = os.environ.get("NEMOTRON_ENDPOINT",  "http://192.168.0.200:8003")
    nemotron_model    = os.environ.get("NEMOTRON_MODEL",     "nemotron-omni")
    nemotron_min_s    = float(os.environ.get("NEMOTRON_MIN_INTERVAL_S",   "30"))
    nemotron_max_s    = float(os.environ.get("NEMOTRON_MAX_INTERVAL_S",  "120"))
    nemotron_motion   = float(os.environ.get("NEMOTRON_MOTION_THRESHOLD", "0.04"))
    snapshot_periodic = float(os.environ.get("SNAPSHOT_PERIODIC_S",       "600"))

    analyzer = NemotronAnalyzer(
        endpoint   = nemotron_endpoint,
        model      = nemotron_model,
        max_tokens = 150,
        timeout    = 20,
    )
    app.state.nemotron_analyzer = analyzer

    nemotron_workers = []
    for cam in config.enabled_cameras:
        buf = manager._buffers.get(cam.id)
        if buf is not None:
            nw = NemotronWorker(
                cam_id              = cam.id,
                buffer              = buf,
                store               = detection_store,
                analyzer            = analyzer,
                min_interval_s      = nemotron_min_s,
                max_interval_s      = nemotron_max_s,
                motion_threshold    = nemotron_motion,
                db                  = db,
                snapshots           = snapshots,
                snapshot_periodic_s = snapshot_periodic,
            )
            nw.start()
            nemotron_workers.append(nw)

    app.state.nemotron_workers = nemotron_workers

    logger.info(
        "Started — %d cams | YOLO 0.5fps | Nemotron motion-gated min=%.0fs max=%.0fs | endpoint=%s",
        len(config.enabled_cameras),
        nemotron_min_s, nemotron_max_s, nemotron_endpoint,
    )
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("THOR Vision shutting down...")
    retention_stop.set()
    for w in yolo_workers:
        w.stop()
    for nw in nemotron_workers:
        nw.stop()
    manager.stop()
    vision_models.teardown()
    db.close()


app = FastAPI(title="THOR Vision", lifespan=lifespan)

app.include_router(stream_router)
app.include_router(status_router)
app.include_router(ws_router)
app.include_router(vision_router)
app.include_router(chat_router)
app.include_router(history_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
