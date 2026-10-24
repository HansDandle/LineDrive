"""
Guide listings from an XMLTV file or URL, for places Gracenote doesn't cover (a week of UK
Freeview from an XMLTV provider, say) and for IPTV channels. Config epg.xmltv: a URL or a file
path (.xml or .xml.gz). Each XMLTV channel is matched to a tuner channel by, in order: the
epg.xmltv_channels map ({"BBCOne.uk": "1"}), a display name or <lcn> that is the channel number,
then the channel's name ("BBC ONE" = "BBC One HD"). Listings come out in the same shape as
epg_zap2it's, and only for matched channels.
"""
import gzip
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

from epg_zap2it import _local_tz

DAYS = 8


def load(source, timeout=60):
    """The XMLTV document's bytes, from a URL or a file, un-gzipped"""
    if re.match(r'^https?://', source, re.I):
        r = requests.get(source, timeout=timeout, headers={'User-Agent': 'LineDrive'})
        r.raise_for_status()
        data = r.content
    else:
        with open(os.path.expanduser(source), 'rb') as f:
            data = f.read()
    return gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data


def _norm(name):
    """'BBC One HD' -> 'bbcone', 'KVUE-DT' -> 'kvue'"""
    name = re.sub(r'[^a-z0-9]+', ' ', (name or '').lower()).strip()
    name = re.sub(r'\b(hd|uhd|sd|dt|tv|\+1)$', '', name).strip()
    return name.replace(' ', '')


def _time(text):
    """'20261024190000 +0100' -> aware datetime (no offset: UTC, as the XMLTV spec says)"""
    m = re.match(r'(\d{12,14})\s*([+-]\d{4})?', text or '')
    if not m:
        return None
    stamp = m.group(1).ljust(14, '0')
    offset = m.group(2) or '+0000'
    return datetime.strptime(stamp + offset, '%Y%m%d%H%M%S%z')


def _episode(prog):
    """(season, episode) as strings, from xmltv_ns ('2.5.0/1' is S3E6) or onscreen ('S03E06')"""
    nums = {e.get('system'): (e.text or '').strip() for e in prog.findall('episode-num')}
    ns = nums.get('xmltv_ns')
    if ns:
        parts = [p.split('/')[0].strip() for p in ns.split('.')]
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return str(int(parts[0]) + 1), str(int(parts[1]) + 1)
    for text in nums.values():
        m = re.search(r'S\s*(\d+)\s*E\s*(\d+)', text, re.I)
        if m:
            return str(int(m.group(1))), str(int(m.group(2)))
    return '', ''


def read(data):
    """({xmltv id: {'names': [...], 'lcn': '...'}}, [programme elements]) from an XMLTV document"""
    root = ET.fromstring(data)
    channels = {ch.get('id'): {'names': [(d.text or '').strip() for d in ch.findall('display-name')],
                               'lcn': (ch.findtext('lcn') or '').strip()}
                for ch in root.findall('channel')}
    return channels, root.findall('programme')


def match_channels(xml_channels, lineup, overrides=None):
    """{xmltv id: [tuner channel numbers]}. lineup: {number: tuner's name for it}."""
    out = {}
    for xid, num in (overrides or {}).items():
        if str(num) in lineup:
            out.setdefault(xid, []).append(str(num))
    taken = {n for nums in out.values() for n in nums}
    by_name = {}
    for num, name in lineup.items():
        by_name.setdefault(_norm(name), []).append(num)
    for xid, ch in xml_channels.items():
        if xid in out:
            continue
        names = [n for n in ch['names'] if n]
        # A display name or LCN that is the channel number ("4.1", "101", or "4.1 KVUE")
        numbers = {ch['lcn']} | {n.split()[0] for n in names}
        nums = [n for n in numbers if n in lineup and n not in taken]
        if not nums:
            nums = [n for name in names for n in by_name.get(_norm(name), []) if n not in taken]
        if nums:
            out[xid] = sorted(set(nums))
            taken |= set(nums)
    return out


def listings(data, lineup, overrides=None, now=None):
    """(listings for the tuner's channels, {'matched': n, 'unmatched': [tuner channels without a guide]})"""
    tz = _local_tz()
    now = (now or datetime.now()).astimezone()
    until = now + timedelta(days=DAYS)
    xml_channels, programmes = read(data)
    mapping = match_channels(xml_channels, lineup, overrides)
    flagged = False
    out = []
    for prog in programmes:
        nums = mapping.get(prog.get('channel'))
        start, stop = _time(prog.get('start')), _time(prog.get('stop'))
        if not nums or not start or (stop and stop <= now) or start >= until:
            continue
        stop = stop or start + timedelta(minutes=30)
        local = start.astimezone(tz)
        season, episode = _episode(prog)
        categories = [(c.text or '').strip() for c in prog.findall('category') if c.text]
        if any(c.lower().startswith('sport') for c in categories) and 'Sports' not in categories:
            categories.append('Sports')
        flags = []
        if prog.find('new') is not None:
            flags.append('New')
        if prog.find('premiere') is not None:
            flags.append('Premiere')
        if prog.find('live') is not None:
            flags.append('Live')
        if flags or prog.find('previously-shown') is not None:
            flagged = True
        date = (prog.findtext('date') or '').strip()
        icon = prog.find('icon')
        for num in nums:
            name = lineup.get(num, '')
            out.append({
                'channel': f"{name} ({num})",
                'title': (prog.findtext('title') or '').strip(),
                'time': local.strftime('%I:%M %p'),
                'date': local.strftime('%Y-%m-%d'),
                'period': 'Morning' if 6 <= local.hour < 12 else 'Afternoon' if 12 <= local.hour < 18 else 'Evening',
                'is_local': True,
                'call_sign': name,
                'channel_number': num,
                'episode_title': (prog.findtext('sub-title') or '').strip(),
                'season_number': season,
                'episode_number': episode,
                'episode_id': f"S{season:0>2}E{episode:0>2}" if season and episode else '',
                'original_air_date': f"{date[:4]}-{date[4:6]}-{date[6:8]}" if re.fullmatch(r'\d{8}', date) else '',
                'description': (prog.findtext('desc') or '').strip(),
                'genre': ', '.join(categories),
                'rating': (prog.findtext('rating/value') or '').strip(),
                'year': date[:4] if re.fullmatch(r'\d{4}', date) else '',
                'flags': flags,
                'duration': max(1, int((stop - start).total_seconds() // 60)),
                'image': icon.get('src', '') if icon is not None else '',
                'source': 'xmltv',
            })
    if not flagged:
        # A feed that never says what's new or a repeat: don't let "new episodes only" treat every
        # airing as a rerun (no flags at all means "unknown" to LineDrive)
        for p in out:
            del p['flags']
    matched = {n for nums in mapping.values() for n in nums}
    unmatched = [f"{num} {name}".strip() for num, name in lineup.items() if num not in matched]
    return out, {'matched': len(matched), 'unmatched': unmatched}
