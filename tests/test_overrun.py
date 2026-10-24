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


def test_padding_for_the_game_itself(dvr, guide, monkeypatch):
    dvr.EPG_CACHE["data"] = [dict(p) for p in guide["programs"]]
    dvr.EPG_CACHE["timestamp"] = time.time()
    # Recording College Football (6:30-10:00 PM on 36.1) itself: games run long too
    pad, game = dvr.overrun_padding("36.1", datetime(2026, 9, 26, 18, 30))
    assert pad == 30 and game["title"] == "College Football"
    # "Record the rest" of a game that's on now gets the extra time as well
    monkeypatch.setattr(dvr, "run_threaded", lambda fn, *args, **kw: None)
    end = datetime.now().replace(second=0, microsecond=0) + dvr.timedelta(minutes=60)
    assert dvr.start_in_progress("36.1", {"title": "Football", "genre": "Sports", "flags": ["Live"]}, end) in (90, 91)
    assert dvr.start_in_progress("36.1", {"title": "News", "genre": "News", "flags": []}, end) in (60, 61)
