"""Commercial marking with Comskip.

After a recording finishes, Comskip finds the ad breaks. LineDrive keeps its .edl beside the
recording (Kodi reads it) and writes the breaks into the file as chapters: 'Show', 'Commercial',
'Show', ... Only the container is rewritten (stream copy), so the picture is never re-encoded or
cut, and a break Comskip got wrong costs nothing but a misplaced chapter. Jellyfin 10.10+ turns
'Commercial' chapters into skippable segments with its Chapter Segments plugin.

recording.comskip_mode 'cut' removes the breaks instead, for players that can't skip chapters
(Plex, Emby). The uncut original is kept in the recycle folder for a week, and a recording where
Comskip's answer looks wrong is given chapters instead of being cut.
"""
import os
import re
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INI = os.path.join(HERE, 'comskip.ini')
SHOW, COMMERCIAL = 'Show', 'Commercial'
# Chapters (a container feature) only go into these; other formats just get the .edl
CHAPTER_FORMATS = ('.mp4', '.m4v', '.mkv')
MIN_BREAK_SECONDS = 5


def parse_edl(text):
    """[(start, end)] seconds of each ad break in a Comskip/MPlayer .edl ('start end action'
    lines; action 0 = cut, 3 = commercial break), merged and in order"""
    breaks = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            start, end = float(parts[0]), float(parts[1])
            action = int(float(parts[2])) if len(parts) > 2 else 0
        except ValueError:
            continue
        if action in (0, 3) and end - start >= MIN_BREAK_SECONDS:
            breaks.append((max(start, 0.0), end))
    merged = []
    for start, end in sorted(breaks):
        # a few seconds of 'show' between two breaks is a bumper or a misread, not the show
        if merged and start <= merged[-1][1] + MIN_BREAK_SECONDS:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def chapters(breaks, duration=None):
    """[(start, end, title)] covering the whole recording, alternating Show/Commercial"""
    end_of_file = max(duration or 0, breaks[-1][1] if breaks else 0)
    out, at = [], 0.0
    for start, end in breaks:
        end = min(end, end_of_file)
        if start - at >= 1:
            out.append((at, start, SHOW))
        if end > start:
            out.append((start, end, COMMERCIAL))
        at = end
    if end_of_file - at >= 1:
        out.append((at, end_of_file, SHOW))
    return out


def ffmetadata(chapter_list):
    lines = [';FFMETADATA1']
    for start, end, title in chapter_list:
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={round(start * 1000)}',
                  f'END={round(end * 1000)}', f'title={title}']
    return '\n'.join(lines) + '\n'


