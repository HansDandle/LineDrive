import time
import xml.etree.ElementTree as ET

import pytest

from epg_zap2it import ota_lineup_id, parse_postal_code


def load_guide(dvr, guide):
    dvr.EPG_CACHE["data"] = [dict(p) for p in guide["programs"]]
    dvr.EPG_CACHE["timestamp"] = time.time()
    dvr.channels.clear()
    dvr.channels.update(guide["lineup"])
    dvr.scheduled_jobs[:] = []


@pytest.fixture
def no_hidden(dvr):
    dvr.config.config.setdefault("guide", {})["hidden_channels"] = []
    yield
    dvr.config.config["guide"]["hidden_channels"] = []


def test_postal_codes():
    assert parse_postal_code("10001") == ("USA", "10001")
    assert parse_postal_code(" m5v 3l9 ") == ("CAN", "M5V3L9")
    assert parse_postal_code("M5V3L9") == ("CAN", "M5V3L9")
    assert parse_postal_code("1000") is None
    assert parse_postal_code("SW1A 1AA") is None     # UK: no Gracenote guide
    assert ota_lineup_id("M5V 3L9") == "CAN-OTAM5V3L9-DEFAULT"
    assert ota_lineup_id("78701") == "USA-OTA78701-DEFAULT"


def test_settings_reject_other_postal_codes(dvr):
    r = dvr.app.test_client().post("/api/setup/save", json={"hdhr_ip": "10.0.0.2", "zip_code": "SW1A 1AA"})
    assert r.status_code == 400 and "Canadian" in r.get_json()["error"]


def test_hidden_channels_leave_the_guide(dvr, guide, no_hidden):
    load_guide(dvr, guide)
    client = dvr.app.test_client()
    shown = [c["number"] for c in client.get("/api/guide?day=0").get_json()["channels"]]
    victim = shown[0]
    r = client.post("/api/guide/hide", json={"channels": [victim], "hidden": True})
    assert r.status_code == 200 and victim in r.get_json()["hidden"]
    after = [c["number"] for c in client.get("/api/guide?day=0").get_json()["channels"]]
    assert victim not in after and len(after) == len(shown) - 1
    assert all(str(p["channel_number"]) != victim for p in dvr.visible_epg())
    assert victim in dvr.channels                      # still recordable by number
    client.post("/api/guide/hide", json={"channels": [victim], "hidden": False})
    assert victim in [c["number"] for c in client.get("/api/guide?day=0").get_json()["channels"]]


def test_xmltv_export(dvr, guide, no_hidden):
    load_guide(dvr, guide)
    r = dvr.app.test_client().get("/guide.xml")
    assert r.status_code == 200 and r.mimetype == "application/xml"
    root = ET.fromstring(r.data)
    ids = {c.get("id") for c in root.findall("channel")}
    assert ids and ids <= set(guide["lineup"])
    progs = root.findall("programme")
    assert progs and all(p.get("channel") in ids for p in progs)
    first = progs[0]
    assert len(first.get("start")) == len("20260926151000 -0500") and first.findtext("title")
    assert any(p.find("new") is not None for p in progs)
    episodes = [p.findtext("episode-num[@system='onscreen']") for p in progs]
    assert any(e and e.startswith("S") for e in episodes)


def test_station_ticks_save_right_away(dvr, guide, no_hidden, monkeypatch):
    load_guide(dvr, guide)
    monkeypatch.setattr(dvr.config, "save_config", lambda: None)
    r = dvr.app.test_client().post("/api/setup/stations",
                                   json={"distant_channels": ["4", "x"], "hidden_channels": ["7.2", "7.1", "7.1"]})
    assert r.status_code == 200
    assert dvr.config.get("guide", "distant_channels") == ["4"]
    assert dvr.hidden_channels() == {"7.1", "7.2"}
    dvr.config.config["guide"]["distant_channels"] = []
