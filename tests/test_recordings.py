import os
from datetime import datetime

STARTED = datetime(2026, 9, 26, 22, 29)


def test_names_follow_media_server_conventions(dvr):
    snl = {"title": "Saturday Night Live", "episode_title": "Jalen Brunson; KATSEYE", "season_number": "52", "episode_number": "1"}
    assert dvr.recording_basename(snl, STARTED) == "Saturday Night Live - S52E01 - Jalen Brunson; KATSEYE"
    news = {"title": "KXAN News at 10PM Saturday"}
    assert dvr.recording_basename(news, STARTED) == "KXAN News at 10PM Saturday - 2026-09-26"
    movie = {"title": "The Graduate", "genre": "Movie", "year": "1967"}
    assert dvr.recording_basename(movie, STARTED) == "The Graduate (1967)"
    unsafe = {"title": "CSI: Vegas?", "episode_title": 'Who/What "Now"...', "season_number": "3", "episode_number": "4"}
    assert dvr.recording_basename(unsafe, STARTED) == "CSI Vegas - S03E04 - Who-What Now"


def test_folders(dvr):
    root = dvr.SAVE_DIR
    assert dvr.recording_folder({"title": "Saturday Night Live", "season_number": "52"}) == \
        os.path.join(root, "TV", "Saturday Night Live", "Season 52")
    assert dvr.recording_folder({"title": "KXAN News"}) == os.path.join(root, "TV", "KXAN News")
    assert dvr.recording_folder({"title": "Heat", "genre": "Movie", "year": "1995"}) == os.path.join(root, "Movies", "Heat (1995)")
    assert dvr.recording_folder(None) == os.path.join(root, "Other")


def test_already_recorded_matches_number_or_title(dvr):
    season = os.path.join(dvr.SAVE_DIR, "TV", "Saturday Night Live", "Season 51")
    os.makedirs(season, exist_ok=True)
    open(os.path.join(season, "Saturday Night Live - S51E04 - Miles Teller.mp4"), "w").close()
    dvr._LIBRARY_CACHE["at"] = 0
    have = lambda **p: dvr.already_recorded(dict({"title": "Saturday Night Live"}, **p))
    assert have(season_number="51", episode_number="4")
    assert have(episode_title="Miles Teller")
    assert not have(season_number="52", episode_number="1", episode_title="Jalen Brunson; KATSEYE")
    assert not have(episode_title="Saturday Night Live")       # a bare show name isn't an episode
    assert not dvr.already_recorded({"title": "KXAN News"})     # no episode info: always record


def test_unique_path_never_overwrites(dvr, tmp_path):
    open(tmp_path / "Show.mp4", "w").close()
    assert dvr._unique_path(str(tmp_path), "Show", ".mp4").endswith("Show (2).mp4")
