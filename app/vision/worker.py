import logging
import queue
import threading
import time

from app.vision.detection_store import DetectionStore
from app.vision.face_db import FaceDB
from app.capture.frame_buffer import FrameBuffer

logger = logging.getLogger(__name__)


class VisionQueue:
    """
    Single inference thread — processes one frame at a time serially.
    Prevents multiple cameras from saturating all CPU cores in parallel.
    """

    def __init__(self, store: DetectionStore, face_db: FaceDB, models):
        self.store = store
        self.face_db = face_db
        self.models = models
        self._q: queue.Queue = queue.Queue(maxsize=5)  # bounded: drop if full
        self._thread = threading.Thread(target=self._run, daemon=True, name="vision-queue")

    def start(self) -> None:
        self._thread.start()
        logger.info("VisionQueue started")

    def submit(self, cam_id: str, frame) -> None:
        try:
            self._q.put_nowait((cam_id, frame))
        except queue.Full:
            pass  # drop frame — better than building a backlog

    def _run(self) -> None:
        while True:
            try:
                cam_id, frame = self._q.get(timeout=1.0)
                t0 = time.monotonic()
                result = self.models.process(frame, cam_id, self.face_db)
                self.store.update(result)
                logger.debug("inference cam=%s  %.0fms", cam_id, (time.monotonic()-t0)*1000)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.warning("VisionQueue error: %s", exc)


class VisionWorker(threading.Thread):
    """
    Lightweight per-camera thread — just grabs the latest frame and
    submits it to the shared VisionQueue at `fps` rate.
    """

    def __init__(
        self,
        cam_id: str,
        buffer: FrameBuffer,
        vision_queue: VisionQueue,
        fps: float = 0.5,
    ):
        super().__init__(daemon=True, name=f"vsrc-{cam_id}")
        self.cam_id = cam_id
        self.buffer = buffer
        self.vision_queue = vision_queue
        self.interval = 1.0 / max(fps, 0.05)
        self._stop = threading.Event()

    def run(self) -> None:
        logger.info("VisionWorker started — cam=%s  interval=%.1fs", self.cam_id, self.interval)
        while not self._stop.is_set():
            t0 = time.monotonic()
            frame = self.buffer.get_latest()
            if frame is not None:
                self.vision_queue.submit(self.cam_id, frame)
            elapsed = time.monotonic() - t0
            sleep = self.interval - elapsed
            if sleep > 0:
                self._stop.wait(sleep)

    def stop(self) -> None:
        self._stop.set()
