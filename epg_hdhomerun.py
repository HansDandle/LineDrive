"""
Guide listings from SiliconDust's own guide service (api.hdhomerun.com), the one the HDHomeRun
app uses. It's keyed to the tuner itself (the DeviceAuth token from its discover.json), so it
matches the tuner's channel lineup exactly and works wherever SiliconDust has guide data, not
just the US. Without a SiliconDust DVR subscription it only reaches about a day ahead, so with a
ZIP code LineDrive uses it to fill in Gracenote's week (series IDs, original air dates, artwork,
channels Gracenote lacks) and on its own only when there's no ZIP code.
"""
import re
from datetime import datetime, timezone

import requests

from epg_zap2it import _local_tz

GUIDE_URL = 'https://api.hdhomerun.com/api/guide.php'


def _device_auth(hdhr_ip):
    """The tuner's current DeviceAuth token (it rotates, so fetch it fresh each time)"""
    return requests.get(f'http://{hdhr_ip}/discover.json', timeout=5).json().get('DeviceAuth')


def fetch_hdhomerun_guide(hdhr_ip, days=7):
    """Raw guide: [{GuideNumber, GuideName, Affiliate, ImageURL, Guide: [listing, ...]}, ...].
    Asks for one day at a time until the service stops answering (the free guide ends after a
    day or so; a DVR subscription goes further)."""
    auth = _device_auth(hdhr_ip)
    if not auth:
        return []
    channels = {}
    start = int(datetime.now(timezone.utc).timestamp()) // 3600 * 3600
    for day in range(days):
        try:
            r = requests.get(GUIDE_URL, params={'DeviceAuth': auth, 'Start': start + day * 86400, 'Duration': 24},
                             timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"SiliconDust guide: request failed: {e}")
            break
        if not isinstance(data, list) or not data:
            break
        for ch in data:
            num = ch.get('GuideNumber')
            if not num:
                continue
            entry = channels.setdefault(num, {k: v for k, v in ch.items() if k != 'Guide'} | {'Guide': []})
            entry['Guide'].extend(ch.get('Guide') or [])
    return list(channels.values())


def parse_hdhomerun_guide(raw):
    """Convert to LineDrive's listing dicts (the same fields epg_zap2it produces)"""
    tz = _local_tz()
    results, seen = [], set()
    for ch in raw:
        num = str(ch.get('GuideNumber', ''))
        call = ch.get('GuideName', '')
        affiliate = ch.get('Affiliate', '')
        display = f"{call} {affiliate} ({num})" if affiliate else f"{call} ({num})"
        for g in ch.get('Guide') or []:
            title = g.get('Title') or ''
            if not title or not g.get('StartTime') or (num, g['StartTime']) in seen:
                continue
            seen.add((num, g['StartTime']))
            start = datetime.fromtimestamp(g['StartTime'], timezone.utc).astimezone(tz)
            season = episode = ''
            m = re.fullmatch(r'S(\d+)E(\d+)', g.get('EpisodeNumber') or '')
            if m:
                season, episode = str(int(m.group(1))), str(int(m.group(2)))
            aired = ''
            if g.get('OriginalAirdate'):
                # Midnight UTC of the air date
                aired = datetime.fromtimestamp(g['OriginalAirdate'], timezone.utc).strftime('%Y-%m-%d')
            first_run = bool(g.get('First'))
            results.append({
                'channel': display,
                'title': title,
                'time': start.strftime('%I:%M %p'),
                'date': start.strftime('%Y-%m-%d'),
                'period': 'Morning' if 6 <= start.hour < 12 else 'Afternoon' if 12 <= start.hour < 18 else 'Evening',
                'is_local': True,
                'call_sign': call,
                'channel_number': num,
                'episode_title': g.get('EpisodeTitle') or '',
                'season_number': season,
                'episode_number': episode,
                'episode_id': f"S{season:0>2}E{episode:0>2}" if season and episode else '',
                'original_air_date': aired,
                'description': g.get('Synopsis') or '',
                'genre': ', '.join(g.get('Filter') or []),
                'rating': '',
                'year': '',
                'flags': ['New'] if first_run else [],
                'duration': max(1, (g.get('EndTime', g['StartTime'] + 1800) - g['StartTime']) // 60),
                'series_id': g.get('SeriesID') or '',
                'image': g.get('ImageURL') or '',
                'first_run': first_run,
                'source': 'hdhomerun',
            })
    return results


# Fields SiliconDust adds to a Gracenote listing, or fills in when Gracenote left them empty
_ADDED = ('series_id', 'image', 'first_run')
_FILLED = ('original_air_date', 'season_number', 'episode_number', 'episode_id', 'episode_title', 'description')


def merge_guides(gracenote, hdhomerun, now=None):
    """Gracenote's listings enriched with SiliconDust's where both cover the same airing, plus
    SiliconDust's listings for channels Gracenote has nothing for. `gracenote` may already hold
    an earlier merge: its SiliconDust-only airings still to come are replaced by the fresh ones."""
    fetched_from = (now or datetime.now()).replace(minute=0, second=0, microsecond=0)
    by_slot = {(p['channel_number'], p['date'], p['time']): p for p in hdhomerun}
    covered = set()
    merged = []
    for p in gracenote:
        if p.get('source') == 'hdhomerun':
            try:
                start = datetime.strptime(f"{p['date']} {p['time']}", '%Y-%m-%d %I:%M %p')
            except (KeyError, ValueError):
                continue
            if start < fetched_from and (p['channel_number'], p['date'], p['time']) not in by_slot:
                merged.append(p)  # already aired; this fetch starts later
            continue
        covered.add(str(p.get('channel_number')))
        sd = by_slot.get((str(p.get('channel_number')), p.get('date'), p.get('time')))
        if sd and sd['title'].lower()[:12] == (p.get('title') or '').lower()[:12]:
            p = dict(p)
            for k in _ADDED:
                p[k] = sd[k]
            for k in _FILLED:
                if not p.get(k) and sd.get(k):
                    p[k] = sd[k]
        merged.append(p)
    merged.extend(sd for sd in hdhomerun if sd['channel_number'] not in covered)
    return merged
