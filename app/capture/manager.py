import logging
import time
from typing import Dict, Optional

import numpy as np

from app.capture.frame_buffer import FrameBuffer
from app.capture.rtsp_reader import RTSPReader, CameraState
from app.config import AppConfig

logger = logging.getLogger(__name__)


class CaptureManager:
    """Orquesta todos los RTSPReaders. Una instancia global por app."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._readers: Dict[str, RTSPReader] = {}
        self._buffers: Dict[str, FrameBuffer] = {}
        self._start_time = time.time()

    def start(self) -> None:
        for cam in self.config.enabled_cameras:
            buf = FrameBuffer(maxlen=self.config.global_cfg.buffer_size)
            reader = RTSPReader(cam, self.config.global_cfg, buf)
            self._buffers[cam.id] = buf
            self._readers[cam.id] = reader
            reader.start()
            logger.info("Started reader for camera: %s", cam.id)

        logger.info("CaptureManager started — %d cameras", len(self._readers))

    def stop(self) -> None:
        for reader in self._readers.values():
            reader.stop()
        for reader in self._readers.values():
            reader.join(timeout=5.0)
        logger.info("CaptureManager stopped")

    def get_frame(self, cam_id: str) -> Optional[np.ndarray]:
        buf = self._buffers.get(cam_id)
        if buf is None:
            return None
        return buf.get_latest()

    def get_state(self, cam_id: str) -> str:
        reader = self._readers.get(cam_id)
        if reader is None:
            return CameraState.DISABLED.value
        return reader.state.value

    def get_camera_stats(self, cam_id: str) -> dict:
        reader = self._readers.get(cam_id)
        if reader is None:
            return {"id": cam_id, "state": "disabled"}
        return reader.stats()

    def get_all_stats(self) -> list:
        return [r.stats() for r in self._readers.values()]

    def summary(self) -> dict:
        stats = self.get_all_stats()
        live = sum(1 for s in stats if s["state"] == "streaming")
        reconnecting = sum(1 for s in stats if s["state"] == "reconnecting")
        return {
            "total": len(stats),
            "live": live,
            "reconnecting": reconnecting,
            "offline": len(stats) - live - reconnecting,
            "uptime_s": int(time.time() - self._start_time),
        }
