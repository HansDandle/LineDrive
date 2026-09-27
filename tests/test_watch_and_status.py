import json
import time


def load_guide(dvr, guide):
    dvr.EPG_CACHE["data"] = [dict(p) for p in guide["programs"]]
    dvr.EPG_CACHE["timestamp"] = time.time()
    dvr.channels.clear()
    dvr.channels.update(guide["lineup"])
    dvr.scheduled_jobs[:] = []


def test_status_is_valid_json_with_a_watch(dvr, guide):
    load_guide(dvr, guide)
    dvr.add_watch("abbott elementary")
    body = dvr.app.test_client().get("/api/status").get_data(as_text=True)
    assert "Infinity" not in body and "NaN" not in body
    status = json.loads(body)
    assert [u["title"] for u in status["upcoming"] if u.get("watch")] == ["Abbott Elementary"]
    dvr.scheduled_jobs[:] = []


def test_watch_tolerates_typos(dvr, guide, monkeypatch):
    load_guide(dvr, guide)
    # Pretend the guide's Jeopardy! airings are in the future
    for p in dvr.EPG_CACHE["data"]:
        p["date"] = "2099-01-0" + str(1 + int(p["date"][-1]) % 9)
    dvr.add_watch("jeoprady")                       # misspelled
    dvr.add_watch("zzzz no such show")
    dvr.check_watchlist()
    watches = {j["query"]: j["status"] for j in dvr.scheduled_jobs if j.get("type") == "watch"}
    assert watches == {"jeoprady": "found", "zzzz no such show": "watching"}
    assert any(j.get("type") == "guide_series" and j["title"] == "Jeopardy!" for j in dvr.scheduled_jobs)
    dvr.scheduled_jobs[:] = []
