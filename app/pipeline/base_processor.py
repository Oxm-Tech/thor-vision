from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
import numpy as np


@dataclass
class ProcessorResult:
    frame: np.ndarray
    metadata: dict = field(default_factory=dict)
    processing_ms: float = 0.0


class BaseProcessor(ABC):
    """
    Interfaz que debe implementar cualquier procesador ML.
    Fase 1: PassthroughProcessor.
    Fase 2: GemmaProcessor (análisis via Spark-1).
    """

    @abstractmethod
    def setup(self, config: dict, device: str) -> None: ...

    @abstractmethod
    def process(self, frame: np.ndarray, cam_id: str) -> ProcessorResult: ...

    @abstractmethod
    def teardown(self) -> None: ...
