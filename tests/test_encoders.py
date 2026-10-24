import encoders


def test_cpu_args_match_the_old_profiles():
    assert encoders.video_args("cpu", 23) == ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    assert encoders.video_args("cpu", 23, encoders.DEINTERLACE_720P) == [
        "-vf", encoders.DEINTERLACE_720P, "-c:v", "libx264", "-preset", "fast", "-crf", "23"]


def test_card_args():
    nv = encoders.video_args("nvenc", 21)
    assert nv[:2] == ["-c:v", "h264_nvenc"] and nv[nv.index("-cq") + 1] == "21"
    qsv = encoders.video_args("qsv", 26, "scale=-2:720")
    assert qsv[:2] == ["-vf", "scale=-2:720,format=nv12"] and "h264_qsv" in qsv
    va = encoders.video_args("vaapi", 23, None, "/dev/dri/renderD129")
    assert va[:2] == ["-vaapi_device", "/dev/dri/renderD129"]
    assert va[va.index("-vf") + 1] == "format=nv12,hwupload"  # frames go to the card after CPU filters
    assert va[va.index("-qp") + 1] == "23"


def test_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(encoders, "_PROBED", {})
    assert encoders.choose("cpu") == ("cpu", None)
    assert encoders.choose("nonsense") == ("cpu", None)
    # No card in the test machine's /dev/dri path: VAAPI is refused without running ffmpeg
    enc, why = encoders.choose("vaapi", device="/nonexistent/renderD128")
    assert enc == "cpu" and "not found" in why


def test_probe_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(encoders, "_PROBED", {})

    class Done:
        returncode = 1
        stderr = ("[h264_nvenc @ 0x5b8a96a76080] Cannot load libcuda.so.1\n"
                  "[vost#0:0/h264_nvenc @ 0x5b8a] [enc:h264_nvenc @ 0x5b8b] Error while opening encoder\n"
                  "[out#0/null @ 0x5b8c] Nothing was written into output file\n")

    monkeypatch.setattr(encoders.subprocess, "run", lambda *a, **kw: calls.append(a) or Done())
    assert encoders.probe("nvenc") == (False, "Cannot load libcuda.so.1")
    assert encoders.probe("nvenc") == (False, "Cannot load libcuda.so.1")
    assert len(calls) == 1
    encoders.probe("nvenc", fresh=True)
    assert len(calls) == 2


def test_recording_uses_the_fallback(dvr, monkeypatch):
    monkeypatch.setattr(dvr.encoders, "_PROBED", {("nvenc", None): (False, "no card")})
    dvr.config.config.setdefault("recording", {}).update(encoder="nvenc", quality="standard")
    args, enc = dvr.video_encoding("ffmpeg")
    assert "libx264" in args and enc == "cpu"
    assert "NVIDIA graphics (NVENC) isn't working (no card); used the CPU." in [n["message"] for n in dvr.NOTICES]
    # Original quality copies the broadcast whatever the encoder
    dvr.config.config["recording"]["quality"] = "original"
    assert dvr.video_encoding("ffmpeg") == (["-c:v", "copy"], None)
    dvr.config.config["recording"].update(encoder="cpu", quality="standard")


class FakeFfmpeg:
    """Stands in for a recording ffmpeg: the GPU one fails with an encoder error, the CPU one works"""
    runs = []

    def __init__(self, cmd, **kw):
        import io
        FakeFfmpeg.runs.append(cmd)
        gpu = "h264_qsv" in cmd
        self.returncode = 1 if gpu else 0
        self.stderr = io.BytesIO(b"[h264_qsv @ 0x1] Error during encoding: device failed (-17)\n" if gpu else b"")
        self.stdin = io.BytesIO()
        self.stdout = None
        out = cmd[-1]
        with open(out, "wb") as f:
            f.write(b"x" * (2 * 1024 * 1024 if gpu and FakeFfmpeg.partial else 10))

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


def _record_with_failing_gpu(dvr, monkeypatch, tmp_path, partial):
    FakeFfmpeg.runs, FakeFfmpeg.partial = [], partial
    monkeypatch.setattr(dvr.subprocess, "Popen", FakeFfmpeg)
    monkeypatch.setattr(dvr.encoders, "_PROBED", {("qsv", None): (True, "ok")})
    dvr.config.config.setdefault("recording", {}).update(encoder="qsv", quality="standard", captions=False)
    path = str(tmp_path / "Show - S01E01.mp4")
    try:
        dvr._record_to_file("24.1", 30, 23, "fast", "mp4", "2026-10-28T19:30:00", path, "http://tuner/auto/v24.1")
    finally:
        dvr.config.config["recording"].update(encoder="cpu", captions=True)
    return path


def test_gpu_failure_retries_on_cpu_in_same_file(dvr, monkeypatch, tmp_path):
    path = _record_with_failing_gpu(dvr, monkeypatch, tmp_path, partial=False)
    assert ["h264_qsv" in r for r in FakeFfmpeg.runs] == [True, False]
    assert FakeFfmpeg.runs[1][-1] == path  # nothing worth keeping was recorded: same file
    assert dvr.encoders._PROBED[("qsv", None)][0] is False  # not used again until re-tested
    assert "failed while recording" in dvr.NOTICES[-1]["message"]


def test_gpu_failure_midway_keeps_the_first_part(dvr, monkeypatch, tmp_path):
    path = _record_with_failing_gpu(dvr, monkeypatch, tmp_path, partial=True)
    assert FakeFfmpeg.runs[1][-1] == str(tmp_path / "Show - S01E01 (part 2).mp4")
    assert dvr.os.path.getsize(path) == 2 * 1024 * 1024  # the GPU's part is kept
