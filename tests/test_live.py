import io
import os

import pytest

import live

A, B = "192.168.1.50", "192.168.1.51"


class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd = cmd
        self.returncode = None
        self.stderr = io.BytesIO(b"")
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def tv(tmp_path):
    clock = Clock()
    died = []
    t = live.LiveTV(str(tmp_path / "live"), popen=FakeProc, clock=clock,
                    explain=lambda tail: "No free tuner (all were in use)",
                    on_died=lambda s, reason: died.append((s.encoder, reason)))
    t.clock_, t.died_ = clock, died
    return t


def _start(tv, channel="24.1", box=A, encoder="cpu"):
    return tv.start(channel, box, f"http://{box}:5004/auto/v{channel}", "ffmpeg", ["-c:v", "libx264"], 2, encoder)


def test_command_makes_hls_from_the_tuner(tv):
    s = _start(tv)
    cmd = s.proc.cmd
    assert cmd[cmd.index("-i") + 1] == f"http://{A}:5004/auto/v24.1"
    assert cmd[cmd.index("-f") + 1] == "hls" and cmd[-1] == os.path.join(s.folder, "index.m3u8")
    assert "libx264" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    assert tv.holding() == {(A, "24.1")}


def test_viewer_limit(tv):
    _start(tv)
    _start(tv, "7.1")
    with pytest.raises(live.LiveError, match="2 people are already watching"):
        _start(tv, "4.1")


def test_heartbeats_keep_it_running_and_silence_stops_it(tv):
    s = _start(tv)
    tv.clock_.now += live.IDLE_SECONDS - 1
    assert tv.touch(s.id) == (True, None)
    tv.clock_.now += live.IDLE_SECONDS - 1
    tv.reap()
    assert s.id in tv.sessions
    tv.clock_.now += live.IDLE_SECONDS + 1
    tv.reap()
    assert s.id not in tv.sessions and s.proc.terminated and not os.path.exists(s.folder)
    running, reason = tv.touch(s.id)
    assert not running and "stopped checking in" in reason


def test_a_dead_stream_ends_the_session_and_says_why(tv):
    s = _start(tv, encoder="qsv")
    s.proc.returncode = 1
    running, reason = tv.touch(s.id)
    assert not running and reason == "The stream stopped: No free tuner (all were in use)"
    assert tv.died_ == [("qsv", "No free tuner (all were in use)")]


def test_a_recording_takes_the_longest_running_viewer_on_its_boxes(tv):
    first = _start(tv, "24.1", A)
    tv.clock_.now += 5
    _start(tv, "7.1", B)
    assert tv.stop_for_recording([B], "Abbott Elementary")["channel"] == "7.1"
    assert tv.stop_for_recording([B], "Abbott Elementary") is None  # nobody left on B
    assert tv.stop_for_recording(None, "News")["id"] == first.id
    assert tv.touch(first.id) == (False, "Stopped so the tuner could record News.")


def test_only_its_own_files_are_served(tv):
    s = _start(tv)
    with open(os.path.join(s.folder, "index.m3u8"), "w") as f:
        f.write("#EXTM3U\n")
    assert tv.file(s.id, "index.m3u8") == os.path.join(s.folder, "index.m3u8")
    assert tv.file(s.id, "seg00001.ts") is None  # not made yet
    assert tv.file(s.id, "../config.json") is None
    assert tv.file("../" + s.id, "index.m3u8") is None
    assert tv.file("0" * 32, "index.m3u8") is None
