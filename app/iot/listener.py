"""Eventos de dispositivos Tuya (puertas, ventanas, garage) por MQTT, SOLO LECTURA.

El puente tuya_bridge (en oapc-devops) publica cada cambio de estado en <prefijo>/<id>/status y el ultimo estado retenido en
<prefijo>/<id>/last. Aqui se guardan en `iot_events`, y cuando una puerta o ventana se abre se genera una alerta con la captura de la
camara asociada; tambien si sigue abierta mucho tiempo y cuando la bateria del sensor esta baja. Nunca se publica nada al broker.

Credenciales: data/mqtt.json (permisos 600, fuera de git): {"host","port","user","password","topic"}.
"""
import json
import logging
import os
import sqlite3
import sys
import threading
import time

import yaml

logger = logging.getLogger(__name__)

MQTT_PATH = os.environ.get("MQTT_CONFIG", "/app/data/mqtt.json")
IOT_YML = os.environ.get("IOT_CONFIG", "/app/config/iot.yml")
LIBS = os.environ.get("PLATES_LIBS", "/app/data/pylibs")        # paho-mqtt se instala junto a fast-alpr (scripts/setup_mqtt.sh)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS iot_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, device_id TEXT NOT NULL, name TEXT, kind TEXT,
  code TEXT NOT NULL, value TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS idx_iot_ts ON iot_events(ts);
