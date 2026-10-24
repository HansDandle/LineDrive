"""
Several HDHomeRun boxes as one pool of tuners. hdhr.ip_address takes one address or several
separated by commas; the channel list is every box's lineup together, and each recording goes to
a box that carries the channel and has a free tuner. Tuners are numbered across boxes in the order
the addresses are listed (box 1's tuners first), so a tuner keeps its number while another box is
unreachable.
"""
import re


def parse_addresses(value):
    """'192.168.1.50, 192.168.1.51' (or a list) -> ['192.168.1.50', '192.168.1.51'], without repeats"""
    items = value if isinstance(value, (list, tuple)) else re.split(r'[,\s;]+', str(value or ''))
    out = []
    for item in items:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out


def merge_lineups(lineups):
    """[(box, lineup.json list or None)] -> (channels {number: name}, carriers {number: [box, ...]}).
    Where boxes disagree on a channel's name, the first box listed wins."""
    channels, carriers = {}, {}
    for box, lineup in lineups:
        for ch in lineup or []:
            num, name = ch.get('GuideNumber'), ch.get('GuideName')
            if not (num and name):
                continue
            channels.setdefault(num, name)
            carriers.setdefault(num, []).append(box)
    return channels, carriers


def combine_status(statuses, counts, ours=(), live=()):
    """statuses: [(box, status.json list, or None when it didn't answer)] in configured order.
    counts: {box: tuner count last seen}, updated here, which keeps numbering stable while a
    box is down. ours: {(box, channel number)} LineDrive is recording; live: the same for
    LineDrive's live TV viewers.
    Returns (tuners, unreachable boxes); tuners is None when no box answered."""
    tuners, down, offset, answered = [], [], 0, False
    for number, (box, status) in enumerate(statuses, 1):
        if status is None:
            down.append(box)
            offset += counts.get(box, 0)
            continue
        answered = True
        mine = []
        for s in status:
            res = s.get('Resource', '')
            if not res.startswith('tuner'):
                continue
            in_use = bool(s.get('VctNumber') or s.get('TargetIP'))
            local = int(res[5:] or 0)
            mine.append({
                'index': offset + local,
                'box': box,
                'box_number': number,
                'box_index': local,
                'channel_number': s.get('VctNumber') or '',
                'channel_name': s.get('VctName') or '',
                'target_ip': s.get('TargetIP') or '',
                'in_use': in_use,
                'ours': in_use and (box, s.get('VctNumber')) in set(ours) | set(live),
                'live': in_use and (box, s.get('VctNumber')) in live and (box, s.get('VctNumber')) not in ours,
            })
        counts[box] = len(mine) or counts.get(box, 0)
        tuners.extend(mine)
        offset += counts[box]
    return (tuners if answered else None), down


def box_order(channel, carriers, tuners):
    """The boxes to try for a channel: those carrying it, ones with a free tuner first (most free
    first, then in configured order). tuners: from combine_status, or None if unknown."""
    boxes = list(carriers.get(str(channel)) or [])
    if not tuners:
        return boxes
    free = {b: sum(1 for t in tuners if t['box'] == b and not t['in_use']) for b in boxes}
    return sorted(boxes, key=lambda b: (free[b] == 0, -free[b], boxes.index(b)))


def free_for(channel, carriers, tuners):
    """(free tuners on boxes carrying the channel, ['24.1 KVUE', ...] in use on those boxes);
    any channel when channel is None or no box lists it"""
    boxes = set(carriers.get(str(channel)) or []) or None if channel is not None else None
    mine = [t for t in tuners if boxes is None or t['box'] in boxes]
    busy = [f"{t['channel_number']} {t['channel_name']}".strip() for t in mine if t['in_use']]
    return len(mine) - len(busy), busy


def stream_url(box, channel):
    return f"http://{box}:5004/auto/v{channel}"
