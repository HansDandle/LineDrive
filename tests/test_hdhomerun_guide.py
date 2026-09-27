from datetime import datetime

import epg_hdhomerun as sd

# Two real listings from SiliconDust's guide for an Austin tuner (times are UTC epoch seconds)
RAW = [
    {"GuideNumber": "36.1", "GuideName": "KXANDT", "Affiliate": "NBC", "Guide": [
        {"StartTime": 1790479740, "EndTime": 1790485380, "First": 1, "Title": "Saturday Night Live",
         "EpisodeNumber": "S52E01", "EpisodeTitle": "Jalen Brunson; KATSEYE", "OriginalAirdate": 1790380800,
         "SeriesID": "C184186ENG0VF", "ImageURL": "https://img.hdhomerun.com/titles/C184186ENG0VF.jpg",
         "Filter": ["Comedy"]},
    ]},
    {"GuideNumber": "4.1", "GuideName": "WOAI", "Affiliate": "NBC", "Guide": [
        {"StartTime": 1790479800, "EndTime": 1790481600, "Title": "News 4 San Antonio",
         "OriginalAirdate": 1790380800, "SeriesID": "C1", "Filter": ["News"]},
    ]},
]


def parsed(monkeypatch):
    monkeypatch.setattr(sd, "_local_tz", lambda: __import__("pytz").timezone("America/Chicago"))
    return sd.parse_hdhomerun_guide(RAW)


def test_parse(monkeypatch):
    snl = parsed(monkeypatch)[0]
    assert (snl["date"], snl["time"], snl["duration"]) == ("2026-09-26", "10:29 PM", 94)
    assert (snl["season_number"], snl["episode_number"], snl["episode_id"]) == ("52", "1", "S52E01")
    assert snl["original_air_date"] == "2026-09-26" and snl["first_run"] and snl["flags"] == ["New"]
    assert snl["series_id"] == "C184186ENG0VF" and snl["image"].endswith(".jpg")
    assert snl["channel"] == "KXANDT NBC (36.1)" and snl["genre"] == "Comedy"


def test_merge_enriches_gracenote_and_fills_missing_channels(monkeypatch):
    gracenote = [{"channel_number": "36.1", "date": "2026-09-26", "time": "10:29 PM", "title": "Saturday Night Live",
                  "episode_title": "Jalen Brunson; KATSEYE", "flags": ["New"], "original_air_date": ""}]
    merged = sd.merge_guides(gracenote, parsed(monkeypatch), now=datetime(2026, 9, 26, 22, 0))
    snl = next(p for p in merged if p["channel_number"] == "36.1")
    assert snl["series_id"] == "C184186ENG0VF" and snl["original_air_date"] == "2026-09-26"
    assert snl.get("source") != "hdhomerun"  # still Gracenote's listing, enriched
    # 4.1 has no Gracenote listings, so SiliconDust's are used
    assert [p["title"] for p in merged if p["channel_number"] == "4.1"] == ["News 4 San Antonio"]
    # Merging again (the next refresh) replaces SiliconDust-only listings instead of duplicating them
    again = sd.merge_guides(merged, parsed(monkeypatch), now=datetime(2026, 9, 26, 22, 0))
    assert len([p for p in again if p["channel_number"] == "4.1"]) == 1


def test_original_air_date_marks_new(dvr):
    assert dvr.is_new_listing({"flags": [], "original_air_date": "2026-09-26", "date": "2026-09-26"})
    assert not dvr.is_new_listing({"flags": [], "original_air_date": "2019-03-02", "date": "2026-09-26"})
    assert dvr.is_new_listing({"flags": [], "first_run": True})
