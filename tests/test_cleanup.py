import os
import time
from datetime import datetime, timedelta

import cleanup

NOW = datetime(2026, 10, 10, 12, 0)


def entry(name, days_ago, played_days_ago=None):
    return {"file": name, "finished_at": NOW - timedelta(days=days_ago),
            "played_at": NOW - timedelta(days=played_days_ago) if played_days_ago is not None else None}


def files(removed):
    return sorted(e["file"] for e in removed)


def test_parse_keep():
    assert cleanup.parse_keep("last:5") == ("last", 5)
    assert cleanup.parse_keep("watched:0") == ("watched", 0)
    for value in ("all", "", None, "last:0", "last:x", "forever:3"):
        assert cleanup.parse_keep(value) is None
    # Ask LineDrive's "for 6 weeks" on older rules
    assert cleanup.keep_setting({"retention_weeks": 6}) == "days:42"
    assert cleanup.keep_setting({"keep": "last:3", "retention_weeks": 6}) == "last:3"
    assert cleanup.keep_setting({}) == "all"


def test_rules():
    eps = [entry("e1", 20, 15), entry("e2", 10, 1), entry("e3", 3), entry("e4", 1)]
    assert files(cleanup.to_remove(eps, ("last", 2), NOW)) == ["e1", "e2"]
    assert files(cleanup.to_remove(eps, ("last", 9), NOW)) == []
    assert files(cleanup.to_remove(eps, ("days", 7), NOW)) == ["e1", "e2"]
    assert files(cleanup.to_remove(eps, ("watched", 2), NOW)) == ["e1"]   # e2 watched only yesterday
    assert files(cleanup.to_remove(eps, ("watched", 0), NOW)) == ["e1", "e2"]
    assert cleanup.to_remove(eps, None, NOW) == []


def test_recycle_and_purge(tmp_path):
    root = tmp_path
    season = root / "TV" / "Jeopardy!" / "Season 43"
    season.mkdir(parents=True)
    video = season / "Jeopardy! - S43E11.mp4"
    for p in (video, season / "Jeopardy! - S43E11.en.srt", season / "Jeopardy! - S43E11.nfo"):
        p.write_text("x")
    cleanup.recycle(str(video), str(root))
    bin_season = root / ".deleted" / "TV" / "Jeopardy!" / "Season 43"
    assert sorted(os.listdir(bin_season)) == ["Jeopardy! - S43E11.en.srt", "Jeopardy! - S43E11.mp4", "Jeopardy! - S43E11.nfo"]
    assert (root / ".deleted" / ".ignore").exists()           # Jellyfin skips it
    assert not (root / "TV" / "Jeopardy!").exists()           # empty show folder removed...
    assert (root / "TV").exists()                             # ...but not TV itself
    assert cleanup.purge_recycled(str(root)) == 0             # just deleted: kept for now
    assert cleanup.purge_recycled(str(root), now=time.time() + 8 * 86400) == 3
    assert os.listdir(root / ".deleted") == [".ignore"]


def test_run_cleanup_only_touches_its_own_recordings(dvr, monkeypatch):
    root = dvr.SAVE_DIR
    show = os.path.join(root, "TV", "Test Show", "Season 01")
    os.makedirs(show, exist_ok=True)
    names = [f"Test Show - S01E0{n}.mp4" for n in range(1, 4)]
    for name in names + ["Test Show - S01E09 - Downloaded.mkv"]:  # the .mkv isn't LineDrive's
        open(os.path.join(show, name), "w").close()
    rule = {"id": 501, "type": "recurring_series", "status": "active", "title": "Test Show", "keep": "last:1"}
    monkeypatch.setattr(dvr, "scheduled_jobs", [rule])
    monkeypatch.setattr(dvr, "LEDGER_FILE", os.path.join(root, "..", "ledger-test.json"))
    monkeypatch.setattr(dvr, "notify_jellyfin", lambda path: None)
    started = NOW - timedelta(days=3)
    for n, name in enumerate(names, 1):
        dvr.ledger_add(os.path.join(show, name), 501, {"title": "Test Show", "season_number": 1, "episode_number": n},
                       started + timedelta(days=n))
    dvr.NOTICES.clear()
    removed = dvr.run_cleanup()
    assert sorted(e["file"].split(os.sep)[-1] for _, e in removed) == names[:2]
    assert sorted(os.listdir(show)) == ["Test Show - S01E03.mp4", "Test Show - S01E09 - Downloaded.mkv"]
    assert "Cleaned up 2 recordings of Test Show" in dvr.NOTICES[-1]["message"]
    # Removed episodes still count as recorded, so a rerun won't bring them back
    assert dvr.already_recorded({"title": "Test Show", "season_number": "1", "episode_number": "1"})
    # The recycle folder isn't listed as a recent recording
    assert not any(r["folder"].startswith(".deleted") for r in dvr.recent_recording_files(20))
    # Running again changes nothing
    assert dvr.run_cleanup() == []


def test_keep_setting_endpoint_and_upcoming(dvr, monkeypatch):
    rule = {"id": 502, "type": "recurring_series", "status": "active", "title": "Nightly", "time": "8:00 PM",
            "duration": 30, "channel_number": "5.1", "recurrence": {"days": []}}
    monkeypatch.setattr(dvr, "scheduled_jobs", [rule])
    monkeypatch.setattr(dvr, "_cleanup_safely", lambda: None)
    client = dvr.app.test_client()
    assert client.post("/api/rules/502", json={"keep": "forever"}).status_code == 400
    r = client.post("/api/rules/502", json={"keep": "last:5"}).get_json()
    assert "keep the newest 5" in r["message"] and ".deleted" in r["message"]
    assert rule["keep"] == "last:5"
    item = next(u for u in dvr.upcoming_recordings() if u["id"] == 502)
    assert item["keep"] == "last:5"


def test_watch_in_vlc(dvr, monkeypatch):
    monkeypatch.setitem(dvr.channels, "24.1", "KVUE")
    monkeypatch.setattr(dvr, "HDHR_IP", "192.168.1.50")
    monkeypatch.setattr(dvr, "no_tuner_message", lambda: None)
    client = dvr.app.test_client()
    data = client.get("/api/watch/24.1").get_json()
    assert data["url"] == "http://192.168.1.50:5004/auto/v24.1"
    playlist = client.get(data["playlist"])
    assert playlist.mimetype == "audio/x-mpegurl"
    assert playlist.get_data(as_text=True).splitlines() == [
        "#EXTM3U", "#EXTINF:-1,24.1 KVUE", "http://192.168.1.50:5004/auto/v24.1"]
    assert client.get("/api/watch/99.9").status_code == 404
    monkeypatch.setattr(dvr, "no_tuner_message", lambda: "Both tuners are in use (5.1, 7.1). Stop one of those to record this.")
    busy = client.get("/api/watch/24.1")
    assert busy.status_code == 409 and "to watch this" in busy.get_json()["error"]
