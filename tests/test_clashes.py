import json
from datetime import datetime, timedelta

NOW = datetime(2026, 10, 1, 12, 0)  # a Thursday


def once(title, date, time, duration=60, **extra):
    return dict({"status": "scheduled", "title": title, "date": date, "time": time,
                 "duration": duration, "channel_number": "5.1"}, **extra)


def lost(dvr, jobs, tuners=2, busy=()):
    airings = dvr.planned_airings(jobs, NOW)
    return [(j["title"], start.strftime("%a %H:%M"), held)
            for start, _end, j, held in dvr.find_clashes(airings, list(busy), tuners)]


def test_third_overlapping_recording_has_no_tuner(dvr):
    jobs = [once("A", "2026-10-01", "20:00"), once("B", "2026-10-01", "20:00"),
            once("C", "2026-10-01", "20:30", 30)]
    assert lost(dvr, jobs) == [("C", "Thu 20:30", ["A", "B"])]
    assert lost(dvr, jobs, tuners=3) == []


def test_back_to_back_is_not_a_clash(dvr):
    jobs = [once("A", "2026-10-01", "20:00"), once("B", "2026-10-01", "20:00"),
            once("C", "2026-10-01", "21:00")]
    assert lost(dvr, jobs) == []


def test_ties_go_to_the_earlier_entry_like_the_scheduler(dvr):
    jobs = [once("A", "2026-10-01", "20:00"), once("B", "2026-10-01", "20:00"),
            once("C", "2026-10-01", "20:00")]
    assert [t for t, _, _ in lost(dvr, jobs)] == ["C"]


def test_a_failed_recording_does_not_hold_a_tuner(dvr):
    # C can't start, so it isn't holding a tuner when E starts at 21:00, as A and B finish
    jobs = [once("A", "2026-10-01", "20:00"), once("B", "2026-10-01", "20:00"),
            once("C", "2026-10-01", "20:30", 120), once("E", "2026-10-01", "21:00")]
    assert [t for t, _, _ in lost(dvr, jobs)] == ["C"]


def test_whats_recording_now_counts(dvr):
    busy = [(NOW + timedelta(minutes=45), "Live game")]
    assert lost(dvr, [once("A", "2026-10-01", "12:30", 30)], tuners=1, busy=busy) == \
        [("A", "Thu 12:30", ["Live game"])]


def test_series_rules_expand_by_weekday(dvr):
    rule = {"type": "recurring_series", "status": "active", "title": "Nightly", "time": "8:00 PM",
            "duration": 60, "channel_number": "7.1", "recurrence": {"days": ["Saturday"]}}
    jobs = [rule, once("A", "2026-10-03", "20:00"), once("B", "2026-10-03", "20:15")]
    # Saturday Oct 3: the rule (listed first) and A get the tuners; B doesn't
    assert lost(dvr, jobs) == [("B", "Sat 20:15", ["Nightly", "A"])]
    # Skipped airings (reruns, already recorded) don't take a tuner
    airings = dvr.planned_airings(jobs, NOW, skip=lambda job, slot: job is rule)
    assert dvr.find_clashes(airings, [], 2) == []
    # Started, past and paused entries don't count
    assert lost(dvr, [dict(rule, status="paused"), once("A", "2026-10-03", "20:00"),
                      once("B", "2026-10-03", "20:00", last_started_at="x")]) == []


def test_scheduling_warns_and_badges_but_still_schedules(dvr, monkeypatch):
    monkeypatch.setattr(dvr, "TUNER_COUNT", 2)
    monkeypatch.setitem(dvr.EPG_CACHE, "data", [])
    monkeypatch.setitem(dvr.channels, "5.1", "KTBC")
    day = (datetime.now() + timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
    dvr.scheduled_jobs[:] = [dict(once("NCIS", day.strftime("%Y-%m-%d"), "20:00"), id=1),
                             dict(once("Survivor", day.strftime("%Y-%m-%d"), "20:00"), id=2)]
    dvr.clashes_changed()
    client = dvr.app.test_client()
    try:
        r = client.post("/schedule", json={"channel": "5.1", "duration": 30, "time": "20:15",
                                           "days": [day.strftime("%A")]})
        body = r.get_json()
        assert r.status_code == 200
        assert "Heads up" in body["message"] and "NCIS and Survivor" in body["message"]
        assert len(dvr.scheduled_jobs) == 3                     # still scheduled
        status = json.loads(client.get("/api/status").get_data(as_text=True))
        clashing = [u for u in status["upcoming"] if u.get("clash")]
        assert [u["title"] for u in clashing] == ["KTBC Recording"]
        assert clashing[0]["clash"]["next"] and clashing[0]["clash"]["with"] == ["NCIS", "Survivor"]
        assert status["version"] == dvr.__version__
        # Cancelling one of the others resolves it, and the badge goes away
        client.post("/api/guide/cancel", json={"job_id": 1})
        status = json.loads(client.get("/api/status").get_data(as_text=True))
        assert not any(u.get("clash") for u in status["upcoming"])
    finally:
        dvr.scheduled_jobs[:] = []
        dvr.clashes_changed()


def test_no_clash_no_warning(dvr, monkeypatch):
    monkeypatch.setattr(dvr, "TUNER_COUNT", 2)
    monkeypatch.setitem(dvr.EPG_CACHE, "data", [])
    monkeypatch.setitem(dvr.channels, "5.1", "KTBC")
    dvr.scheduled_jobs[:] = []
    dvr.clashes_changed()
    try:
        body = dvr.app.test_client().post("/schedule", json={"channel": "5.1", "duration": 30, "time": "20:15",
                                                             "days": ["Monday"]}).get_json()
        assert "Heads up" not in body["message"] and "clash_warning" not in body
    finally:
        dvr.scheduled_jobs[:] = []
        dvr.clashes_changed()


def test_settings_turn_off_srt_and_nfo(dvr, monkeypatch):
    import copy
    monkeypatch.setattr(dvr.config, "config", copy.deepcopy(dvr.config.config))
    saved = {}
    monkeypatch.setattr(dvr.config, "save_config", lambda: saved.update(dvr.config.config.get("recording", {})))
    monkeypatch.setattr(dvr, "_restart_soon", lambda: None)
    r = dvr.app.test_client().post("/api/setup/save", json={"hdhr_ip": "192.168.1.50", "captions": False, "nfo": False})
    assert r.status_code == 200
    assert saved["captions"] is False and saved["nfo"] is False
    page = dvr.app.test_client().get("/setup").get_data(as_text=True)
    assert 'id="nfo" />' in page and 'id="captions" />' in page      # unticked
    assert "LineDrive " + dvr.__version__ in page
