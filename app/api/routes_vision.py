import logging

import cv2
import numpy as np
from fastapi import APIRouter, Form, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Detection endpoints ────────────────────────────────────────────────

@router.get("/api/detections")
def get_all_detections(request: Request):
    store = request.app.state.detection_store
    return {
        "total_persons": store.total_persons(),
        "cameras": store.as_api(),
    }


@router.get("/api/detections/{cam_id}")
def get_camera_detection(cam_id: str, request: Request):
    store = request.app.state.detection_store
    d = store.get(cam_id)
    if d is None:
        return {"person_count": 0, "faces": [], "updated_at": None}
    return {
        "person_count": d.person_count,
        "faces": [
            {"name": f.name, "confidence": round(f.confidence, 3)}
            for f in d.faces
        ],
        "updated_at": d.updated_at,
        "inference_ms": round(d.inference_ms, 1),
    }


# ── Face management endpoints ──────────────────────────────────────────

@router.get("/api/faces")
def list_faces(request: Request):
    face_db = request.app.state.face_db
    return {"faces": face_db.list_faces(), "total": len(face_db)}


@router.post("/api/faces")
async def register_face(
    request: Request,
    name: str = Form(...),
    image: UploadFile = File(...),
):
    vision_models = request.app.state.vision_models
    face_db = request.app.state.face_db

    if vision_models._face_app is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Face recognition model not loaded"},
        )

    data = await image.read()
    arr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image"})

    embedding = vision_models.extract_embedding(frame)
    if embedding is None:
        return JSONResponse(status_code=422, content={"error": "No face detected in image"})

    face_id = face_db.add(name, embedding)
    logger.info("Registered face '%s' id=%s", name, face_id)
    return {"id": face_id, "name": name}


@router.delete("/api/faces/{face_id}")
def delete_face(face_id: str, request: Request):
    face_db = request.app.state.face_db
    if face_db.remove(face_id):
        return {"deleted": True, "id": face_id}
    return JSONResponse(status_code=404, content={"error": "Face not found"})
