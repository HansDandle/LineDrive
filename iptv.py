"""
IPTV channels from M3U playlists, recorded alongside the HDHomeRun's. Config iptv: a list of
{"name", "m3u" (URL or file), "max_streams" (how many channels the provider lets you stream at
once; default 1), "xmltv" (optional; else the playlist's url-tvg), "groups" (optional: only
these group-title values)}. Each source works like one more box in the tuner pool, with
max_streams tuners and only its own channels. Channels keep the playlist's tvg-chno where it has
one that's free, else they're numbered from 1000 per source (1001, 1002, ...; the second source
from 2001).
"""
import os
import re

import requests

ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def box_id(source):
    return 'iptv:' + (source.get('name') or 'IPTV')


def is_iptv(box):
    return str(box or '').startswith('iptv:')


def input_args(url):
    """ffmpeg options to go before -i url. FAST channels (Samsung TV Plus on amagi.tv, say) splice
    in ad segments whose URLs don't end in .ts, which ffmpeg 7.1+ refuses ("is not in
    allowed_segment_extensions"). The option belongs to ffmpeg's HLS reader and is an error for
    any other input (the HDHomeRun's transport stream), so only HLS playlists get it."""
    return ['-extension_picky', '0'] if '.m3u8' in str(url or '').lower() else []


def load(location, timeout=30):
    if re.match(r'^https?://', location, re.I):
        r = requests.get(location, timeout=timeout, headers={'User-Agent': 'LineDrive'})
        r.raise_for_status()
        return r.text
    with open(os.path.expanduser(location), encoding='utf-8', errors='replace') as f:
        return f.read()


def parse(text):
    """(header attributes, [{name, url, tvg_id, tvg_chno, group, logo}]) from an M3U playlist"""
    header, entries, info = {}, [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXTM3U'):
            header = dict(ATTR.findall(line))
        elif line.startswith('#EXTINF'):
            attrs = dict(ATTR.findall(line))
            name = line.rsplit(',', 1)[1].strip() if ',' in line else ''
            info = {'name': name or attrs.get('tvg-name', ''), 'tvg_id': attrs.get('tvg-id', ''),
                    'tvg_chno': attrs.get('tvg-chno') or attrs.get('channel-number', ''),
                    'group': attrs.get('group-title', ''), 'logo': attrs.get('tvg-logo', '')}
        elif line and not line.startswith('#') and info is not None:
            entries.append(dict(info, url=line))
            info = None
    return header, entries


def number(entries, index, taken):
    """Give each entry a channel number not in `taken` (which is updated): its tvg-chno if free,
    else index * 1000 + 1, + 2, ..."""
    next_n = index * 1000 + 1
    out = []
    for e in entries:
        num = str(e.get('tvg_chno') or '').strip()
        if not num or num in taken:
            while str(next_n) in taken:
                next_n += 1
            num = str(next_n)
        taken.add(num)
        out.append(dict(e, number=num))
    return out


def channels(sources, taken):
    """Every source's channels: [(source, box id, guide url, [entries with 'number'])].
    taken: channel numbers already used (the HDHomeRun lineup); updated."""
    out = []
    for i, source in enumerate(sources or [], 1):
        if not source.get('m3u'):
            continue
        try:
            header, entries = parse(load(source['m3u']))
        except Exception as e:
            print(f"[IPTV] Couldn't read {source.get('name') or source['m3u']}: {e}")
            continue
        groups = set(source.get('groups') or [])
        if groups:
            entries = [e for e in entries if e['group'] in groups]
        guide = source.get('xmltv') or header.get('url-tvg') or header.get('x-tvg-url') or ''
        out.append((source, box_id(source), guide.split(',')[0].strip(), number(entries, i, taken)))
    return out
