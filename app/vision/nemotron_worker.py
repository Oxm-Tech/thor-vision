import logging
import random
import threading
import time
from typing import Optional

import cv2
import numpy as np

from app.capture.frame_buffer     import FrameBuffer
from app.vision.detection_store   import DetectionStore
from app.vision.nemotron_analyzer import NemotronAnalyzer

logger = logging.getLogger(__name__)

# Set de "alerts" sintéticos del propio analyzer cuando algo falla
# — no son alertas reales, no deben disparar snapshots
_FAKE_ALERTS = {"error", "empty response", "bad json", "encode failed",
                "unreachable", ""}


class NemotronWorker(threading.Thread):
    """
    Worker por cámara con disparo por movimiento.

    Estrategia para no quemar la GPU del DGX Spark:
    - Cada `check_interval_s` segundos, compara el frame actual contra el
      anterior (diferencia absoluta en escala de grises, sub-muestreada).
    - Solo llama a Nemotron si:
        a) Hay movimiento significativo, Y han pasado >= min_interval_s
        b) O han pasado >= max_interval_s desde el último análisis (heartbeat)
    - Resultado: escenas estáticas casi no consumen GPU, escenas con
      actividad se actualizan ágilmente.
    """

    def __init__(
        self,
        cam_id: str,
        buffer: FrameBuffer,
        store: DetectionStore,
        analyzer: NemotronAnalyzer,
        min_interval_s:      float = 30.0,
        max_interval_s:      float = 120.0,
        motion_threshold:    float = 0.04,
        check_interval_s:    float = 2.0,
        db                         = None,        # EventDB | None
        snapshots                  = None,        # SnapshotManager | None
        snapshot_periodic_s: float = 600.0,
    ):
        super().__init__(daemon=True, name=f"nemotron-{cam_id}")
        self.cam_id              = cam_id
        self.buffer              = buffer
        self.store               = store
        self.analyzer            = analyzer
        self.min_interval_s      = min_interval_s
        self.max_interval_s      = max_interval_s
        self.motion_threshold    = motion_threshold
        self.check_interval_s    = check_interval_s
        self.db                  = db
        self.snapshots           = snapshots
        self.snapshot_periodic_s = snapshot_periodic_s

        self._stop             = threading.Event()
        self._prev_gray        = None
        self._last_analysis_t  = 0.0
        self._last_people      = 0
        self._last_periodic_t  = 0.0

    # ── Motion ────────────────────────────────────────────────────────────

    def _compute_motion(self, frame: np.ndarray) -> float:
        """
        Fracción de píxeles con cambio significativo respecto al frame previo.
        Sub-muestrea a 160x90 para que esto cueste casi nada (~0.5ms).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
        if self._prev_gray is None:
            self._prev_gray = gray
            return 0.0
        diff = cv2.absdiff(gray, self._prev_gray)
        self._prev_gray = gray
        return float((diff > 25).mean())

    # ── Run loop ──────────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info(
            "NemotronWorker started — cam=%s min=%.0fs max=%.0fs thr=%.3f",
            self.cam_id, self.min_interval_s, self.max_interval_s, self.motion_threshold
        )
        # Stagger inicial para no saturar la GPU con 10 cámaras a la vez
        self._stop.wait(random.uniform(0, min(self.max_interval_s, 15)))

        while not self._stop.is_set():
            frame = self.buffer.get_latest()
            if frame is None:
                self._stop.wait(self.check_interval_s)
                continue

            now     = time.monotonic()
            elapsed = now - self._last_analysis_t

            should_analyze = False
            reason         = ""

            # Heartbeat: siempre analizar si pasó demasiado tiempo
            if elapsed >= self.max_interval_s:
                should_analyze = True
                reason         = "heartbeat"
            # Motion-triggered: solo si pasó el mínimo intervalo
            elif elapsed >= self.min_interval_s:
                motion = self._compute_motion(frame)
                if motion >= self.motion_threshold:
                    should_analyze = True
                    reason         = f"motion={motion:.3f}"
            else:
                # En cooldown — actualizar baseline igualmente para que
                # cuando salgamos del cooldown, motion se mida bien.
                self._compute_motion(frame)

            if should_analyze:
                detection = self.store.get(self.cam_id)
                context = None
                if detection:
                    context = {
                        "person_count": detection.person_count,
                        "faces": [
                            {"name": f.name, "confidence": round(f.confidence, 2)}
                            for f in detection.faces
                        ],
                    }
                result = self.analyzer.analyze(frame, context)
                self.store.update_nemotron(self.cam_id, result)
                self._last_analysis_t = now

                people    = result.get("people") if isinstance(result.get("people"), int) else 0
                has_alert = self._has_real_alert(result)

                # ── Persistir evento ─────────────────────────────────────
                event_id: Optional[int] = None
                if self.db is not None and result.get("activity") != "error":
                    try:
                        # Adjuntar el trigger del análisis (heartbeat/motion=...)
                        payload = dict(result)
                        payload["_trigger"] = reason
                        event_id = self.db.insert_event(
                            type      = "nemotron",
                            cam_id    = self.cam_id,
                            payload   = payload,
                            people    = max(people, 0),
                            has_alert = has_alert,
                        )
                    except Exception as e:
                        logger.warning("DB insert error cam=%s: %s", self.cam_id, e)

                # ── Decidir snapshot ─────────────────────────────────────
                if self.snapshots is not None and result.get("activity") != "error":
                    trigger = self._snapshot_trigger(people, has_alert, now)
                    if trigger:
                        try:
                            self.snapshots.save(self.cam_id, frame, trigger, event_id)
                            if trigger == "periodic":
                                self._last_periodic_t = now
                        except Exception as e:
                            logger.warning("Snapshot save error cam=%s: %s",
                                           self.cam_id, e)

                self._last_people = max(people, 0)

                logger.info(
                    "Nemotron cam=%s [%s] people=%s activity=%s %.0fms",
                    self.cam_id, reason,
                    result.get("people"),
                    str(result.get("activity", ""))[:40],
                    result.get("_ms", 0),
                )

            self._stop.wait(self.check_interval_s)

    # ── Snapshot trigger logic ────────────────────────────────────────────

    @staticmethod
    def _has_real_alert(result: dict) -> bool:
        for a in (result.get("alerts") or []):
            if str(a).strip() and str(a).strip() not in _FAKE_ALERTS:
                return True
        return False

    def _snapshot_trigger(self, people: int, has_alert: bool,
                          now: float) -> Optional[str]:
        """
        Decide qué tipo de snapshot guardar (o None).
        Prioridad: alert > people_change > periodic.
        """
        if has_alert:
            return "alert"

        prev = self._last_people
        # Personas aparecieron donde no había, o desaparecieron
        if (prev == 0 and people > 0) or (prev > 0 and people == 0):
            return "people_change"
        # Cambio relativo > 50%
        if prev > 0 and abs(people - prev) / prev > 0.5:
            return "people_change"

        if now - self._last_periodic_t >= self.snapshot_periodic_s:
            return "periodic"

        return None

    def stop(self) -> None:
        self._stop.set()
