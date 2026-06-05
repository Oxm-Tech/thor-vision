"""
Chat endpoint que consulta Nemotron sobre lo que ven las cámaras.

- POST /api/chat
  Body: { "message": str, "history": [{role, content}] }
  Response: { "response": str, "context_cameras": int, "ms": int }

El sistema incluye en el system prompt el contexto en vivo de
todas las cámaras (último análisis Nemotron) para que el modelo
pueda responder con conocimiento de la escena actual.

Nemotron corre en DGX Spark con GPU — esta ruta solo orquesta
el request HTTP, no hace inferencia local.
"""
import json
import logging
import re
import time
import urllib.request
import urllib.error
import uuid
from typing import List, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Detector: ¿la pregunta requiere histórico?
#
# Por default NO incluimos histórico — solo el estado actual va al prompt.
# Esto evita saturar Nemotron con eventos pasados cuando la pregunta es
# sobre "ahora". El histórico solo se inyecta cuando hay señales claras
# de que la pregunta es sobre el pasado o pide una agregación temporal.
# ─────────────────────────────────────────────────────────────────────────
_HISTORY_RE = re.compile(
    r"\b("
    # Adverbios temporales pasados
    r"hoy|ayer|anteayer|antes|anteriormente|previamente|"
    r"anoche|esta\s+(?:mañana|tarde|noche|madrugada)|"
    r"hace\s+\d+|hace\s+(?:un|una|unos|unas|dos|tres|cuatro|cinco|diez|veinte|"
    r"medi[oa]|much[oa]s?)\s+(?:segund|minut|hor|d[ií]a|semana|mes|año)|"
    # Tiempos verbales pasados (pretérito + imperfecto)
    r"pas[oó]|pasaron|pasaba|pasaban|"
    r"sucedi[oó]|sucedieron|ocurri[oó]|ocurrieron|"
    r"estuv[oe]|estuvieron|estaba|estaban|"
    r"hub[oe]|hab[ií]a|hab[ií]an|"
    r"vin[oe]|vinieron|ven[ií]a|ven[ií]an|"
    r"entr[oó]|entraron|sali[oó]|salieron|lleg[oó]|llegaron|"
    r"vio|vieron|ve[ií]a|ve[ií]an|detect[oó]|detectaron|registr[oó]|registraron|"
    # Perfecto compuesto: "ha/han + participio"
    r"ha[ns]?\s+(?:visto|habido|pasado|ocurrido|entrado|salido|llegado|estado|detectado|registrado)|"
    r"se\s+(?:vio|vieron|ve[ií]a|ve[ií]an|registr[oó]|registraron|detect[oó]|detectaron)|"
    # Preguntas sobre cuándo
    r"cu[aá]ndo|desde\s+cu[aá]ndo|hasta\s+cu[aá]ndo|cu[aá]nto\s+tiempo|"
    r"[uú]ltim[oa]\s+(?:vez|momento|hora|d[ií]a)|"
    # Agregaciones / históricos
    r"resumen|resumir|historial|hist[oó]ric|registro|reporte|"
    r"cu[aá]nt[ao]s?\s+veces|"
    r"tendencia|evoluci[oó]n|patr[oó]n|pico\s+de|"
    # Disparadores explícitos
    r"qu[eé]\s+pas[oó]|qu[eé]\s+ha\s+pasado|qu[eé]\s+ocurri[oó]"
    r")\b",
    re.IGNORECASE,
)


def _question_needs_history(question: str) -> bool:
    """True si la pregunta hace referencia al pasado o pide agregación."""
    return bool(_HISTORY_RE.search(question or ""))


class ChatMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


