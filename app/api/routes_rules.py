"""Reglas de alertas: definicion de cada tipo, que camaras lo usan, como se disparan y datos reales; el modelo propone mejoras (no se aplican solas)."""
import json
import os
import time
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
SCENES_PATH = os.environ.get("SCENES_CONFIG", "/app/config/scenes.yml")

# De donde sale cada tipo y que filtros extra lo acompanan (lo que NO esta en scenes.yml)
SOURCES = {
    "persona_en_suelo": "VLM; se descarta si YOLO no vio personas o ninguna con forma horizontal (ancho/alto >= 0.8).",
    "persona_nocturna": "VLM; la regla de horario y de fin de semana sale de scenes.yml (night_person, night_hours).",
    "vehiculo_detenido": "VLM y ParkedTracker: un vehiculo quieto dentro del poligono de estacionamiento (llegada, cada hora, salida).",
    "visita_videoportero": "DoorAlerts: alguien con rostro frente al videoportero.",
    "timbre_videoportero": "Evento nativo de Dahua (CallNoAnswered/Invite) con captura del videoportero.",
    "puerta_abierta": "Sensor Tuya (MQTT): puerta/ventana/garage abierto, y de nuevo si sigue abierto 10 min.",
    "movimiento_tuya": "Camara Tuya: ipc_motion, una alerta por camara cada 120 s con captura.",
    "ruido_tuya": "Camara Tuya: ipc_bang (ruido fuerte).",
    "trafico_calle": "Visitas de personas en Exterior 1/2 (registro, no alerta del VLM).",
}


def _scenes() -> dict:
    try:
        with open(SCENES_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _stats(db, days: int = 7) -> dict:
    since = time.time() - days * 86400
    out: dict = {}
    with db._lock:
        rows = db._conn.execute(
            "SELECT json_extract(data,'$.alert_types[0]'), cam_id, COALESCE(review_label,'sin'), COUNT(*) FROM events "
            "WHERE type='nemotron' AND has_alert=1 AND ts>=? GROUP BY 1,2,3", (since,)).fetchall()
    for t, cam, lab, n in rows:
        o = out.setdefault(t or "sin_tipo", {"total": 0, "important": 0, "noise": 0, "sin": 0, "cams": {}})
        o["total"] += n
        o[lab if lab in ("important", "noise") else "sin"] += n
        o["cams"][cam] = o["cams"].get(cam, 0) + n
    return out


@router.get("/api/rules")
def rules(request: Request, days: int = 7):
    raw = _scenes()
    catalog = raw.get("alert_catalog") or {}
    names = {c.id: c.name for c in request.app.state.config.cameras}
    db = getattr(request.app.state, "db", None)
    st = _stats(db, min(max(days, 1), 30)) if db is not None else {}
    cams_by_type: dict = {}
    for cid, c in (raw.get("cameras") or {}).items():
        for t in c.get("alert_types") or []:
            cams_by_type.setdefault(t, []).append(cid)
    types = list(catalog) + [t for t in st if t not in catalog]
    out = []
    for t in types:
        s = st.get(t) or {"total": 0, "important": 0, "noise": 0, "sin": 0, "cams": {}}
        rev = s["important"] + s["noise"]
        out.append({"type": t, "definition": catalog.get(t, ""), "source": SOURCES.get(t, "VLM (Qwen) con el prompt de la camara"),
                    "cams": [{"id": c, "name": names.get(c, c), "alerts": s["cams"].get(c, 0)} for c in cams_by_type.get(t, [])],
                    "other_cams": [{"id": c, "name": names.get(c, c), "alerts": n} for c, n in s["cams"].items() if c not in cams_by_type.get(t, [])],
                    "stats": {k: s[k] for k in ("total", "important", "noise", "sin")}, "noise_rate": round(s["noise"] / rev, 2) if rev else None})
    return {"days": days, "night_hours": raw.get("night_hours"), "rules": out}


class AnalyzeBody(BaseModel):
    type: str
    days: int = 7


@router.post("/api/rules/analyze")
def analyze(body: AnalyzeBody, request: Request):
    """Pide al modelo (el mismo del reporte) revisar la regla con eventos reales; devuelve texto, no cambia ningun archivo."""
    from app.storage.report_generator import report_llm
    from app.vision.llm_text import complete_text
    analyzer = getattr(request.app.state, "vlm_analyzer", None)
    db = getattr(request.app.state, "db", None)
    if analyzer is None or db is None:
        raise HTTPException(503, "sin modelo disponible")
    raw = _scenes()
    catalog = raw.get("alert_catalog") or {}
    if body.type not in catalog and body.type not in SOURCES:
        raise HTTPException(404, "tipo de alerta desconocido")
    since = time.time() - min(max(body.days, 1), 30) * 86400
    with db._lock:
        rows = db._conn.execute(
            "SELECT cam_id, ts, COALESCE(review_label,'sin'), json_extract(data,'$.activity'), json_extract(data,'$.yolo_people'), json_extract(data,'$.severity') FROM events "
            "WHERE type='nemotron' AND has_alert=1 AND json_extract(data,'$.alert_types[0]')=? AND ts>=? ORDER BY ts DESC LIMIT 400", (body.type, since)).fetchall()
    if not rows:
        return {"type": body.type, "analysis": "No hay alertas de este tipo en el periodo; no hay datos para analizar."}
    pick = [r for r in rows if r[2] == "noise"][:10] + [r for r in rows if r[2] == "important"][:10] + [r for r in rows if r[2] == "sin"][:14]
    cams = {r[0] for r in rows}
    ctx = {c: {k: (raw.get("cameras", {}).get(c) or {}).get(k) for k in ("where", "focus", "ignore", "night_person")} for c in list(cams)[:6]}
    lines = "\n".join(f"- [{r[2]}] {r[0]} {time.strftime('%d/%m %H:%M', time.localtime(r[1]))} yolo={r[4]} sev={r[5]}: {(r[3] or '')[:140]}" for r in pick)
    msg = [{"role": "system", "content": "Eres un analista de un sistema de videovigilancia domestica. Respondes en espanol, conciso y concreto."},
           {"role": "user", "content": (
               f"Tipo de alerta: {body.type}\nDefinicion actual: {catalog.get(body.type, '(sin definicion)')}\nComo se genera: {SOURCES.get(body.type, 'VLM con el prompt de la camara')}\n"
               f"Totales ({len(rows)} alertas en el periodo): ruido marcado={sum(1 for r in rows if r[2]=='noise')}, importantes={sum(1 for r in rows if r[2]=='important')}, sin revisar={sum(1 for r in rows if r[2]=='sin')}.\n"
               f"Contexto de camaras (scenes.yml):\n{json.dumps(ctx, ensure_ascii=False)[:2500]}\n\nMuestras reales (etiqueta, camara, hora, personas segun YOLO, descripcion):\n{lines}\n\n"
               "Dame: 1) diagnostico breve (que parte son probablemente falsos positivos y por que); 2) una definicion mejorada para el catalogo; "
               "3) lineas concretas para agregar a 'ignore' o 'focus' por camara; 4) un filtro objetivo que se pueda programar (YOLO, hora, zona, duracion) para descartar los falsos positivos.")}]
    try:
        text = complete_text(report_llm(analyzer), msg, max_tokens=1100, temperature=0.2, timeout=120)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(502, f"el modelo no respondio: {exc}") from exc
    return {"type": body.type, "samples": len(pick), "analysis": text}
