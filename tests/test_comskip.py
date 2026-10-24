import os
import shutil
import subprocess

import pytest

import comskip

EDL = """0.00\t2.50\t0
612.35\t792.10\t0
795.00\t801.00\t3
1500.20\t1503.00\t0
1650.00\t1830.40\t3
"""


def test_parse_edl():
    # A 2.5 s blip at the start and a 3 s one mid-show are noise; 792-795 is merged into one break
    assert comskip.parse_edl(EDL) == [(612.35, 801.0), (1650.0, 1830.4)]
    assert comskip.parse_edl("") == []
    assert comskip.parse_edl("garbage\n10 20 x\n") == []


def test_chapters_cover_the_whole_recording():
    breaks = [(612.35, 801.0), (1650.0, 1830.4)]
    assert comskip.chapters(breaks, 1800.0 + 60) == [
        (0.0, 612.35, "Show"), (612.35, 801.0, "Commercial"), (801.0, 1650.0, "Show"),
        (1650.0, 1830.4, "Commercial"), (1830.4, 1860.0, "Show")]
    # A break at the very start, and no duration known
    assert comskip.chapters([(0.0, 30.0)]) == [(0.0, 30.0, "Commercial")]
    assert comskip.chapters([], 100.0) == [(0.0, 100.0, "Show")]


def test_ffmetadata():
    text = comskip.ffmetadata([(0.0, 61.5, "Show"), (61.5, 120.0, "Commercial")])
    assert text.startswith(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=61500\ntitle=Show\n")
    assert "START=61500\nEND=120000\ntitle=Commercial" in text


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_add_chapters(tmp_path):
    video = str(tmp_path / "show.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10", "-t", "30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", video], check=True)
    assert comskip.add_chapters(video, [(10.0, 20.0)]) == 1
    out = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "csv=p=0", video],
                         capture_output=True, text=True).stdout
    assert [line.split(",")[-1] for line in out.strip().splitlines()] == ["Show", "Commercial", "Show"]
    assert [p.name for p in tmp_path.iterdir()] == ["show.mp4"]  # no temp files left
    # .ts can't carry chapters: left alone
    assert comskip.add_chapters(str(tmp_path / "x.ts"), [(1.0, 9.0)]) == 0


def test_cut_check():
    assert comskip.cut_check([(100.0, 280.0)], 1800.0) is None
    assert "ads" in comskip.cut_check([(0.0, 1000.0)], 1800.0)  # 56% "ads": Comskip got it wrong
    assert comskip.cut_check([], 1800.0) == "no ad breaks found"
    assert "length" in comskip.cut_check([(100.0, 280.0)], None)


def test_shift_srt():
    srt = ("1\n00:00:05,000 --> 00:00:07,500\nBefore the break\n\n"
           "2\n00:01:05,000 --> 00:01:06,000\nAn ad\n\n"
           "3\n00:03:10,250 --> 00:03:12,000\nAfter the break\n")
    out = comskip.shift_srt(srt, [(60.0, 180.0)])
    assert out == ("1\n00:00:05,000 --> 00:00:07,500\nBefore the break\n\n"
                   "2\n00:01:10,250 --> 00:01:12,000\nAfter the break\n")


def _test_video(path, seconds=60):
    # a keyframe every second, like a real cut point would have nearby
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", str(seconds), "-c:v", "libx264", "-g", "10",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path], check=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_cut_ads(tmp_path):
    import cleanup
    root = tmp_path / "recordings"
    show = root / "TV" / "Show" / "Season 01"
    show.mkdir(parents=True)
    video = str(show / "Show - S01E01.mp4")
    _test_video(video)
    (show / "Show - S01E01.en.srt").write_text("1\n00:00:50,000 --> 00:00:51,000\nHi\n", encoding="utf-8")
    (show / "Show - S01E01.edl").write_text("20.0\t35.0\t0\n", encoding="utf-8")
    removed = comskip.cut_ads(video, [(20.0, 35.0)],
                              keep_original=lambda p: cleanup.recycle(p, str(root), keep_sidecars=True))
    assert 13 <= removed <= 16
    assert 44 <= comskip.duration_of(video) <= 47
    # captions moved 15 s earlier, the .edl (times for the uncut file) is gone
    assert "00:00:35,000 --> 00:00:36,000" in (show / "Show - S01E01.en.srt").read_text(encoding="utf-8")
    assert sorted(p.name for p in show.iterdir()) == ["Show - S01E01.en.srt", "Show - S01E01.mp4"]
    # the uncut original, with its untouched captions and .edl, waits in the recycle folder
    kept = root / ".deleted" / "TV" / "Show" / "Season 01"
    assert sorted(p.name for p in kept.iterdir()) == ["Show - S01E01.edl", "Show - S01E01.en.srt", "Show - S01E01.mp4"]
    assert 59 <= comskip.duration_of(str(kept / "Show - S01E01.mp4")) <= 61


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_cut_ads_refuses_when_it_looks_wrong(tmp_path):
    video = str(tmp_path / "show.mp4")
    _test_video(video, 30)
    with pytest.raises(RuntimeError, match="not cutting"):
        comskip.cut_ads(video, [(0.0, 25.0)], keep_original=lambda p: pytest.fail("touched the original"))
    assert 29 <= comskip.duration_of(video) <= 31
    assert [p.name for p in tmp_path.iterdir()] == ["show.mp4"]


def test_comskip_off_by_default_and_queue_needs_binary(dvr, monkeypatch):
    assert dvr.config.get("recording", "comskip", False) is False
    monkeypatch.setattr(dvr, "comskip_bin", lambda: None)
    assert dvr.queue_comskip("/recordings/TV/x.mp4") is False
