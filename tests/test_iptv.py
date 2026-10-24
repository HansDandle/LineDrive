import iptv

PLAYLIST = """#EXTM3U url-tvg="http://guide.example/epg.xml.gz,http://backup/epg.xml"
#EXTINF:-1 tvg-id="news.us" tvg-chno="24.1" tvg-logo="http://logo/news.png" group-title="News",News 24
http://iptv.example/live/news.m3u8
#EXTINF:-1 tvg-id="movies.us" group-title="Movies",Movie Channel
http://iptv.example/live/movies.ts
#EXTVLCOPT:http-user-agent=Something
#EXTINF:-1 tvg-id="" tvg-chno="77" group-title="Sports",Sports Live
http://iptv.example/live/sports.ts
"""


def test_parse():
    header, entries = iptv.parse(PLAYLIST)
    assert header["url-tvg"].startswith("http://guide.example/")
    assert [(e["name"], e["tvg_id"], e["tvg_chno"], e["group"]) for e in entries] == [
        ("News 24", "news.us", "24.1", "News"), ("Movie Channel", "movies.us", "", "Movies"),
        ("Sports Live", "", "77", "Sports")]
    assert entries[1]["url"] == "http://iptv.example/live/movies.ts"


def test_numbers_avoid_the_antenna_lineup():
    _, entries = iptv.parse(PLAYLIST)
    taken = {"24.1", "7.1"}  # the HDHomeRun already has 24.1
    numbered = iptv.number(entries, 1, taken)
    assert [e["number"] for e in numbered] == ["1001", "1002", "77"]
    assert {"1001", "1002", "77"} <= taken


def test_sources(tmp_path, monkeypatch):
    path = tmp_path / "list.m3u"
    path.write_text(PLAYLIST, encoding="utf-8")
    out = iptv.channels([{"name": "Provider", "m3u": str(path), "groups": ["News", "Sports"]},
                         {"name": "Empty"}], set())
    assert len(out) == 1
    source, box, guide, entries = out[0]
    assert box == "iptv:Provider" and guide == "http://guide.example/epg.xml.gz"
    assert [e["name"] for e in entries] == ["News 24", "Sports Live"]


def test_an_iptv_source_is_a_box_whose_tuners_are_its_streams(dvr, monkeypatch):
    box = "iptv:Provider"
    monkeypatch.setattr(dvr, "IPTV_LIMITS", {box: 2})
    monkeypatch.setattr(dvr, "IPTV_URLS", {"1001": "http://iptv.example/live/news.m3u8"})
    monkeypatch.setitem(dvr.channels, "1001", "News 24")
    monkeypatch.setattr(dvr, "ACTIVE_RECORDINGS", {"x.mp4": {"channel_number": "1001", "box": box}})
    status = dvr._box_status(box)
    assert [s["VctNumber"] for s in status] == ["1001", ""]
    assert dvr.stream_url(box, "1001") == "http://iptv.example/live/news.m3u8"
    assert dvr.stream_url("192.168.1.50", "24.1") == "http://192.168.1.50:5004/auto/v24.1"


def test_a_recording_takes_the_only_stream_from_live_tv(dvr, monkeypatch, tmp_path):
    """One login, one stream: someone watching an IPTV channel in LineDrive is stopped so a
    recording on another of the provider's channels can start, never two streams at once."""
    import live
    from test_live import FakeProc
    box = "iptv:Provider"
    monkeypatch.setattr(dvr, "IPTV_LIMITS", {box: 1})
    monkeypatch.setattr(dvr, "IPTV_URLS", {"1001": "http://iptv.example/news", "1002": "http://iptv.example/sports"})
    monkeypatch.setattr(dvr, "ALL_BOXES", [box])
    monkeypatch.setattr(dvr, "BOX_TUNERS", {})
    monkeypatch.setattr(dvr, "ACTIVE_RECORDINGS", {})
    for num, name in (("1001", "News 24"), ("1002", "Sports Live")):
        monkeypatch.setitem(dvr.channels, num, name)
        monkeypatch.setitem(dvr.CHANNEL_BOXES, num, [box])
    tv = live.LiveTV(str(tmp_path / "live"), popen=FakeProc)
    monkeypatch.setattr(dvr, "LIVE", tv)
    monkeypatch.setattr(dvr.t, "sleep", lambda s: None)
    watching = tv.start("1001", box, dvr.IPTV_URLS["1001"], "ffmpeg", [], 2)
    assert "IPTV provider's stream is in use" in dvr.no_tuner_message("1002")
    assert dvr.make_room("1002", "The Game") is None       # free now
    assert watching.proc.terminated and not tv.sessions
    assert "record The Game" in tv.ended[watching.id][0]  # what the viewer's player is told
