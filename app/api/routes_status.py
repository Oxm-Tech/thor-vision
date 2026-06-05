from fastapi import APIRouter, Request
from app.utils.gpu_probe import get_system_metrics

router = APIRouter()


def _get_manager(request: Request):
    return request.app.state.capture_manager


@router.get("/api/health")
def health(request: Request):
    manager = _get_manager(request)
    return {"status": "ok", **manager.summary()}


@router.get("/api/cameras")
def cameras(request: Request):
    manager = _get_manager(request)
    return {"cameras": manager.get_all_stats()}


@router.get("/api/cameras/{cam_id}")
def camera_detail(cam_id: str, request: Request):
    manager = _get_manager(request)
    return manager.get_camera_stats(cam_id)


@router.get("/api/stats")
def stats(request: Request):
    manager = _get_manager(request)
    return {
        "summary": manager.summary(),
        "cameras": manager.get_all_stats(),
        "system": get_system_metrics(),
    }


@router.get("/api/system")
def system_metrics():
    return get_system_metrics()
