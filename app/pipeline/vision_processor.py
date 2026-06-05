import logging
import os
import time
from typing import Optional

import cv2
import numpy as np

from app.vision.detection_store import CameraDetection, FaceDetection
from app.vision.face_db import FaceDB

logger = logging.getLogger(__name__)

_INFER_THREADS = int(os.environ.get("INFER_THREADS", "4"))


def _apply_thread_limits() -> None:
    try:
        import torch
        torch.set_num_threads(_INFER_THREADS)
        logger.info("torch threads → %d", _INFER_THREADS)
    except ImportError:
        pass
    try:
        cv2.setNumThreads(_INFER_THREADS)
    except Exception:
        pass


class VisionModels:
    def __init__(self, device: str = "cpu", yolo_conf: float = 0.25):
        self.device = device
        self.yolo_conf = yolo_conf
        self._yolo = None
        self._face_app = None

    def setup(self) -> None:
        _apply_thread_limits()
        self._load_yolo()
        self._load_insightface()

    def _load_yolo(self) -> None:
        try:
            from ultralytics import YOLO
            self._yolo = YOLO("yolov8s.pt")   # yolov8s: +15% precisión vs nano
            dummy = np.zeros((64, 64, 3), dtype=np.uint8)
            self._yolo(dummy, verbose=False, imgsz=640)
            logger.info("YOLOv8s loaded (device=%s, imgsz=640, conf=%.2f, threads=%d)",
                        self.device, self.yolo_conf, _INFER_THREADS)
        except Exception as exc:
            logger.error("YOLO load failed: %s", exc)

    def _load_insightface(self) -> None:
        try:
            from insightface.app import FaceAnalysis
            self._face_app = FaceAnalysis(
                name="buffalo_sc",
                providers=["CPUExecutionProvider"],
            )
            self._face_app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace buffalo_sc loaded (det_size=640)")
        except Exception as exc:
            logger.warning("InsightFace load failed: %s", exc)

    def process(self, frame: np.ndarray, cam_id: str, face_db: FaceDB) -> CameraDetection:
        t0 = time.monotonic()
        person_bboxes = self._detect_persons(frame)
        faces = self._detect_faces(frame, face_db)
        return CameraDetection(
            cam_id=cam_id,
            person_count=len(person_bboxes),
            person_bboxes=person_bboxes,
            faces=faces,
            updated_at=time.time(),
            inference_ms=(time.monotonic() - t0) * 1000,
        )

    def _detect_persons(self, frame: np.ndarray) -> list:
        if self._yolo is None:
            return []
        try:
            results = self._yolo(
                frame,
                classes=[0],          # class 0 = person
                conf=self.yolo_conf,
                imgsz=640,
                verbose=False,
                device=self.device,
            )
            bboxes = []
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    bboxes.append((x1, y1, x2, y2))
            return bboxes
        except Exception as exc:
            logger.debug("YOLO error: %s", exc)
            return []

    def _detect_faces(self, frame: np.ndarray, face_db: FaceDB) -> list:
        if self._face_app is None:
            return []
        try:
            detected = self._face_app.get(frame)
            faces = []
            for face in detected:
                bbox = tuple(map(int, face.bbox.tolist()))
                name, conf = face_db.recognize(face.embedding)
                faces.append(FaceDetection(bbox=bbox, name=name, confidence=conf))
            return faces
        except Exception as exc:
            logger.debug("InsightFace error: %s", exc)
            return []

    def extract_embedding(self, frame: np.ndarray) -> Optional[np.ndarray]:
        if self._face_app is None:
            return None
        try:
            detected = self._face_app.get(frame)
            if not detected:
                return None
            best = max(detected, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
            return best.embedding
        except Exception as exc:
            logger.debug("Embedding error: %s", exc)
            return None

    def teardown(self) -> None:
        self._yolo = None
        self._face_app = None
