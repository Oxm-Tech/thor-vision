"""
Snapshot manager — guarda JPGs en disco e indexa en SQLite.

Layout: {base_path}/{cam_id}/{yyyymmdd}/{HHMMSS}_{trigger}.jpg
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.storage.db import EventDB

logger = logging.getLogger(__name__)


class SnapshotManager:
    def __init__(self, base_path: str, db: EventDB,
                 frame_width: int = 1280, quality: int = 85):
        self.base        = Path(base_path)
        self.db          = db
        self.frame_width = frame_width
        self.quality     = quality
        self.base.mkdir(parents=True, exist_ok=True)
        logger.info("SnapshotManager ready — base=%s width=%d q=%d",
                    self.base, frame_width, quality)

    def save(self, cam_id: str, frame: np.ndarray, trigger: str,
             event_id: Optional[int] = None) -> Optional[str]:
        """
        Guarda un JPG y registra en la tabla snapshots.
        Retorna la ruta relativa (a `base_path`) o None si falla.
        """
        if frame is None or frame.size == 0:
            return None

        try:
            # Resize si excede frame_width
            h, w = frame.shape[:2]
            if w > self.frame_width:
                scale = self.frame_width / w
                frame = cv2.resize(frame, (self.frame_width, int(h * scale)),
                                   interpolation=cv2.INTER_LINEAR)

            now      = time.localtime()
            day_dir  = f"{now.tm_year:04d}{now.tm_mon:02d}{now.tm_mday:02d}"
            filename = (f"{now.tm_hour:02d}{now.tm_min:02d}{now.tm_sec:02d}"
                        f"_{trigger}.jpg")

            cam_dir  = self.base / cam_id / day_dir
            cam_dir.mkdir(parents=True, exist_ok=True)
            full_path = cam_dir / filename

            ok, buf = cv2.imencode(".jpg", frame,
                                   [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if not ok:
                logger.warning("Snapshot encode failed — cam=%s", cam_id)
                return None

            buf.tofile(str(full_path))
            size = full_path.stat().st_size

            # Ruta relativa al base_path
            rel_path = str(full_path.relative_to(self.base))
            # Persistir en index
            self.db.insert_snapshot(
                cam_id     = cam_id,
                path       = rel_path,
                trigger    = trigger,
                event_id   = event_id,
                size_bytes = size,
            )
            logger.debug("Snapshot saved cam=%s trigger=%s path=%s (%.1f KB)",
                         cam_id, trigger, rel_path, size / 1024)
            return rel_path

        except Exception as e:
            logger.warning("Snapshot save error cam=%s: %s", cam_id, e)
            return None

    def absolute_path(self, rel_path: str) -> Path:
        """Convierte ruta relativa a absoluta."""
        return self.base / rel_path

    def rotate(self, max_bytes: int = 50 * 1024 * 1024 * 1024,
               max_age_days: int = 30) -> dict:
        """
        Borra JPGs en disco más viejos que `max_age_days` o si la carpeta
        excede `max_bytes`. También elimina filas huérfanas en la tabla.
        """
        result = {"deleted_files": 0, "freed_bytes": 0, "deleted_rows": 0}
        now = time.time()
        cutoff = now - max_age_days * 86400

        # 1) Listar todos los snapshots indexados
        indexed = self.db.all_snapshot_paths()  # [(id, path)]

        # 2) Recolectar info de archivos
        files_info = []  # (id, rel_path, abs_path, mtime, size)
        for snap_id, rel_path in indexed:
            abs_path = self.base / rel_path
            try:
                st = abs_path.stat()
                files_info.append((snap_id, rel_path, abs_path, st.st_mtime, st.st_size))
            except FileNotFoundError:
                # Huérfano: archivo ya no existe → borrar fila
                self.db.delete_snapshot_row(snap_id)
                result["deleted_rows"] += 1

        # 3) Borrar archivos > max_age_days
        survivors = []
        for snap_id, rel, abs_path, mtime, size in files_info:
            if mtime < cutoff:
                try:
                    abs_path.unlink()
                    self.db.delete_snapshot_row(snap_id)
                    result["deleted_files"] += 1
                    result["freed_bytes"]   += size
                except OSError:
                    pass
            else:
                survivors.append((snap_id, rel, abs_path, mtime, size))

        # 4) Si total aún excede max_bytes, borrar más antiguos
        total = sum(s[4] for s in survivors)
        if total > max_bytes:
            survivors.sort(key=lambda s: s[3])   # más viejos primero
            for snap_id, rel, abs_path, mtime, size in survivors:
                if total <= max_bytes:
                    break
                try:
                    abs_path.unlink()
                    self.db.delete_snapshot_row(snap_id)
                    result["deleted_files"] += 1
                    result["freed_bytes"]   += size
                    total -= size
                except OSError:
                    pass

        # 5) Limpiar directorios día/cámara vacíos
        for cam_dir in self.base.iterdir():
            if not cam_dir.is_dir(): continue
            for day_dir in cam_dir.iterdir():
                if day_dir.is_dir():
                    try:
                        next(day_dir.iterdir())
                    except StopIteration:
                        day_dir.rmdir()
            try:
                next(cam_dir.iterdir())
            except StopIteration:
                cam_dir.rmdir()
            except FileNotFoundError:
                pass

        return result
