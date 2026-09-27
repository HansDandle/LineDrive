import time
from datetime import datetime


def test_padding_after_live_sports(dvr, guide):
    dvr.EPG_CACHE["data"] = [dict(p) for p in guide["programs"]]
    dvr.EPG_CACHE["timestamp"] = time.time()
    # SNL 10:29 PM on 36.1 follows College Football (6:30-10:00) and the 10 PM news
    pad, game = dvr.overrun_padding("36.1", datetime(2026, 9, 26, 22, 29))
    assert pad == 30 and game["title"] == "College Football"
    # A morning show with no sports before it gets nothing
    assert dvr.overrun_padding("36.1", datetime(2026, 9, 28, 15, 30))[0] == 0
    # Turned off
    dvr.config.config.setdefault("recording", {})["sports_overrun_minutes"] = 0
    assert dvr.overrun_padding("36.1", datetime(2026, 9, 26, 22, 29))[0] == 0
    dvr.config.config["recording"]["sports_overrun_minutes"] = 30
