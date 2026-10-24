from datetime import datetime

import sonarr

SERIES = [
    {"id": 1, "title": "Abbott Elementary", "alternateTitles": []},
    {"id": 2, "title": "Ghosts (US)", "alternateTitles": []},
    {"id": 3, "title": "Ghosts (UK)", "alternateTitles": []},
    {"id": 4, "title": "Law & Order: Special Victims Unit", "alternateTitles": [{"title": "Law & Order: SVU"}]},
]

EPISODES = {
    1: [
        {"id": 101, "seasonNumber": 5, "episodeNumber": 9, "title": "Field Trip", "airDate": "2026-10-22",
         "monitored": True, "hasFile": False},
        {"id": 102, "seasonNumber": 5, "episodeNumber": 10, "title": "Parent Night", "airDate": "2026-10-29",
         "monitored": True, "hasFile": False},
        {"id": 100, "seasonNumber": 0, "episodeNumber": 1, "title": "Special", "airDate": "2026-10-22",
         "monitored": False, "hasFile": False},
    ],
    2: [{"id": 201, "seasonNumber": 5, "episodeNumber": 3, "title": "The Party", "airDate": "2026-10-23",
         "monitored": True, "hasFile": True}],
    3: [{"id": 301, "seasonNumber": 2, "episodeNumber": 1, "title": "Gone Girl", "airDate": "2019-04-15",
         "monitored": True, "hasFile": False}],
    4: [],
}


def test_norm():
    assert sonarr.norm("The Office (US)") == "office"
    assert sonarr.norm("Law & Order: SVU") == "law and order svu"
    assert sonarr.norm(None) == ""


def test_series_matches():
    assert [s["id"] for s in sonarr.series_matches(SERIES, "Ghosts")] == [2, 3]
    assert [s["id"] for s in sonarr.series_matches(SERIES, "Law & Order: SVU")] == [4]
    assert sonarr.series_matches(SERIES, "Jeopardy!") == []
    assert sonarr.series_matches(SERIES, "") == []


def test_find_episode():
    eps = EPISODES[1]
    assert sonarr.find_episode(eps, "5", "9")["id"] == 101
    # No numbers from the guide: the one regular episode that aired that day (specials ignored)
    assert sonarr.find_episode(eps, "", "", "2026-10-22")["id"] == 101
    assert sonarr.find_episode(eps, None, None, "2026-10-01", "Parent night")["id"] == 102
    assert sonarr.find_episode(eps, "", "", "2026-10-01", "Something Else") is None
    # Same number, different title: another show of the same name (an old series' rerun)
    assert sonarr.find_episode(eps, "5", "9", None, "My Bed Banter & Beyond") is None
    assert sonarr.find_episode(eps, "5", "9", None, "Field Trip")["id"] == 101
    assert sonarr.find_episode(eps, "", "", "2026-10-22", "My Bed Banter & Beyond") is None


class FakeSonarr(sonarr.Sonarr):
    def __init__(self):
        super().__init__("http://sonarr:8989", "key")
        self.unmonitored = []

    def _get(self, path, **params):
        return SERIES if path == "/series" else EPISODES[params["seriesId"]]


def test_handoff(monkeypatch):
    s = FakeSonarr()

    class Ok:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(sonarr.requests, "put",
                        lambda url, json, **kw: s.unmonitored.extend(json["episodeIds"]) or Ok())
    assert s.handoff("Abbott Elementary", "5", "9") == (
        True, "Unmonitored Abbott Elementary S05E09 in Sonarr so it won't download it")
    assert s.unmonitored == [101]
    # Sonarr already downloaded it: leave it be
    assert s.handoff("Ghosts", "5", "3")[0] is False
    # Same title in two regions: the one whose episode matches wins
    assert s.handoff("Ghosts", "", "", "2019-04-15") == (
        True, "Unmonitored Ghosts (UK) S02E01 in Sonarr so it won't download it")
    assert s.handoff("Jeopardy!", "", "") == (False, "Jeopardy! isn't in Sonarr")
    assert s.handoff("Law & Order: SVU", "27", "4")[0] is False
    assert s.unmonitored == [101, 301]


def test_handoff_skips_movies_and_unconfigured(dvr, monkeypatch):
    calls = []
    monkeypatch.setattr(dvr.sonarr.Sonarr, "handoff", lambda self, *a: calls.append(a) or (True, "done"))
    started = datetime(2026, 10, 22, 19, 0)
    dvr.config.config["sonarr"] = {}
    dvr.sonarr_handoff({"title": "Abbott Elementary"}, started)
    dvr.config.config["sonarr"] = {"url": "http://sonarr:8989", "api_key": "key"}
    dvr.sonarr_handoff({"title": "Dune", "genre": "Movie"}, started)
    dvr.sonarr_handoff({"title": "College Football", "genre": "Sports"}, started)
    assert calls == []
    dvr.sonarr_handoff({"title": "Abbott Elementary", "season_number": "5", "episode_number": "9"}, started)
    assert calls == [("Abbott Elementary", "5", "9", "2026-10-22", None)]
    assert dvr.NOTICES[-1]["message"] == "done."
    dvr.config.config.pop("sonarr")
