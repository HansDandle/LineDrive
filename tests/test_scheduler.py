from datetime import datetime, timedelta

SNL = {"type": "recurring_series", "status": "active", "title": "Saturday Night Live", "channel_number": "36.1",
       "time": "10:29 PM", "duration": "94", "recurrence": {"days": ["Saturday"], "time": "10:29 PM"}}
SAT = datetime(2026, 9, 26)


def due(dvr, jobs, when):
    return [j["title"] for j, _ in dvr.find_due_jobs(jobs, when)]


def test_series_fires_on_time_and_late_but_not_early(dvr):
    assert due(dvr, [dict(SNL)], SAT.replace(hour=22, minute=28, second=59)) == []
    assert due(dvr, [dict(SNL)], SAT.replace(hour=22, minute=29, second=1)) == ["Saturday Night Live"]
    # A slow loop or a restart still starts it within the grace window
    assert due(dvr, [dict(SNL)], SAT.replace(hour=22, minute=33)) == ["Saturday Night Live"]
    assert due(dvr, [dict(SNL)], SAT.replace(hour=22, minute=35)) == []


def test_series_respects_days_and_status(dvr):
    assert due(dvr, [dict(SNL)], datetime(2026, 9, 25, 22, 29, 30)) == []           # Friday
    assert due(dvr, [dict(SNL, status="paused")], SAT.replace(hour=22, minute=29, second=5)) == []


def test_started_slot_is_not_repeated(dvr):
    job = dict(SNL, last_started_at=SAT.replace(hour=22, minute=29, second=2).isoformat())
    assert due(dvr, [job], SAT.replace(hour=22, minute=30)) == []
    # ...but an old start (last week) doesn't block this week
    job = dict(SNL, last_started_at=(SAT - timedelta(days=7)).replace(hour=22, minute=29).isoformat())
    assert due(dvr, [job], SAT.replace(hour=22, minute=29, second=5)) == ["Saturday Night Live"]


def test_late_night_slot_seen_after_midnight(dvr):
    late = {"type": "recurring_series", "status": "active", "title": "Late", "time": "11:58 PM",
            "recurrence": {"days": ["Sat"]}}
    assert due(dvr, [late], datetime(2026, 9, 27, 0, 1)) == ["Late"]


def test_one_off_episode(dvr):
    one = {"status": "scheduled", "title": "Once", "date": "2026-09-27", "time": "19:00"}
    assert due(dvr, [dict(one)], datetime(2026, 9, 27, 19, 0, 2)) == ["Once"]
    assert due(dvr, [dict(one, time="7:00 PM")], datetime(2026, 9, 27, 19, 2)) == ["Once"]
    assert due(dvr, [dict(one, status="recording")], datetime(2026, 9, 27, 19, 1)) == []


def test_next_job_id_never_reuses(dvr):
    dvr.scheduled_jobs[:] = [{"id": 8}, {"id": 2}]
    assert dvr.next_job_id() == 9
    dvr.scheduled_jobs[:] = []


def interrupted(dvr, jobs, when, padding=lambda c, s: 0):
    return [(j["title"], started) for j, _slot, _end, started in dvr.interrupted_jobs(jobs, when, padding)]


def test_restart_mid_recording_resumes(dvr):
    started = dict(SNL, last_started_at=SAT.replace(hour=22, minute=29, second=3).isoformat())
    # Restarted an hour in: record the rest
    assert interrupted(dvr, [started], SAT.replace(hour=23, minute=30)) == [("Saturday Night Live", True)]
    # Restarted two minutes in, still inside the scheduler's grace window: it isn't started again by that
    assert interrupted(dvr, [started], SAT.replace(hour=22, minute=31)) == [("Saturday Night Live", True)]
    # Nearly over, or already over
    assert interrupted(dvr, [started], datetime(2026, 9, 27, 0, 2)) == []
    assert interrupted(dvr, [started], datetime(2026, 9, 27, 0, 10)) == []


def test_missed_start_is_picked_up_after_the_grace_window(dvr):
    never = dict(SNL, last_started_at=(SAT - timedelta(days=7)).replace(hour=22, minute=29).isoformat())
    assert interrupted(dvr, [never], SAT.replace(hour=22, minute=31)) == []  # the scheduler handles this one
    assert interrupted(dvr, [never], SAT.replace(hour=22, minute=50)) == [("Saturday Night Live", False)]
    assert interrupted(dvr, [never], datetime(2026, 9, 25, 22, 50)) == []    # Friday: not a recording day


def test_resume_counts_sports_padding(dvr):
    started = dict(SNL, last_started_at=SAT.replace(hour=22, minute=29).isoformat())
    # 94 min ends 12:03 AM; with 30 min of padding it's still worth resuming at 12:10
    assert interrupted(dvr, [started], datetime(2026, 9, 27, 0, 10)) == []
    assert interrupted(dvr, [started], datetime(2026, 9, 27, 0, 10), lambda c, s: 30) == [("Saturday Night Live", True)]


def test_one_time_recording_resumes(dvr):
    job = {"type": "one_time", "status": "recording", "title": "Jeopardy!", "channel_number": "36.1",
           "date": "2026-09-28", "time": "03:30 PM", "duration": 30, "last_started_at": "2026-09-28T15:30:01"}
    assert interrupted(dvr, [job], datetime(2026, 9, 28, 15, 45)) == [("Jeopardy!", True)]
    assert interrupted(dvr, [dict(job, status="completed")], datetime(2026, 9, 28, 15, 45)) == []
