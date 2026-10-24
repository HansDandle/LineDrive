"""
Live TV in the browser. Browsers can't play the tuner's MPEG-2/AC-3 transport stream, so each
viewer gets an ffmpeg that turns it into H.264/AAC HLS (2-second segments in a folder of its
own), which the guide's player reads. Every viewer holds a tuner and an encode, so a session ends
when its page stops sending heartbeats, when the stream dies, or when a recording needs the tuner.
"""
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

SEGMENT_SECONDS = 2
PLAYLIST_SEGMENTS = 6  # what the playlist lists; older segments are deleted
IDLE_SECONDS = 75  # no heartbeat for this long: the viewer has gone (a background tab may only get to send one a minute)
ENDED_KEEP_SECONDS = 600  # how long a heartbeat can still learn why its session ended
FILE_NAME = re.compile(r'^(index\.m3u8|seg\d{5}\.ts)$')
SESSION_ID = re.compile(r'^[0-9a-f]{32}$')


class LiveError(Exception):
    pass


class Session:
    def __init__(self, sid, channel, box, folder, now):
        self.id, self.channel, self.box, self.folder = sid, channel, box, folder
        self.started = self.seen = now
        self.proc = None
        self.encoder = None
        self.tail = []

    def info(self):
        return {'id': self.id, 'channel': self.channel, 'box': self.box, 'started': self.started}


class LiveTV:
    def __init__(self, root, popen=subprocess.Popen, clock=time.time, explain=None, on_died=None):
        """root: a folder for the segments, emptied now. explain(stderr lines) -> a reason
        for a stream that died. on_died(session, reason): called when one does."""
        self.root = root
        self.popen, self.clock = popen, clock
        self.explain = explain or (lambda tail: tail[-1] if tail else 'the stream stopped')
        self.on_died = on_died or (lambda session, reason: None)
        self.sessions = {}
        self.ended = {}  # id -> (reason, when)
        self.lock = threading.RLock()
        shutil.rmtree(root, ignore_errors=True)
        os.makedirs(root, exist_ok=True)

    @staticmethod
    def command(ffmpeg, url, video_args, folder):
        return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', url,
                '-map', '0:v:0', '-map', '0:a:0?'] + list(video_args) + [
                '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_SECONDS})',
                '-c:a', 'aac', '-b:a', '128k', '-ac', '2',
                '-f', 'hls', '-hls_time', str(SEGMENT_SECONDS), '-hls_list_size', str(PLAYLIST_SEGMENTS),
                '-hls_flags', 'delete_segments+independent_segments',
                '-hls_segment_filename', os.path.join(folder, 'seg%05d.ts'),
                os.path.join(folder, 'index.m3u8')]

    def start(self, channel, box, url, ffmpeg, video_args, max_viewers, encoder=None):
        """Start converting a channel for one viewer. Raises LiveError when too many are watching."""
        with self.lock:
            self.reap()
            if len(self.sessions) >= max_viewers:
                raise LiveError(f"{len(self.sessions)} {'person is' if len(self.sessions) == 1 else 'people are'} "
                                f"already watching live TV (the most at once is {max_viewers}). Close a player first.")
            sid = uuid.uuid4().hex
            folder = os.path.join(self.root, sid)
            os.makedirs(folder)
            s = Session(sid, str(channel), box, folder, self.clock())
            s.encoder = encoder
            s.proc = self.popen(self.command(ffmpeg, url, video_args, folder),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            threading.Thread(target=self._read_errors, args=(s,), daemon=True).start()
            self.sessions[sid] = s
            return s

    @staticmethod
    def _read_errors(s):
        for line in iter(s.proc.stderr.readline, b''):
            s.tail.append(line.decode(errors='ignore').strip())
            del s.tail[:-10]

    def touch(self, sid):
        """A heartbeat. Returns (True, None) while the session runs, else (False, why it ended)."""
        with self.lock:
            self.reap()
            s = self.sessions.get(sid)
            if s:
                s.seen = self.clock()
                return True, None
            reason, _ = self.ended.get(sid, ('This live stream has ended.', None))
            return False, reason

    def stop(self, sid, reason='Closed.'):
        with self.lock:
            s = self.sessions.pop(sid, None)
            if not s:
                return False
            self.ended[sid] = (reason, self.clock())
        if s.proc.poll() is None:
            s.proc.terminate()
            try:
                s.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                s.proc.kill()
                s.proc.wait()
        shutil.rmtree(s.folder, ignore_errors=True)
        return True

    def stop_for_recording(self, boxes, title):
        """Free a tuner for a recording: stop the longest-running viewer on one of these boxes.
        Returns the stopped session's info, or None when nobody was watching there."""
        with self.lock:
            mine = sorted((s for s in self.sessions.values() if not boxes or s.box in boxes), key=lambda s: s.started)
            if not mine:
                return None
            s = mine[0]
        self.stop(s.id, f"Stopped so the tuner could record {title}.")
        return s.info()

    def reap(self):
        """End sessions whose viewer went away or whose stream died"""
        now = self.clock()
        with self.lock:
            for s in list(self.sessions.values()):
                if now - s.seen > IDLE_SECONDS:
                    self.stop(s.id, 'Stopped: the player stopped checking in.')
                elif s.proc.poll() is not None:
                    reason = self.explain(s.tail)
                    self.stop(s.id, f"The stream stopped: {reason}")
                    self.on_died(s, reason)
            for sid, (_, when) in list(self.ended.items()):
                if now - when > ENDED_KEEP_SECONDS:
                    del self.ended[sid]

    def holding(self):
        """{(box, channel)} tuned for viewers"""
        with self.lock:
            return {(s.box, s.channel) for s in self.sessions.values()}

    def file(self, sid, name):
        """Path of a session's playlist or segment, or None"""
        if not (SESSION_ID.match(sid or '') and FILE_NAME.match(name or '')):
            return None
        with self.lock:
            s = self.sessions.get(sid)
        if not s:
            return None
        path = os.path.join(s.folder, name)
        return path if os.path.exists(path) else None

    def stop_all(self):
        for sid in list(self.sessions):
            self.stop(sid, 'LineDrive is restarting.')
