"""Video encoders for recordings: the CPU (libx264) or a graphics card.

recording.encoder picks one: 'cpu' (default), 'nvenc' (NVIDIA), 'qsv' (Intel Quick Sync) or
'vaapi' (Intel/AMD on Linux). The tuner's MPEG-2 is still decoded on the CPU, which is cheap; the
card does the expensive part, the H.264 encode. Each card encoder is tried with a one-second test
encode before it's trusted, and a recording falls back to the CPU when the chosen one doesn't work
on this machine (no card, no driver, or the device isn't passed into the container).
"""
import os
import re
import subprocess
import threading

ENCODERS = {
    'cpu':   'CPU (works everywhere)',
    'nvenc': 'NVIDIA graphics (NVENC)',
    'qsv':   'Intel graphics (Quick Sync)',
    'vaapi': 'Intel or AMD graphics (VAAPI, Linux)',
}
VAAPI_DEVICE = '/dev/dri/renderD128'
DEINTERLACE_720P = 'bwdif=mode=send_frame:deint=interlaced,scale=-2:720'


def video_args(encoder, crf, vf=None, device=None):
    """ffmpeg arguments for the video of a recording. crf is libx264's quality number (lower is
    better); each card encoder gets its closest equivalent, so sizes come out similar but not
    identical. vf: a CPU filter chain to run first (e.g. the 720p deinterlace and scale)."""
    if encoder == 'nvenc':
        args = ['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', str(crf), '-b:v', '0']
        return (['-vf', vf] if vf else []) + args
    if encoder == 'qsv':
        args = ['-c:v', 'h264_qsv', '-preset', 'medium', '-global_quality', str(crf), '-look_ahead', '0']
        return ['-vf', (vf + ',' if vf else '') + 'format=nv12'] + args
    if encoder == 'vaapi':
        # Frames are uploaded to the card after the CPU filters; -qp is a fixed quantizer, which
        # every VAAPI driver supports (constant-quality modes vary by card)
        return ['-vaapi_device', device or VAAPI_DEVICE,
                '-vf', (vf + ',' if vf else '') + 'format=nv12,hwupload',
                '-c:v', 'h264_vaapi', '-rc_mode', 'CQP', '-qp', str(crf)]
    return (['-vf', vf] if vf else []) + ['-c:v', 'libx264', '-preset', 'fast', '-crf', str(crf)]


_PROBED = {}
_LOCK = threading.Lock()


def probe(encoder, ffmpeg='ffmpeg', device=None, fresh=False):
    """(works, reason): a one-second 720p test encode with this encoder. Cached until fresh=True."""
    if encoder == 'cpu':
        return True, 'ok'
    key = (encoder, device)
    with _LOCK:
        if not fresh and key in _PROBED:
            return _PROBED[key]
    if encoder == 'vaapi' and not os.path.exists(device or VAAPI_DEVICE):
        result = (False, f"{device or VAAPI_DEVICE} not found (pass /dev/dri into the container)")
    else:
        cmd = [ffmpeg, '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30',
               '-t', '1'] + video_args(encoder, 23, device=device) + ['-f', 'null', '-']
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            # ffmpeg's first error is the cause ("Cannot load libcuda.so.1"); the rest is fallout
            lines = [re.sub(r'^(\[[^\]]*@ [0-9a-fA-Fx]+\]\s*)+', '', line).strip()
                     for line in (proc.stderr or '').splitlines() if line.strip()]
            result = (True, 'ok') if proc.returncode == 0 else (False, (lines[0] if lines else 'failed')[:200])
        except (OSError, subprocess.SubprocessError) as e:
            result = (False, str(e)[:200])
    with _LOCK:
        _PROBED[key] = result
    return result


def mark_broken(encoder, device=None, reason='failed'):
    """Treat an encoder as not working (it failed for real) until it's probed fresh"""
    with _LOCK:
        _PROBED[(encoder, device)] = (False, reason[:200])


def choose(encoder, ffmpeg='ffmpeg', device=None):
    """(encoder to use, reason it isn't the one asked for or None)"""
    if encoder not in ENCODERS:
        encoder = 'cpu'
    works, reason = probe(encoder, ffmpeg, device)
    return (encoder, None) if works else ('cpu', f"{ENCODERS[encoder]} isn't working ({reason}); used the CPU")
