import base64
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un sistema de análisis de cámaras de seguridad. "
    "Responde ÚNICAMENTE con un objeto JSON válido. "
    "Sin texto adicional, sin markdown, sin explicación."
)

USER_PROMPT = (
    'Analiza el frame y responde con este JSON exacto:\n'
    '{"people": 0, "activity": "descripcion", "alerts": [], "scene": "descripcion"}\n'
    'Usa enteros reales para people, strings reales para los demas campos.'
)


class NemotronAnalyzer:
    """
    Envía frames a Nemotron-Omni (vllm) para análisis semántico.
    Deshabilita thinking mode con chat_template_kwargs para obtener
    JSON directo en content sin razonamiento.
    """

    def __init__(self, endpoint: str, model: str = "nemotron-omni",
                 max_tokens: int = 200, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        logger.info("NemotronAnalyzer init — endpoint=%s model=%s", self.endpoint, self.model)

    def analyze(self, frame: np.ndarray, context: dict = None) -> dict:
        t0 = time.monotonic()
        jpeg = self._encode_jpeg(frame)
        if not jpeg:
            return self._error("encode failed")

        b64 = base64.b64encode(jpeg).decode()

        # Construir prompt con contexto YOLO opcional
        user_text = USER_PROMPT
        if context:
            parts = []
            if context.get("person_count") is not None:
                parts.append(f"YOLO contó {context['person_count']} persona(s)")
            if context.get("faces"):
                names = [f.get("name", "desconocido") for f in context["faces"]]
                parts.append(f"Caras reconocidas: {', '.join(names)}")
            if parts:
                user_text = "Contexto YOLO: " + "; ".join(parts) + ".\n" + user_text

        payload = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
            # Deshabilitar thinking mode — fuerza respuesta directa en content
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }},
                        {"type": "text", "text": user_text},
                    ]
                }
            ]
        }).encode()

        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())

            choice = data["choices"][0]["message"]
            text = (choice.get("content") or "").strip()

            if not text:
                # Fallback: intentar extraer JSON del reasoning
                reasoning = (choice.get("reasoning") or "").strip()
                # Buscar último bloque JSON completo en el reasoning
                start = reasoning.rfind("{")
                end   = reasoning.rfind("}") + 1
                if start >= 0 and end > start:
                    candidate = reasoning[start:end]
                    try:
                        json.loads(candidate)  # validar antes de usar
                        text = candidate
                        logger.debug("Nemotron: JSON extraído de reasoning")
                    except json.JSONDecodeError:
                        pass

            if not text:
                logger.warning("Nemotron empty content+reasoning for response: %s",
                               json.dumps(choice)[:200])
                return self._error("empty response")

            # Limpiar fences markdown si los hay
            if "```" in text:
                for block in text.split("```"):
                    block = block.strip().lstrip("json").strip()
                    if block.startswith("{"):
                        text = block
                        break

            # Extraer primer objeto JSON
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

            result = json.loads(text)
            result["_ms"] = round((time.monotonic() - t0) * 1000)
            result["_ts"] = time.time()
            logger.info("Nemotron OK %.0fms people=%s activity=%s",
                        result["_ms"], result.get("people"), str(result.get("activity", ""))[:50])
            return result

        except urllib.error.URLError as e:
            logger.warning("Nemotron unreachable: %s", e)
            return self._error(f"unreachable: {e}")
        except json.JSONDecodeError as e:
            snippet = text[:120] if 'text' in locals() else "?"
            logger.warning("Nemotron bad JSON: %s | snippet=%s", e, snippet)
            return self._error("bad json")
        except Exception as e:
            logger.warning("Nemotron error: %s", e)
            return self._error(str(e))

    def _encode_jpeg(self, frame: np.ndarray, quality: int = 70) -> Optional[bytes]:
        try:
            h, w = frame.shape[:2]
            if w > 640:
                scale = 640 / w
                frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            return buf.tobytes()
        except Exception as e:
            logger.error("JPEG encode error: %s", e)
            return None

    @staticmethod
    def _error(msg: str) -> dict:
        return {
            "people": -1,
            "activity": "error",
            "alerts": [msg],
            "scene": "error",
            "_ts": time.time(),
            "_ms": 0,
        }