CREATE INDEX IF NOT EXISTS idx_iot_dev ON iot_events(device_id, ts);
"""


def load_map(path: str = IOT_YML) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("iot: no se pudo leer %s: %s", path, exc)
        return {}


def is_open(dev: dict, changes: dict):
    """True/False si el cambio trae el estado abierto/cerrado del dispositivo; None si no lo trae."""
    code = dev.get("open_code", "doorcontact_state")
    if code not in changes:
        return None
    return changes[code] == dev.get("open_value", True)


class IotListener:
    def __init__(self, db, snapshots, buffers: dict, cam_names: dict):
        self.db, self.snapshots, self.buffers, self.cam_names = db, snapshots, buffers, cam_names
        self.cfg = load_map()
        self.devices: dict = self.cfg.get("devices", {})
        self.state: dict = {}            # device_id -> {"open": bool|None, "since": ts, "battery": int|None, "last_ts": ts}
        self._alerted_open: dict = {}    # device_id -> ts de la ultima alerta de "sigue abierto"
        self._low_batt: dict = {}
        self._stop = threading.Event()
        self.status = {"connected": False, "error": "", "messages": 0}
        with db._lock:
            db._conn.executescript(_SCHEMA)

    # ---- mensajes
    def handle(self, topic: str, payload: bytes, retained: bool = False) -> None:
        try:
            msg = json.loads(payload)
        except ValueError:
            return
        dev_id = msg.get("device_id") or topic.split("/")[-2]
        changes = msg.get("changes") or {}
        dev = self.devices.get(dev_id)
        if dev is None or not changes:
            return
        self.status["messages"] += 1
        ts = float(msg.get("ts") or time.time())
        st = self.state.setdefault(dev_id, {"open": None, "since": ts, "battery": None, "last_ts": ts})
        st["last_ts"] = ts
        source = "sync" if retained else "event"
        for code, value in changes.items():
            self._store(ts, dev_id, dev, code, value, source)
        if "battery_percentage" in changes:
            st["battery"] = changes["battery_percentage"]
            self._check_battery(dev_id, dev, st["battery"])
        op = is_open(dev, changes)
        if op is None:
            return
        changed = st["open"] is not None and st["open"] != op
        first = st["open"] is None
        if op != st["open"]:
            st["open"], st["since"] = op, ts
        if retained or first:
            return                       # estado al arrancar: solo se registra, no alerta
        if changed and op:
            self._alert_opened(dev_id, dev, ts)
        elif changed and not op:
            self._store(ts, dev_id, dev, "cerrada", "true", "derived")

    def _store(self, ts, dev_id, dev, code, value, source) -> None:
        try:
            with self.db._lock:
                self.db._conn.execute("INSERT INTO iot_events (ts, device_id, name, kind, code, value, source) VALUES (?,?,?,?,?,?,?)",
                                      (ts, dev_id, dev.get("name"), dev.get("kind"), code, json.dumps(value), source))
                self.db._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("iot: no se pudo guardar el evento: %s", exc)

    # ---- alertas
    def _insert_alert(self, cam_id, activity: str, alert: str, alert_type: str, severity: str, extra: dict) -> int:
        payload = {"schema": 2, "source": "iot", "people": 0, "persons": [], "vehicles": 0, "activity": activity, "scene": "",
                   "relevant": True, "alerts": [alert], "alert_types": [alert_type], "severity": severity, "confidence": "high", "iot": extra}
        return self.db.insert_event("nemotron", cam_id, payload, people=0, has_alert=True)

    def _snapshot(self, event_id: int, cam_id, trigger: str) -> None:
        buf = self.buffers.get(cam_id) if cam_id else None
        frame = buf.peek_latest() if buf is not None and hasattr(buf, "peek_latest") else None
        if isinstance(frame, tuple):
            frame = frame[0]
        if self.snapshots is not None and frame is not None:
            try:
                self.snapshots.save(cam_id, frame, trigger, event_id=event_id)
            except (OSError, ValueError) as exc:
                logger.warning("iot: no se pudo guardar la captura: %s", exc)

    def _night(self, ts: float) -> bool:
        h = time.localtime(ts).tm_hour
        return h >= 22 or h < 6

    def _alert_opened(self, dev_id: str, dev: dict, ts: float) -> None:
        what = {"door": "puerta", "window": "ventana", "garage": "garage"}.get(dev.get("kind"), "dispositivo")
        sev = "medium" if self._night(ts) else "low"
        cam = dev.get("cam")
        eid = self._insert_alert(cam, f"Se abrio {what}: {dev['name']}", f"{dev['name']} abierta" + (" de noche" if sev == "medium" else ""),
                                 "puerta_abierta", sev, {"device_id": dev_id, "name": dev["name"], "kind": dev.get("kind"), "state": "open",
                                                          "cam_confirmed": bool(dev.get("confirmed"))})
        self._alerted_open[dev_id] = ts
        self._snapshot(eid, cam, "puerta")
        logger.info("iot: %s abierta -> alerta %d (cam %s)", dev["name"], eid, cam)

    def _check_battery(self, dev_id: str, dev: dict, pct) -> None:
        try:
            pct = int(pct)
        except (TypeError, ValueError):
            return
        if pct > int(self.cfg.get("low_battery_pct", 15)) or time.time() - self._low_batt.get(dev_id, 0) < 86400:
            return
        self._low_batt[dev_id] = time.time()
        self._insert_alert(dev.get("cam"), f"Bateria baja ({pct}%) del sensor {dev['name']}", f"Cambiar la pila del sensor {dev['name']} ({pct}%)",
                           "sensor_bateria_baja", "low", {"device_id": dev_id, "name": dev["name"], "battery": pct})

    def check_open_too_long(self, now: float | None = None) -> None:
        """Llamar periodicamente: alerta de nuevo si una puerta o ventana sigue abierta mas de alert_open_minutes."""
        now = now or time.time()
        limit = float(self.cfg.get("alert_open_minutes", 10)) * 60
        for dev_id, st in self.state.items():
            dev = self.devices.get(dev_id, {})
            if not st.get("open") or dev.get("kind") == "camera":
                continue
            if now - st["since"] >= limit and now - self._alerted_open.get(dev_id, 0) >= limit:
                self._alerted_open[dev_id] = now
                mins = int((now - st["since"]) // 60)
                eid = self._insert_alert(dev.get("cam"), f"{dev['name']} lleva {mins} min abierta", f"{dev['name']} sigue abierta ({mins} min)",
                                         "puerta_abierta", "medium", {"device_id": dev_id, "name": dev["name"], "state": "open", "minutes": mins})
                self._snapshot(eid, dev.get("cam"), "puerta")

    # ---- conexion MQTT
    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="iot-mqtt").start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            try:
                with open(MQTT_PATH, encoding="utf-8") as f:
                    cfg = json.load(f)
            except (OSError, ValueError):
                self.status.update(connected=False, error="sin data/mqtt.json (scripts/setup_mqtt.sh)")
                self._stop.wait(60)
                continue
            try:
                if LIBS not in sys.path:
                    sys.path.append(LIBS)
                import paho.mqtt.client as mqtt
            except ImportError:
                self.status.update(connected=False, error="falta paho-mqtt (scripts/setup_mqtt.sh)")
                self._stop.wait(60)
                continue
            prefix = str(cfg.get("topic", "oxm/tuya/#")).rstrip("#").rstrip("/")
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="thor-vision-iot")
            c.username_pw_set(cfg["user"], cfg["password"])

            def on_connect(cl, u, f, rc, p=None, _prefix=prefix):
                if rc.is_failure:
                    self.status.update(connected=False, error=str(rc))
                    return
                self.status.update(connected=True, error="")
                cl.subscribe([(f"{_prefix}/+/status", 1), (f"{_prefix}/+/last", 1)])

            c.on_connect = on_connect
            c.on_disconnect = lambda cl, u, f, rc, p=None: self.status.update(connected=False)
            c.on_message = lambda cl, u, m: self.handle(m.topic, m.payload, bool(m.retain))
            try:
                c.connect(cfg.get("host", "192.168.0.101"), int(cfg.get("port", 1883)), 30)
                c.loop_start()
                backoff = 5
                while not self._stop.wait(30):
                    self.check_open_too_long()
                c.loop_stop()
                c.disconnect()
            except OSError as exc:
                self.status.update(connected=False, error=f"sin conexion: {exc}"[:120])
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 120)

    def snapshot_state(self) -> list:
        out = []
        for dev_id, dev in self.devices.items():
            st = self.state.get(dev_id, {})
            out.append({"device_id": dev_id, "name": dev.get("name"), "kind": dev.get("kind"), "cam": dev.get("cam"),
                        "cam_name": self.cam_names.get(dev.get("cam") or "", None), "confirmed": bool(dev.get("confirmed")),
                        "open": st.get("open"), "since": st.get("since"), "battery": st.get("battery"), "last_ts": st.get("last_ts")})
        return out

    def recent(self, device_id: str = "", limit: int = 100) -> list:
        sql, args = "SELECT id, ts, device_id, name, kind, code, value, source FROM iot_events", []
        if device_id:
            sql += " WHERE device_id=?"
            args.append(device_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(min(limit, 500))
        with self.db._lock:
            rows = self.db._conn.execute(sql, args).fetchall()
        return [{"id": i, "ts": t, "device_id": d, "name": n, "kind": k, "code": c, "value": json.loads(v) if v else None, "source": s}
                for i, t, d, n, k, c, v, s in rows]
