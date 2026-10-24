import gzip
from datetime import datetime, timezone

import epg_xmltv

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="BBCOne.uk"><display-name>BBC One HD</display-name><lcn>101</lcn></channel>
  <channel id="ITV1.uk"><display-name>ITV1</display-name></channel>
  <channel id="kvue.us"><display-name>24.1 KVUE</display-name></channel>
  <channel id="Dave.uk"><display-name>Dave</display-name></channel>
  <channel id="Other.uk"><display-name>Something Else</display-name></channel>
  <programme start="20261024190000 +0100" stop="20261024200000 +0100" channel="BBCOne.uk">
    <title>Strictly Come Dancing</title><sub-title>Week 5</sub-title><desc>Ballroom.</desc>
    <category>Entertainment</category><episode-num system="xmltv_ns">23.4.0/1</episode-num>
    <new/><icon src="http://img/strictly.jpg"/>
  </programme>
  <programme start="20261024200000 +0100" stop="20261024223000 +0100" channel="ITV1.uk">
    <title>Live Premier League Football</title><category>Sport</category>
    <episode-num system="onscreen">S2026E10</episode-num><live/>
  </programme>
  <programme start="20261024100000 +0100" stop="20261024110000 +0100" channel="ITV1.uk">
    <title>Already Over</title>
  </programme>
  <programme start="20261024210000 +0100" stop="20261024220000 +0100" channel="Dave.uk">
    <title>Taskmaster</title><previously-shown/><date>20201015</date>
  </programme>
  <programme start="20261024180000 -0500" stop="20261024183000 -0500" channel="kvue.us">
    <title>KVUE News</title>
  </programme>
  <programme start="20261024180000 +0000" stop="20261024190000 +0000" channel="Other.uk">
    <title>Not On My Tuner</title>
  </programme>
</tv>"""

LINEUP = {"101": "BBC ONE", "103": "ITV 1", "19": "Dave", "24.1": "KVUE-DT", "50": "QVC"}


def test_channels_match_by_number_name_or_map():
    xml_channels, _ = epg_xmltv.read(FEED)
    mapping = epg_xmltv.match_channels(xml_channels, LINEUP)
    assert mapping["BBCOne.uk"] == ["101"]        # its <lcn>
    assert mapping["ITV1.uk"] == ["103"]          # "ITV1" = "ITV 1"
    assert mapping["kvue.us"] == ["24.1"]         # "24.1 KVUE"
    assert mapping["Dave.uk"] == ["19"]
    assert "Other.uk" not in mapping
    assert epg_xmltv.match_channels(xml_channels, LINEUP, {"Other.uk": "50"})["Other.uk"] == ["50"]


def test_listings(monkeypatch):
    monkeypatch.setattr(epg_xmltv, "_local_tz", lambda: timezone.utc)
    found, report = epg_xmltv.listings(FEED, LINEUP, now=NOW)
    by_title = {p["title"]: p for p in found}
    assert "Already Over" not in by_title and "Not On My Tuner" not in by_title
    strictly = by_title["Strictly Come Dancing"]
    assert (strictly["channel_number"], strictly["date"], strictly["time"], strictly["duration"]) == \
        ("101", "2026-10-24", "06:00 PM", 60)
    assert (strictly["season_number"], strictly["episode_number"], strictly["episode_title"]) == ("24", "5", "Week 5")
    assert strictly["flags"] == ["New"] and strictly["image"] == "http://img/strictly.jpg"
    football = by_title["Live Premier League Football"]
    assert "Sports" in football["genre"] and football["flags"] == ["Live"]
    assert (football["season_number"], football["episode_number"]) == ("2026", "10")
    taskmaster = by_title["Taskmaster"]
    assert taskmaster["flags"] == [] and taskmaster["original_air_date"] == "2020-10-15"  # a repeat
    assert by_title["KVUE News"]["time"] == "11:00 PM"  # 6 PM US Central
    assert report == {"matched": 4, "unmatched": ["50 QVC"]}


def test_a_feed_without_new_or_repeat_marks_leaves_flags_unknown(monkeypatch):
    monkeypatch.setattr(epg_xmltv, "_local_tz", lambda: timezone.utc)
    plain = FEED.replace(b"<new/>", b"").replace(b"<live/>", b"").replace(b"<previously-shown/>", b"")
    found, _ = epg_xmltv.listings(plain, LINEUP, now=NOW)
    assert found and all("flags" not in p for p in found)


def test_load_reads_gzipped_files(tmp_path):
    path = tmp_path / "guide.xml.gz"
    path.write_bytes(gzip.compress(FEED))
    assert epg_xmltv.load(str(path)) == FEED