def duration_of(video, ffprobe='ffprobe'):
    try:
        out = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                              video], capture_output=True, text=True, timeout=120).stdout
        return float(out.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _low_priority():
    try:
        os.nice(19)  # recordings being encoded at the same time come first
    except (AttributeError, OSError):
        pass


def find_breaks(video, comskip='comskip', ini=None, timeout=4 * 3600):
    """Run Comskip on a finished recording. Returns (breaks, edl_path), keeping the .edl beside
    the video. Raises RuntimeError if Comskip fails."""
    ini = ini or DEFAULT_INI
    base = os.path.splitext(os.path.basename(video))[0]
    with tempfile.TemporaryDirectory(prefix='comskip-') as work:
        # Its other outputs (.txt, .log, ...) go to a scratch folder, so nothing else is left behind
        proc = subprocess.run([comskip, f'--ini={ini}', f'--output={work}', video],
                              capture_output=True, text=True, timeout=timeout,
                              preexec_fn=_low_priority if os.name == 'posix' else None)
        edl = os.path.join(work, base + '.edl')
        # Comskip exits 1 when it found breaks and 0 when it found none
        if proc.returncode not in (0, 1) or (proc.returncode == 1 and not os.path.exists(edl)):
            tail = (proc.stderr or proc.stdout or '').strip().splitlines()[-1:] or ['no output']
            raise RuntimeError(f"comskip exited {proc.returncode}: {tail[0][:200]}")
        if not os.path.exists(edl):
            return [], None
        with open(edl, encoding='utf-8', errors='replace') as f:
            breaks = parse_edl(f.read())
        dest = os.path.splitext(video)[0] + '.edl'
        shutil.copyfile(edl, dest)
        return breaks, dest


MAX_AD_SHARE = 0.5      # refuse to cut when Comskip calls more than this much of a recording ads
CUT_LENGTH_SLACK = 10   # seconds per piece of show the cut file may run long (it starts on a keyframe)


def show_segments(breaks, duration=None):
    """[(start, end)] of the show between the ad breaks"""
    return [(s, e) for s, e, title in chapters(breaks, duration) if title == SHOW]


def cut_check(breaks, duration):
    """Why cutting these breaks out isn't safe, or None if it is"""
    if not breaks:
        return 'no ad breaks found'
    if not duration:
        return "couldn't read the recording's length"
    ads = sum(min(e, duration) - s for s, e in breaks)
    if ads > duration * MAX_AD_SHARE:
        return f"Comskip marked {ads / duration:.0%} of it as ads, which looks wrong"
    if not show_segments(breaks, duration):
        return 'nothing would be left'
    return None


def shift_srt(text, breaks):
    """Subtitles re-timed for a recording with these breaks cut out; cues inside a break are dropped"""
    def to_s(ts):
        h, m, rest = ts.strip().replace('.', ',').split(':')
        s, ms = rest.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    def to_ts(t):
        ms = round(max(t, 0) * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    def new_time(t):
        removed = 0.0
        for s, e in breaks:
            if t >= e:
                removed += e - s
            elif t > s:
                return None  # inside a break
        return t - removed

    out, n = [], 0
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n').strip()):
        lines = block.split('\n')
        timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing is None:
            continue
        try:
            start, end = (to_s(p) for p in lines[timing].split('-->'))
        except ValueError:
            continue
        a, b = new_time(start), new_time(end)
        if a is None or b is None or b <= a:
            continue
        n += 1
        out.append('\n'.join([str(n), f"{to_ts(a)} --> {to_ts(b)}"] + lines[timing + 1:]))
    return '\n\n'.join(out) + '\n' if out else ''


def cut_ads(video, breaks, ffmpeg='ffmpeg', ffprobe='ffprobe', keep_original=None):
    """Cut the ad breaks out of a recording (stream copy, so each piece of show starts at the
    keyframe before it: a second of ad may stay in, the show never loses any). keep_original(path)
    moves the uncut file somewhere safe before the cut one takes its place; captions are re-timed.
    Returns seconds removed. Raises RuntimeError when it isn't safe; the recording is untouched then."""
    duration = duration_of(video, ffprobe)
    problem = cut_check(breaks, duration)
    if problem:
        raise RuntimeError(f"not cutting: {problem}")
    segments = show_segments(breaks, duration)
    folder, name = os.path.split(video)
    stem, ext = os.path.splitext(name)
    tmp = os.path.join(folder, f".{stem}.cut{ext}")
    listing = tmp + '.txt'
    quoted = os.path.abspath(video).replace("'", "'\\''")
    with open(listing, 'w', encoding='utf-8') as f:
        f.write('ffconcat version 1.0\n')
        for start, end in segments:
            f.write(f"file '{quoted}'\ninpoint {start:.3f}\noutpoint {end:.3f}\n")
    try:
        cmd = [ffmpeg, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listing, '-map', '0',
               '-c', 'copy', '-avoid_negative_ts', 'make_zero']
        if ext.lower() in ('.mp4', '.m4v'):
            cmd += ['-movflags', '+faststart']
        proc = subprocess.run(cmd + [tmp], capture_output=True, text=True, timeout=3600)
        expected = sum(e - s for s, e in segments)
        got = duration_of(tmp, ffprobe) if os.path.exists(tmp) else None
        if proc.returncode != 0 or got is None or not (
                expected - CUT_LENGTH_SLACK <= got <= expected + CUT_LENGTH_SLACK * (len(segments) + 1)):
            raise RuntimeError(f"cut came out wrong (expected {expected:.0f} s, got {got}): "
                               f"{(proc.stderr or '').strip()[-200:]}")
        srt = os.path.join(folder, stem + '.en.srt')
        edl = os.path.join(folder, stem + '.edl')
        if keep_original:
            keep_original(video)  # copies the .srt/.edl too, before they change below
        os.replace(tmp, video)
        if os.path.exists(srt):
            with open(srt, encoding='utf-8', errors='replace') as f:
                shifted = shift_srt(f.read(), breaks)
            with open(srt, 'w', encoding='utf-8') as f:
                f.write(shifted)
        if os.path.exists(edl):
            os.remove(edl)  # its times are for the uncut recording
        return duration - got
    finally:
        for leftover in (tmp, listing):
            if os.path.exists(leftover):
                os.remove(leftover)


def add_chapters(video, breaks, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Rewrite the recording with Show/Commercial chapters (stream copy). Returns the number of
    breaks marked, 0 if the format can't carry chapters or there were none."""
    if not breaks or os.path.splitext(video)[1].lower() not in CHAPTER_FORMATS:
        return 0
    meta = ffmetadata(chapters(breaks, duration_of(video, ffprobe)))
    folder, name = os.path.split(video)
    stem, ext = os.path.splitext(name)
    tmp = os.path.join(folder, f".{stem}.chapters{ext}")
    meta_path = tmp + '.ffmeta'
    with open(meta_path, 'w', encoding='utf-8') as f:
        f.write(meta)
    try:
        cmd = [ffmpeg, '-v', 'error', '-y', '-i', video, '-i', meta_path, '-map', '0', '-map_metadata', '0',
               '-map_chapters', '1', '-c', 'copy']
        if ext.lower() in ('.mp4', '.m4v'):
            cmd += ['-movflags', '+faststart']
        proc = subprocess.run(cmd + [tmp], capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < os.path.getsize(video) * 0.9:
            raise RuntimeError(f"ffmpeg couldn't add chapters: {(proc.stderr or '').strip()[-200:]}")
        os.replace(tmp, video)
        return len(breaks)
    finally:
        for leftover in (tmp, meta_path):
            if os.path.exists(leftover):
                os.remove(leftover)