def _format_relative_time(seconds_ago: float) -> str:
    """1h23min, 45min, 12s — texto humano de cuánto hace."""
    if seconds_ago < 60:
        return f"{int(seconds_ago)}s"
    if seconds_ago < 3600:
        return f"{int(seconds_ago // 60)}min"
    h = int(seconds_ago // 3600)
    m = int((seconds_ago % 3600) // 60)
    return f"{h}h{m:02d}min" if m else f"{h}h"


def _build_recent_history(db, config, hours: float = 6.0,
                          max_events: int = 25) -> tuple[str, int]:
    """
    Construye un timeline cronológico de eventos significativos en las
    últimas `hours` horas, consultando la tabla `events`.

    Significativo = tiene alerta, o tiene personas, o la descripción
    cambió respecto a la observación anterior de la misma cámara.

    Retorna (texto, total_eventos_listados).
    """
    if db is None:
        return "(persistencia no disponible)", 0

    cam_names = {c.id: c.name for c in config.cameras}
    since     = time.time() - hours * 3600

    try:
        # Pedimos bastantes para luego filtrar a los significativos
        events = db.query_events(type="nemotron", since=since, limit=400)
    except Exception:
        return "(error consultando histórico)", 0

    if not events:
        return f"Sin actividad registrada en las últimas {int(hours)} horas.", 0

    # Orden cronológico (más viejo primero) para detectar cambios de descripción
    events_chrono = list(reversed(events))

    last_desc_per_cam: dict = {}
    last_people_per_cam: dict = {}
    significant = []
    alert_count = 0
    for ev in events_chrono:
        cam_id    = ev.get("cam_id") or ""
        people    = ev.get("people") or 0
        has_alert = bool(ev.get("has_alert"))
        data      = ev.get("data") or {}
        activity  = (data.get("activity") or "").strip()
        alerts    = [a for a in (data.get("alerts") or []) if str(a).strip()]

        prev_desc   = last_desc_per_cam.get(cam_id)
        prev_people = last_people_per_cam.get(cam_id, 0)

        is_significant = (
            has_alert
            or people > 0
            or (prev_desc is not None and activity and activity != prev_desc)
            or (prev_people > 0 and people == 0)   # personas se fueron
        )

        if is_significant:
            if has_alert:
                alert_count += 1
            significant.append({
                "ts":        ev["ts"],
                "cam_id":    cam_id,
                "people":    people,
                "activity":  activity,
                "has_alert": has_alert,
                "alerts":    alerts,
            })

        last_desc_per_cam[cam_id]   = activity
        last_people_per_cam[cam_id] = people

    # Quedarnos con los más recientes (los últimos `max_events`)
    significant = significant[-max_events:]
    if not significant:
        return (f"Sin cambios significativos en las últimas {int(hours)} horas "
                f"(escenas estáticas)."), 0

    now = time.time()
    lines = []
    for ev in significant:
        ago    = _format_relative_time(now - ev["ts"])
        name   = cam_names.get(ev["cam_id"], ev["cam_id"])
        prefix = "[ALERTA] " if ev["has_alert"] else ""
        ppl    = f"{ev['people']}p" if ev["people"] > 0 else "0p"
        desc   = ev["activity"][:70] if ev["activity"] else "(sin descripción)"
        line   = f"- hace {ago} · {name} · {ppl} · {desc}"
        if ev["has_alert"] and ev["alerts"]:
            line += f"  ALERTAS: {', '.join(ev['alerts'][:2])}"
        lines.append(prefix + line)

    header = f"({len(significant)} eventos relevantes"
    if alert_count:
        header += f", {alert_count} con alerta"
    header += "):"
    return header + "\n" + "\n".join(lines), len(significant)


def _build_camera_context(store, config) -> tuple[str, int]:
    """Construye el contexto en vivo de todas las cámaras."""
    if store is None:
        return "Sin sistema de análisis disponible.", 0

    cam_names = {c.id: c.name for c in config.cameras}
    lines = []
    now = time.time()

    for cam_id, det in store.get_all().items():
        nem = det.nemotron
        if not nem or nem.get("activity") == "error":
            continue
        name     = cam_names.get(cam_id, cam_id)
        people   = nem.get("people", 0)
        activity = (nem.get("activity") or "").strip()
        scene    = (nem.get("scene") or "").strip()
        alerts   = [a for a in (nem.get("alerts") or [])
                    if str(a).strip() not in
                    {"", "error", "empty response", "bad json", "unreachable"}]
        age_s = int(now - nem.get("_ts", now))

        parts = [f"{name}: {people} persona(s)"]
        if activity: parts.append(f"actividad: {activity}")
        if scene and scene != activity: parts.append(f"escena: {scene}")
        if alerts: parts.append(f"ALERTAS: {', '.join(alerts)}")
        parts.append(f"hace {age_s}s")
        lines.append("- " + " | ".join(parts))

    if not lines:
        return "Sin observaciones recientes de las cámaras.", 0

    return "\n".join(lines), len(lines)


@router.post("/api/chat")
def chat(req: ChatRequest, request: Request,
         x_session_id: Optional[str] = Header(default=None)):
    t0 = time.monotonic()

    analyzer = getattr(request.app.state, "nemotron_analyzer", None)
    if analyzer is None:
        return {"response": "Nemotron no está configurado en el servidor.",
                "error": True, "ms": 0}

    store  = getattr(request.app.state, "detection_store", None)
    config = request.app.state.config
    db     = getattr(request.app.state, "db", None)

    # Asignar session_id si no vino
    session_id = (x_session_id or "").strip() or str(uuid.uuid4())

    context_block, n_ctx = _build_camera_context(store, config)
    total_cams = len(config.cameras)

    # Solo cargamos el histórico si la pregunta lo necesita
    # — esto reduce el contexto enviado a Nemotron y baja la carga GPU.
    needs_history = _question_needs_history(req.message)
    if needs_history:
        history_block, n_hist = _build_recent_history(db, config, hours=6.0)
    else:
        history_block = ""
        n_hist = 0

    if needs_history:
        system_prompt = (
            f"Eres el asistente de THOR Vision, un sistema de vigilancia con "
            f"{total_cams} cámaras IP. Tienes dos fuentes:\n"
            f"1. Estado actual de las cámaras (en vivo)\n"
            f"2. Histórico de eventos significativos de las últimas 6 horas\n\n"
            f"## Estado actual por cámara:\n"
            f"{context_block}\n\n"
            f"## Histórico reciente {history_block}\n\n"
            f"## Instrucciones\n"
            f"- Responde en español, conciso y profesional.\n"
            f"- Cuando cites un evento del histórico, incluye 'hace Xmin' o 'hace Xh'.\n"
            f"- Si hay alertas, priorízalas.\n"
            f"- No inventes información que no esté en los datos provistos.\n"
            f"- Usa los nombres de las cámaras tal como aparecen."
        )
    else:
        # Pregunta sobre estado presente — sin histórico, prompt mucho más corto.
        system_prompt = (
            f"Eres el asistente de THOR Vision, un sistema de vigilancia con "
            f"{total_cams} cámaras IP. Respondes sobre lo que las cámaras "
            f"están viendo AHORA MISMO.\n\n"
            f"## Estado actual por cámara:\n"
            f"{context_block}\n\n"
            f"## Instrucciones\n"
            f"- Responde en español, conciso y profesional.\n"
            f"- Solo usa el estado actual — no especules sobre el pasado.\n"
            f"- Si la pregunta requiere datos históricos, sugiere reformularla "
            f"con palabras como 'hoy', 'hace un rato', 'cuándo' para activar "
            f"la búsqueda en el historial.\n"
            f"- No inventes información que no esté en los datos provistos.\n"
            f"- Usa los nombres de las cámaras tal como aparecen."
        )

    # Construir mensajes — system + últimos 10 turnos + nuevo
    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history[-10:]:
        if m.role in ("user", "assistant") and m.content:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    payload = json.dumps({
        "model":                analyzer.model,
        "max_tokens":           600,
        "temperature":          0.3,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages":             messages,
    }).encode()

    http_req = urllib.request.Request(
        analyzer.endpoint,
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )

    try:
        with urllib.request.urlopen(http_req, timeout=60) as resp:
            data = json.loads(resp.read())

        choice = data["choices"][0]["message"]
        text = (choice.get("content") or "").strip()

        if not text:
            # Fallback al reasoning si el modelo no produce content
            reasoning = (choice.get("reasoning") or "").strip()
            # Tomar las primeras 2-3 líneas significativas
            if reasoning:
                text = reasoning.split("\n\n")[-1].strip()

        if not text:
            text = "(sin respuesta del modelo)"

        ms = round((time.monotonic() - t0) * 1000)
        logger.info(
            "Chat OK %dms ctx=%d cams hist=%s(%d) | session=%s Q=%s",
            ms, n_ctx,
            "yes" if needs_history else "no",
            n_hist,
            session_id[:8],
            req.message[:60].replace("\n", " "),
        )

        # Persistir conversación (user + assistant) si hay DB
        if db is not None:
            try:
                db.insert_chat(session_id, "user",      req.message,
                               context_cams=n_ctx)
                db.insert_chat(session_id, "assistant", text,
                               context_cams=n_ctx, ms=ms)
            except Exception as e:
                logger.warning("Chat DB insert error: %s", e)

        return {
            "response":         text,
            "context_cameras":  n_ctx,
            "history_events":   n_hist,
            "used_history":     needs_history,
            "ms":               ms,
            "session_id":       session_id,
        }

    except urllib.error.URLError as e:
        logger.warning("Chat unreachable: %s", e)
        return {"response": f"No se puede contactar a Nemotron: {e}",
                "error": True, "session_id": session_id,
                "ms": round((time.monotonic() - t0) * 1000)}
    except Exception as e:
        logger.warning("Chat error: %s", e)
        return {"response": f"Error procesando la pregunta: {e}",
                "error": True, "session_id": session_id,
                "ms": round((time.monotonic() - t0) * 1000)}
