import time
import numpy as np

from app.pipeline.base_processor import BaseProcessor, ProcessorResult


class PassthroughProcessor(BaseProcessor):
    """Devuelve el frame sin modificar. Usado en fase 1."""

    def setup(self, config: dict, device: str) -> None:
        pass

    def process(self, frame: np.ndarray, cam_id: str) -> ProcessorResult:
        t0 = time.monotonic()
        return ProcessorResult(
            frame=frame,
            metadata={},
            processing_ms=(time.monotonic() - t0) * 1000,
        )

    def teardown(self) -> None:
        pass
