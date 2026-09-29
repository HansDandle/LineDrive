"""
LineDrive's guide as an XMLTV file (served at /guide.xml), so Jellyfin, Plex, Channels, TVHeadend
and the like can use the same merged Gracenote + SiliconDust listings. Channel ids are the tuner's
channel numbers ("4.1"), which is also how those apps number HDHomeRun channels.
"""
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET


def _start(prog):
    try:
        return datetime.strptime(f"{prog['date']} {prog['time']}", '%Y-%m-%d %I:%M %p')
    except (KeyError, TypeError, ValueError):
        return None


def _stamp(naive, tz):
    """XMLTV time, e.g. 20260928200000 -0400. Guide times are local to tz (None: this machine's zone)."""
    aware = tz.localize(naive) if tz is not None and hasattr(tz, 'localize') else \
        naive.replace(tzinfo=tz) if tz is not None else naive.astimezone()
    return aware.strftime('%Y%m%d%H%M%S %z')


def build_xmltv(guide_channels, tz=None, is_new=None):
    """guide_channels: [(number, name, call_sign, programs)] as dvr_web._guide_channels returns.
    is_new(prog) marks first-run airings. Returns the document as UTF-8 bytes."""
    root = ET.Element('tv', {'generator-info-name': 'LineDrive',
                             'generator-info-url': 'https://github.com/HansDandle/LineDrive'})
    programmes = []
    for num, name, call, progs in guide_channels:
        chan = ET.SubElement(root, 'channel', id=num)
        # Several display names, so apps can match by number, call sign or both
        for label in dict.fromkeys(filter(None, [f"{num} {name}".strip(), num, name, call])):
            ET.SubElement(chan, 'display-name').text = label
        seen = set()
        for p in sorted(progs, key=lambda p: _start(p) or datetime.max):
            start = _start(p)
            if not start or start in seen or not p.get('title'):
                continue
            seen.add(start)
            programmes.append((num, start, p))

    for num, start, p in programmes:
        stop = start + timedelta(minutes=int(p.get('duration') or 30))
        prog = ET.SubElement(root, 'programme', start=_stamp(start, tz), stop=_stamp(stop, tz), channel=num)
        ET.SubElement(prog, 'title', lang='en').text = p['title']
        if p.get('episode_title'):
            ET.SubElement(prog, 'sub-title', lang='en').text = p['episode_title']
        if p.get('description'):
            ET.SubElement(prog, 'desc', lang='en').text = p['description']
        if p.get('year'):
            ET.SubElement(prog, 'date').text = str(p['year'])
        elif p.get('original_air_date'):
            ET.SubElement(prog, 'date').text = p['original_air_date'].replace('-', '')
        for genre in filter(None, (g.strip() for g in (p.get('genre') or '').split(','))):
            ET.SubElement(prog, 'category', lang='en').text = genre
        if p.get('image'):
            ET.SubElement(prog, 'icon', src=p['image'])
        season, episode = str(p.get('season_number') or ''), str(p.get('episode_number') or '')
        if season.isdigit() and episode.isdigit():
            ET.SubElement(prog, 'episode-num', system='xmltv_ns').text = f"{int(season) - 1}.{int(episode) - 1}."
            ET.SubElement(prog, 'episode-num', system='onscreen').text = f"S{int(season):02}E{int(episode):02}"
        if is_new and is_new(p):
            ET.SubElement(prog, 'new')
        elif p.get('original_air_date'):
            ET.SubElement(prog, 'previously-shown', start=p['original_air_date'].replace('-', '') + '000000')
        if p.get('rating'):
            ET.SubElement(ET.SubElement(prog, 'rating'), 'value').text = p['rating']

    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n' + \
        ET.tostring(root, encoding='utf-8')
