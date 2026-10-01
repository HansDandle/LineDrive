"""Keep/delete rules for series recordings.

A series rule's `keep` setting says how many of its recordings to keep: 'last:5' (the newest five),
'days:14' (two weeks after recording), 'watched:2' (two days after it's watched in Jellyfin) or
'all'. LineDrive only ever removes files it recorded itself, as listed in its ledger, and removed
files go to <recordings>/.deleted/ first, where they're purged after RECYCLE_DAYS.
"""
import os
import shutil
import time
from datetime import timedelta

RECYCLE_DIR = '.deleted'
RECYCLE_DAYS = 7
SIDECARS = ('.en.srt', '.srt', '.nfo')
# Folders under the recordings root that LineDrive files into; never removed even when empty
TOP_FOLDERS = {'TV', 'Movies', 'Other'}

KEEP_CHOICES = [
    ('all', 'Keep all'),
    ('last:1', 'Keep the newest 1'), ('last:3', 'Keep the newest 3'), ('last:5', 'Keep the newest 5'),
    ('last:10', 'Keep the newest 10'),
    ('days:7', 'Delete after 1 week'), ('days:14', 'Delete after 2 weeks'), ('days:30', 'Delete after 30 days'),
    ('watched:0', 'Delete once watched'), ('watched:2', 'Delete 2 days after watching'),
    ('watched:7', 'Delete a week after watching'),
]
KEEP_LABELS = dict(KEEP_CHOICES)


def parse_keep(value):
    """'last:5' -> ('last', 5), 'days:14' -> ('days', 14), 'watched:2' -> ('watched', 2);
    'all', empty or anything malformed -> None (keep everything)"""
    kind, _, n = str(value or '').partition(':')
    if kind not in ('last', 'days', 'watched') or not n.isdigit():
        return None
    n = int(n)
    if kind == 'last' and n < 1:
        return None
    return kind, n


def keep_setting(rule):
    """The rule's keep setting as a string. Older rules made by Ask LineDrive ("record X every week
    for 6 weeks") carry retention_weeks instead."""
    if rule.get('keep'):
        return rule['keep'] if parse_keep(rule['keep']) else 'all'
    weeks = rule.get('retention_weeks')
    if isinstance(weeks, int) and weeks > 0:
        return f'days:{weeks * 7}'
    return 'all'


def keep_label(value):
    policy = parse_keep(value)
    if not policy:
        return KEEP_LABELS['all']
    kind, n = policy
    return KEEP_LABELS.get(f'{kind}:{n}') or {
        'last': f'Keep the newest {n}', 'days': f'Delete after {n} days',
        'watched': f'Delete {n} days after watching'}[kind]


def to_remove(entries, policy, now):
    """Which of one rule's recordings (ledger entries still on disk) the policy says to remove.
    Entries carry finished_at (datetime) and, once Jellyfin reports them watched, played_at."""
    if not policy:
        return []
    kind, n = policy
    if kind == 'last':
        newest_first = sorted(entries, key=lambda e: e['finished_at'], reverse=True)
        return newest_first[n:]
    if kind == 'days':
        return [e for e in entries if now - e['finished_at'] >= timedelta(days=n)]
    return [e for e in entries if e.get('played_at') and now - e['played_at'] >= timedelta(days=n)]


def sidecars(video_path):
    """The .srt/.nfo files saved beside a recording"""
    base = os.path.splitext(video_path)[0]
    return [base + ext for ext in SIDECARS if os.path.exists(base + ext)]


def _free_name(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f'{base} ({n}){ext}'):
        n += 1
    return f'{base} ({n}){ext}'


def recycle(video_path, root):
    """Move a recording and its .srt/.nfo into root/.deleted/ (same relative path), then remove the
    show/season folders that left empty. Returns the recording's new path."""
    bin_dir = os.path.join(root, RECYCLE_DIR)
    os.makedirs(bin_dir, exist_ok=True)
    marker = os.path.join(bin_dir, '.ignore')  # Jellyfin skips folders holding a .ignore file
    if not os.path.exists(marker):
        open(marker, 'w').close()
    now = time.time()
    moved = None
    for path in [video_path] + sidecars(video_path):
        dest = _free_name(os.path.join(bin_dir, os.path.relpath(path, root)))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(path, dest)
        os.utime(dest, (now, now))  # the purge counts from when it was deleted, not recorded
        moved = moved or dest
    folder = os.path.dirname(video_path)
    while os.path.normcase(folder) != os.path.normcase(root) and \
            os.path.relpath(folder, root).split(os.sep)[0] not in ('..', RECYCLE_DIR) and \
            os.path.relpath(folder, root) not in TOP_FOLDERS:
        try:
            os.rmdir(folder)  # only succeeds when empty
        except OSError:
            break
        folder = os.path.dirname(folder)
    return moved


def purge_recycled(root, days=RECYCLE_DAYS, now=None):
    """Permanently delete files that have been in root/.deleted/ longer than `days`. Returns how many."""
    bin_dir = os.path.join(root, RECYCLE_DIR)
    cutoff = (now or time.time()) - days * 86400
    removed = 0
    for folder, dirs, names in os.walk(bin_dir, topdown=False):
        for name in names:
            path = os.path.join(folder, name)
            if name == '.ignore' and folder == bin_dir:
                continue
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
        if folder != bin_dir:
            try:
                os.rmdir(folder)
            except OSError:
                pass
    return removed
