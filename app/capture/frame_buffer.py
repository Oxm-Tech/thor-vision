import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class FrameEntry:
    frame: np.ndarray
    timestamp: float = field(default_factory=time.monotonic)


class FrameBuffer:
    """
    Buffer circular thread-safe por cámara.
    maxlen=2 → siempre se tiene el frame más reciente, latencia < 200ms.
    """

    def __init__(self, maxlen: int = 2):
        self._buf: deque[FrameEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._frame_count = 0
        self._last_ts: float = 0.0
        self._fps: float = 0.0

    def put(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        entry = FrameEntry(frame=frame, timestamp=now)
        with self._lock:
            self._buf.append(entry)
            self._frame_count += 1
            if self._last_ts > 0:
                elapsed = now - self._last_ts
                self._fps = 0.9 * self._fps + 0.1 * (1.0 / elapsed if elapsed > 0 else 0)
            self._last_ts = now

    def get_latest(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._buf:
                return None
            return self._buf[-1].frame.copy()

    def get_latest_entry(self) -> Optional[FrameEntry]:
        with self._lock:
            if not self._buf:
                return None
            e = self._buf[-1]
            return FrameEntry(frame=e.frame.copy(), timestamp=e.timestamp)

    def latency_ms(self) -> float:
        """Milisegundos desde el último frame recibido."""
        with self._lock:
            if self._last_ts == 0:
                return -1.0
            return (time.monotonic() - self._last_ts) * 1000

    @property
    def fps(self) -> float:
        with self._lock:
            return round(self._fps, 1)

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._frame_count

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._last_ts = 0.0
            self._fps = 0.0
