"""Eventos IoT por MQTT (solo lectura): estado, alertas de puerta abierta, abierta mucho tiempo y bateria baja."""
import json
import sqlite3
import threading
import time

from app.iot import listener as li


class FakeDB:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:")
        self.events = []

    def insert_event(self, type, cam_id, payload, people=None, has_alert=False):
        self.events.append((type, cam_id, payload, has_alert))
        return len(self.events)


class FakeSnaps:
    def __init__(self):
        self.saved = []

    def save(self, cam_id, frame, trigger, event_id=None):
        self.saved.append((cam_id, trigger, event_id))


class FakeBuf:
    def peek_latest(self):
        return object()


def make():
    db, sn = FakeDB(), FakeSnaps()
    m = li.IotListener(db, sn, {"cam-113": FakeBuf()}, {"cam-113": "Escaleras entrada"})
    m.cfg = {"alert_open_minutes": 10, "low_battery_pct": 15}
    m.devices = {"D1": {"name": "Recepcion Puerta", "kind": "door", "cam": "cam-113", "confirmed": False, "open_code": "doorcontact_state", "open_value": True},
                 "C1": {"name": "Camara", "kind": "camera", "cam": None}}
    return m, db, sn


def msg(dev, changes, ts=None):
    return json.dumps({"device_id": dev, "ts": ts or time.time(), "changes": changes}).encode()


def test_repo_map_parses_and_has_the_sensors():
    cfg = li.load_map("config/iot.yml")
    assert cfg["devices"]["ebd84e19bf42731470j1ao"]["kind"] == "door" and cfg["alert_open_minutes"] == 10


def test_is_open():
    d = {"open_code": "doorcontact_state", "open_value": True}
    assert li.is_open(d, {"doorcontact_state": True}) is True and li.is_open(d, {"doorcontact_state": False}) is False
    assert li.is_open(d, {"battery_percentage": 50}) is None


def test_startup_state_and_retained_never_alert_but_are_stored():
    m, db, sn = make()
    m.handle("oxm/tuya/D1/last", msg("D1", {"doorcontact_state": True}), retained=True)
    m.handle("oxm/tuya/D1/status", msg("D1", {"doorcontact_state": True}))            # primer estado conocido
    assert db.events == [] and m.state["D1"]["open"] is True
    assert {r["source"] for r in m.recent()} == {"sync", "event"}


def test_opening_creates_alert_with_snapshot_and_closing_does_not():
    m, db, sn = make()
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}))
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": True}))
    assert len(db.events) == 1
    typ, cam, p, has_alert = db.events[0]
    assert typ == "nemotron" and cam == "cam-113" and has_alert and p["source"] == "iot"
    assert p["alert_types"] == ["puerta_abierta"] and p["iot"]["state"] == "open" and p["iot"]["cam_confirmed"] is False
    assert sn.saved == [("cam-113", "puerta", 1)]
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}))                  # cerrarse no alerta
    assert len(db.events) == 1 and m.state["D1"]["open"] is False


def test_open_too_long_alerts_once_per_interval():
    m, db, sn = make()
    t0 = 1_000_000.0
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}, t0))
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": True}, t0 + 10))
    n = len(db.events)
    m.check_open_too_long(t0 + 10 + 300)                                                # 5 min: aun no
    assert len(db.events) == n
    m.check_open_too_long(t0 + 10 + 11 * 60)
    assert len(db.events) == n + 1 and "min abierta" in db.events[-1][2]["activity"]
    m.check_open_too_long(t0 + 10 + 12 * 60)                                            # no repite enseguida
    assert len(db.events) == n + 1


def test_low_battery_alerts_once_a_day_and_unknown_devices_are_ignored():
    m, db, sn = make()
    m.handle("t/D1/status", msg("D1", {"battery_percentage": 1}))
    m.handle("t/D1/status", msg("D1", {"battery_percentage": 1}))
    assert [e[2]["alert_types"] for e in db.events] == [["sensor_bateria_baja"]]
    m.handle("t/XX/status", msg("XX", {"doorcontact_state": True}))
    assert len(db.events) == 1 and "XX" not in m.state


def test_garbage_messages_are_ignored():
    m, db, _ = make()
    m.handle("t/D1/status", b"no es json")
    m.handle("t/D1/status", msg("D1", {}))
    assert db.events == []
