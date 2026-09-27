"""
Offline question answering over the program guide for "Ask LineDrive".

Understands questions like:
  "when is the next basketball game"      "what's on now"
  "what's on channel 24 tonight at 8"     "is jeopardy on tomorrow"
  "any movies this weekend"               "find longhorns"
  "news on nbc tonight"                   "what's on at 9"

answer() returns None when the text doesn't look like a guide question, so the
caller can fall back to the older command parser.
"""
import re
from datetime import datetime, timedelta

MAX_RESULTS = 12

WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

QUESTION_STARTS = (
    'when', 'what', 'whats', 'is', 'are', 'any', 'anything', 'find', 'search', 'show me', 'list',
    'where', 'who', 'which', 'look for', 'lookup', 'look up', 'tell me', 'will', 'does', 'do ',
    'got', 'have', 'check',
)

# Words that shape the question but aren't part of what to search for
STOPWORDS = set("""
when what which who where is are was be being will would does do did can could should going gonna
the a an any anything something some there here this that these those it its of in on at for to from
me my i we you please tell show shows showing find search look lookup up list give get check see
next upcoming coming comes come soon later airing air airs aired playing plays play broadcast
time times tv program programs episode episodes watch watching watchable channel ch whats
today tonight tomorrow now currently right morning afternoon evening night weekend week
pm am oclock o clock about with and or have got
""".split())

# Topic words -> alternatives that count as a match
SYNONYMS = {
    'basketball': ['basketball', 'nba', 'wnba'],
    'football': ['football', 'nfl'],
    'soccer': ['soccer', 'fútbol', 'futbol', 'mls', 'nwsl', 'premier league', 'liga', 'copa', 'uefa'],
    'baseball': ['baseball', 'mlb'],
    'hockey': ['hockey', 'nhl'],
    'golf': ['golf', 'pga', 'lpga', 'presidents cup', 'ryder cup', 'masters'],
    'racing': ['racing', 'nascar', 'indycar', 'formula 1', 'grand prix'],
    'nascar': ['nascar'],
    'fighting': ['boxing', 'ufc', 'mma', 'wrestling', 'wwe'],
    'wrestling': ['wrestling', 'wwe', 'aew'],
    'college': ['college', 'ncaa'],
    'cartoon': ['cartoon', 'animated', 'animation'],
    'weather': ['weather', 'forecast'],
}

# College nicknames that listings spell by school name ("Texas at Ohio State").
# The school name only counts on sports listings, so "longhorns" doesn't find "Walker, Texas Ranger".
TEAM_ALIASES = {
    'longhorns': 'texas',
    'horns': 'texas',
    'aggies': 'texas a&m',
    'sooners': 'oklahoma',
    'red raiders': 'texas tech',
    'horned frogs': 'tcu',
    'bears': 'baylor',
    'bobcats': 'texas state',
    'roadrunners': 'utsa',
}
SPORTS_TITLE_WORDS = ('football', 'basketball', 'baseball', 'hockey', 'soccer', 'fútbol', 'volleyball', 'softball')
# Other schools whose names contain an alias ("Texas A&M", "North Texas") — not a match for "texas"
SCHOOL_NAME_AFTER = (' a&m', ' tech', ' state', ' southern', ' christian', '-')
SCHOOL_NAME_BEFORE = ('north ', 'south ', 'east ', 'west ', 'central ', 'southeastern ', 'stephen f. austin ')

# Words that mean a category rather than text to match
CATEGORY_WORDS = {
    'sports': 'Sports', 'sport': 'Sports', 'game': 'Sports', 'games': 'Sports', 'match': 'Sports',
    'matches': 'Sports',
    'movie': 'Movie', 'movies': 'Movie', 'film': 'Movie', 'films': 'Movie',
    'news': 'News', 'newscast': 'News',
    'kids': 'Family', 'family': 'Family', 'cartoons': 'Family', 'children': 'Family',
    'talk': 'Talk',
}

# Network names -> text found in the guide's channel description
NETWORKS = {
    'nbc': ['NATIONAL BROADCASTING', ' NBC'],
    'cbs': ['CBS'],
    'abc': ['AMERICAN BROADCASTING', ' ABC'],
    'fox': ['FOX ENTERTAINMENT', 'FOX BROADCASTING'],
    'pbs': ['PUBLIC BROADCASTING', ' PBS'],
    'cw': ['THE CW', ' CW '],
    'mynetwork': ['MYNETWORKTV'],
    'ion': [' ION'],
    'telemundo': ['TELEMUNDO'],
    'univision': ['UNIVISION'],
    'metv': ['ME TV'],
    'me tv': ['ME TV'],
    'antenna tv': ['ANTENNA TV'],
    'bounce': ['BOUNCE'],
    'comet': ['COMET'],
}

# Common show abbreviations -> guide titles
ABBREVIATIONS = {
    'snl': 'saturday night live',
    'gma': 'good morning america',
    'svu': 'law & order: special victims unit',
    'wof': 'wheel of fortune',
    'snf': 'sunday night football',
    'tnf': 'thursday night football',
    'mnf': 'monday night football',
}

CONTRACTIONS = [
    (r"\bwhat'?s\b", 'what is'), (r"\bwhen'?s\b", 'when is'), (r"\bwho'?s\b", 'who is'),
    (r"\bwhere'?s\b", 'where is'), (r"\bisn'?t\b", 'is not'), (r"\bthere'?s\b", 'there is'),
    (r"\bo'?clock\b", 'oclock'),
]


def normalize(text):
    t = (text or '').lower().replace('’', "'").replace('?', ' ').replace('!', ' ').replace(',', ' ')
    for pattern, repl in CONTRACTIONS:
        t = re.sub(pattern, repl, t)
    return re.sub(r'\s+', ' ', t).strip()


def looks_like_question(text):
    t = normalize(text)
    return t.startswith(QUESTION_STARTS) or (text or '').strip().endswith('?')


# --- time parsing -------------------------------------------------------------

def _day_start(dt):
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_clock(t):
    """Find a clock time like 'at 8', '8pm', '8:30 pm', '20:00', '8 oclock' -> (hour, minute, explicit_ampm)"""
    m = re.search(r'\b(?:at\s+|@\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b', t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)[0]
        if not (1 <= h <= 12 and mi < 60):
            return None, t
        h = h % 12 + (12 if ap == 'p' else 0)
        return (h, mi, True), t[:m.start()] + ' ' + t[m.end():]
    m = re.search(r'\b(?:at|@|around|by)\s+(\d{1,2})(?::(\d{2}))?(?:\s*oclock)?\b', t) or \
        re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*oclock\b', t) or \
        re.search(r'\b(\d{1,2}):(\d{2})\b', t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h > 23 or mi > 59:
            return None, t
        return (h, mi, h > 12 or h == 0), t[:m.start()] + ' ' + t[m.end():]
    return None, t


def parse_when(t, now):
    """Pull time expressions out of the question.
    Returns (mode, start, end, label, remaining_text); mode is 'at' (a moment) or 'range'."""
    day = None
    part = None
    label = ''

    if re.search(r'\b(right now|on now|currently|at the moment|now)\b', t):
        t = re.sub(r'\b(right now|on now|currently|at the moment|now)\b', ' ', t)
        return 'at', now, now, 'right now', t

    m = re.search(r'\btomorrow\s+(morning|afternoon|evening|night)\b', t) or re.search(r'\btomorrow\b', t)
    if m:
        day = _day_start(now) + timedelta(days=1)
        part = m.group(1) if m.groups() and m.lastindex else None
        label = 'tomorrow' + (' ' + part if part else '')
        t = t[:m.start()] + ' ' + t[m.end():]
    elif re.search(r'\btonight\b', t):
        day, part, label = _day_start(now), 'night', 'tonight'
        t = re.sub(r'\btonight\b', ' ', t)
    elif re.search(r'\b(this\s+)?weekend\b', t):
        t = re.sub(r'\b(this\s+)?weekend\b', ' ', t)
        sat = _day_start(now) + timedelta(days=(5 - now.weekday()) % 7)
        if now.weekday() == 6:
            sat = _day_start(now) - timedelta(days=1)
        return 'range', max(now, sat), sat + timedelta(days=2), 'this weekend', t
    else:
        m = re.search(r'\b(?:on\s+|this\s+|next\s+)?(' + '|'.join(WEEKDAYS) + r')s?(?:\s+(morning|afternoon|evening|night))?\b', t)
        if m:
            wd = WEEKDAYS.index(m.group(1))
            day = _day_start(now) + timedelta(days=(wd - now.weekday()) % 7)
            part = m.group(2)
            label = ('on ' + m.group(1).title()) + (' ' + part if part else '')
            t = t[:m.start()] + ' ' + t[m.end():]
        m = re.search(r'\b(this\s+)?(morning|afternoon|evening)\b', t)
        if m and day is None:
            day, part, label = _day_start(now), m.group(2), 'this ' + m.group(2)
            t = t[:m.start()] + ' ' + t[m.end():]
        if re.search(r'\btoday\b', t):
            day = day or _day_start(now)
            label = label or 'today'
            t = re.sub(r'\btoday\b', ' ', t)

    clock, t = _parse_clock(t)
    if clock:
        h, mi, explicit = clock
        if not explicit and 1 <= h <= 11:
            # TV questions mean evening unless the morning was asked about
            h = h if part == 'morning' else h + 12
        base = day or _day_start(now)
        at = base.replace(hour=h, minute=mi)
        if day is None and at + timedelta(minutes=30) < now:
            at += timedelta(days=1)
        when_word = label or ('tonight' if at.date() == now.date() and at.hour >= 17 else
                              'today' if at.date() == now.date() else _day_label(at, now))
        return 'at', at, at, f"at {_clock(at)} {when_word}".strip(), t

    if day is not None:
        windows = {'morning': (5, 12), 'afternoon': (12, 17), 'evening': (17, 22), 'night': (17, 28)}
        a, b = windows.get(part, (0, 24))
        start, end = day + timedelta(hours=a), day + timedelta(hours=b)
        return 'range', max(start, now), end, label, t

    return 'range', now, now + timedelta(days=8), '', t


def _clock(dt):
    return dt.strftime('%I:%M %p').lstrip('0')


def _day_label(dt, now):
    days = (dt.date() - now.date()).days
    if days == 0:
        return 'tonight' if dt.hour >= 17 else 'today'
    if days == 1:
        return 'tomorrow'
    if 1 < days < 7:
        return dt.strftime('%A')
    return dt.strftime('%a, %b ') + str(dt.day)


def when_label(dt, now):
    days = (dt.date() - now.date()).days
    if days == 0:
        return ('Tonight ' if dt.hour >= 17 else 'Today ') + _clock(dt)
    if days == 1:
        return 'Tomorrow ' + _clock(dt)
    if 1 < days < 7:
        return dt.strftime('%a ') + _clock(dt)
    return dt.strftime('%a, %b ') + str(dt.day) + ' · ' + _clock(dt)


# --- channel / topic parsing -------------------------------------------------------------

def parse_channel(t, lineup_names):
    """Returns (channel numbers or None, network patterns or None, label, remaining text)"""
    m = re.search(r'\b(?:on\s+)?(?:channel|ch\.?)\s*(\d{1,3}(?:\.\d{1,2})?)\b', t) or \
        re.search(r'\bon\s+(\d{1,3}\.\d{1,2})\b', t)
    if m:
        num = m.group(1)
        nums = [num] if '.' in num else [n for n in lineup_names if n.split('.')[0] == num]
        return nums or [num], None, f"channel {num}", t[:m.start()] + ' ' + t[m.end():]
    for name in sorted(NETWORKS, key=len, reverse=True):
        m = re.search(r'\b(?:on\s+)?' + re.escape(name) + r'\b', t)
        if m:
            return None, NETWORKS[name], name.upper(), t[:m.start()] + ' ' + t[m.end():]
    # Call signs like "kxan" / "on kvue" (skip ordinary words like "what" that merely look like one)
    for m in re.finditer(r'\b(?:on\s+)?([kw][a-z]{2,3})\b', t):
        call = m.group(1).upper()
        nums = [n for n, name in lineup_names.items() if name.upper().replace('-', '').startswith(call)]
        if nums:
            return nums, None, call, t[:m.start()] + ' ' + t[m.end():]
    return None, None, '', t


def find_title(t, programs):
    """Longest known show title mentioned in the question, so words like 'Saturday Night' in
    'Saturday Night Live' or 'Morning' in 'Good Morning America' aren't read as times.
    Returns (title_phrase or None, remaining text)."""
    titles = set()
    for p in programs:
        nt = normalize(p.get('title') or '').strip(" .:'-")
        # Skip titles made only of time/question words (a show called "Right Now" would
        # otherwise swallow "what's on right now")
        if len(nt) >= 6 and not all(w in STOPWORDS or w in WEEKDAYS for w in nt.split()):
            titles.add(nt)
    for nt in sorted(titles, key=len, reverse=True):
        m = re.search(r'(?<![a-z0-9])' + re.escape(nt) + r'(?![a-z0-9])', t)
        if m:
            return nt, t[:m.start()] + ' ' + t[m.end():]
    return None, t


def _stem(word):
    if len(word) > 4 and word.endswith('es') and not word.endswith(('ses', 'oes')):
        return word[:-1]
    if len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def parse_topic(t):
    """Returns (category or None, [[alternatives], ...] every group must match, words for display)"""
    t = re.sub(r'\b(the next|next)\b', ' ', t)
    category = None
    groups = []
    shown = []
    # Multi-word team nicknames first ("red raiders")
    for key in sorted(TEAM_ALIASES, key=len, reverse=True):
        if ' ' in key and re.search(r'\b' + re.escape(key) + r'\b', t):
            groups.append([key, ('team', TEAM_ALIASES[key])])
            shown.append(key)
            t = re.sub(r'\b' + re.escape(key) + r'\b', ' ', t)
    for word in re.findall(r"[a-z0-9&'.\-]+", t):
        word = word.strip(".'-")
        if not word or word in STOPWORDS:
            continue
        if word in CATEGORY_WORDS:
            category = category or CATEGORY_WORDS[word]
            if word in ('news',):
                groups.append(['news'])
                shown.append(word)
            continue
        if word in TEAM_ALIASES:
            groups.append([word, ('team', TEAM_ALIASES[word])])
            shown.append(word)
            continue
        base = word if word in SYNONYMS else _stem(word)
        groups.append(SYNONYMS.get(word) or SYNONYMS.get(base) or [base])
        shown.append(word)
    return category, groups, shown


# --- matching ----------------------------------------------------------------------------

def _program_start(p):
    try:
        return datetime.strptime(f"{p['date']} {p['time']}", '%Y-%m-%d %I:%M %p')
    except (KeyError, ValueError, TypeError):
        return None


def _is_sports(p):
    title = (p.get('title') or '').lower()
    return 'Sports' in (p.get('genre') or '') or any(w in title for w in SPORTS_TITLE_WORDS)


def _school_in(name, text):
    for m in re.finditer(r'(?<![a-z0-9])' + re.escape(name) + r'(?![a-z0-9])', text):
        after, before = text[m.end():], text[:m.start()]
        if not after.startswith(SCHOOL_NAME_AFTER) and not before.endswith(SCHOOL_NAME_BEFORE):
            return True
    return False


def _match_tier(p, groups, title_only=False):
    """How well a program matches every topic group: 2 = all in title or episode title
    (includes matchups like 'Ravens vs. Cowboys'), 1 = some only in the description, 0 = no match.
    title_only ignores episode titles and descriptions."""
    if not groups:
        return 2
    title = (p.get('title') or '').lower()
    head = title if title_only else title + ' | ' + (p.get('episode_title') or '').lower()
    desc = '' if title_only else (p.get('description') or '').lower()
    tier = 2
    for alts in groups:
        best = 0
        for alt in alts:
            if isinstance(alt, tuple) and alt[0] == 'title':  # a named show: its title, nothing else
                if re.search(r'(?<![a-z0-9])' + re.escape(alt[1]) + r'(?![a-z0-9])', normalize(p.get('title') or '')):
                    best = 2
                continue
            if isinstance(alt, tuple):  # ('team', 'texas'): school name, sports listings only
                if _is_sports(p) and _school_in(alt[1], head):
                    best = 2
                continue
            pat = r'(?<![a-z0-9])' + re.escape(alt)
            if re.search(pat, head):
                best = 2
            elif best < 1 and re.search(pat, desc):
                best = 1
        if not best:
            return 0
        tier = min(tier, best)
    return tier


def _find(programs, lineup, now, mode, win_start, win_end, strict_start, ch_nums, net_pats, category, groups,
          title_only=False, mentions=True):
    """Programs matching the filters, as (program, start, end, tier)"""
    out = []
    for p in programs:
        num = str(p.get('channel_number'))
        if lineup and num not in lineup:
            continue
        if ch_nums and num not in ch_nums:
            continue
        if net_pats and not any(pat in ' ' + (p.get('channel') or '').upper() for pat in net_pats):
            continue
        start = _program_start(p)
        if not start:
            continue
        end = start + timedelta(minutes=int(p.get('duration') or 30))
        if end <= now:
            continue
        if mode == 'at':
            if not (start <= win_start < end):
                continue
        elif strict_start:
            if not (win_start <= start < win_end):
                continue
        elif not (start < win_end and end > win_start):
            continue
        if category and category not in (p.get('genre') or '') and not (category == 'News' and groups):
            continue
        tier = _match_tier(p, groups, title_only)
        if tier == 2 or (tier == 1 and mentions):
            out.append((p, start, end, tier))
    # Title/matchup hits beat description mentions: only fall back to mentions when nothing else matches
    if out and max(m[3] for m in out) == 2:
        out = [m for m in out if m[3] == 2]
    return out


def _chan_key(num):
    try:
        return tuple(int(x) for x in str(num).split('.'))
    except ValueError:
        return (9999,)


def _shape(matches, lineup, now, coverage, distant=()):
    """Merge simulcasts (same show and time on several channels) and shape results for display.
    A local channel leads over a distant (out-of-market) one carrying the same airing."""
    merged = {}
    order = lambda m: (m[1], str(m[0].get('channel_number')) in distant, _chan_key(m[0].get('channel_number')))
    for p, start, end, tier in sorted(matches, key=order):
        num = str(p.get('channel_number'))
        key = (p.get('title'), p.get('episode_title'), start)
        if key in merged:
            r = merged[key]
            if num != r['channel_number'] and num not in r['also_on']:
                r['also_on'].append(num)
            continue
        merged[key] = {
            'title': p.get('title', ''),
            'episode_title': p.get('episode_title') or '',
            'description': (p.get('description') or '')[:220],
            'genre': p.get('genre') or '',
            'flags': p.get('flags') or [],
            'channel_number': num,
            'channel_name': lineup.get(num, p.get('call_sign', '')),
            'date': p.get('date'),
            'time': p.get('time'),
            'duration': int(p.get('duration') or 30),
            'start': start.timestamp(),
            'end': end.timestamp(),
            'when': when_label(start, now),
            'airing': start <= now < end,
            'also_on': [],
            'mention_only': tier == 1,
            'recording': coverage(num, start) if coverage else None,
        }
    return list(merged.values())


def _prefer_local(results, distant):
    """For a show a local station carries, drop airings only a distant station has (e.g. its reruns)"""
    if not distant:
        return results
    local_titles = {r['title'] for r in results if r['channel_number'] not in distant}
    return [r for r in results if r['channel_number'] not in distant or r['title'] not in local_titles]


def answer(question, programs, lineup, now=None, coverage=None, strict=False, distant=()):
    """Answer a guide question. lineup maps channel number -> tuner channel name.
    coverage(channel_number, start_dt) returns recording info for a program or None.
    strict=True (for text that isn't phrased as a question) only accepts title/matchup hits
    and returns None when nothing matches, so the caller can show help instead."""
    now = now or datetime.now()
    t = normalize(question)
    t = re.sub(r'^(record|tape|dvr)\s+', '', t)
    for short, full in ABBREVIATIONS.items():
        t = re.sub(r'\b' + short + r'\b', full, t)
    wants_next = bool(re.search(r'\b(next|upcoming|soonest|first)\b', t))

    title, t = find_title(t, programs)
    mode, win_start, win_end, when_text, t = parse_when(t, now)
    ch_nums, net_pats, ch_text, t = parse_channel(t, lineup)
    category, groups, words = parse_topic(t)
    if title:
        groups.insert(0, [('title', title)])
        words.insert(0, title)
    # Guides cached before categories were captured have no genres; don't filter on them
    if category and not any(p.get('genre') for p in programs[:2000]):
        category = None

    if mode == 'range' and not (groups or category or ch_nums or net_pats or when_text):
        return None  # nothing guide-shaped to go on

    # A named window that starts later ("tonight", "on Sunday") means shows starting in it,
    # not ones already running that spill over into it
    strict_start = mode == 'range' and bool(when_text) and win_start > now
    # A named show or plain words (strict) must match titles, not just be mentioned somewhere
    mentions = not (title or strict)
    found = _find(programs, lineup, now, mode, win_start, win_end, strict_start, ch_nums, net_pats, category, groups,
                  title_only=strict, mentions=mentions)

    # Nothing in the asked-for window: look at the whole guide so we can say when it IS on
    later = []
    if not found and groups and when_text:
        later = _shape(_find(programs, lineup, now, 'range', now, now + timedelta(days=15), False,
                             ch_nums, net_pats, category, groups, title_only=strict, mentions=False),
                       lineup, now, coverage, distant)
    if strict and not found and not later:
        return None

    results = _prefer_local(_shape(found, lineup, now, coverage, distant), distant)
    later = _prefer_local(later, distant)[:5]
    if mode == 'at':
        results.sort(key=lambda r: (r['channel_number'] in distant, _chan_key(r['channel_number'])))

    # What to call the thing asked about: the real title if one was named, else the words used
    shown = results or later
    if title and shown:
        thing = shown[0]['title']
    else:
        thing = ' '.join(words)
        ball_sport = thing in ('basketball', 'football', 'baseball', 'hockey', 'soccer', 'softball', 'volleyball')
        sporty = category == 'Sports' or (shown and thing and (ball_sport or any(w in TEAM_ALIASES for w in words))
                                          and all(r['genre'] == 'Sports' for r in shown))
        if sporty:
            thing = (thing + (' game' if wants_next or len(shown) == 1 else ' games')) if thing else 'sports'
        elif category == 'Movie' and not words:
            thing = 'movies'
        elif category and not thing:
            thing = category.lower()

    return {
        'status': 'guide_results',
        'message': _message(results, later, mode, thing, bool(title), when_text, ch_text, wants_next),
        'programs': (results or later)[:MAX_RESULTS],
        'total': len(results or later),
    }


def _sentence_start(s):
    return s[:1].upper() + s[1:] if s else s


def _message(results, later, mode, thing, is_title, when_text, ch_text, wants_next):
    where = ' '.join(x for x in ((f'on {ch_text}' if ch_text else ''), when_text) if x)
    if not results:
        if later:
            first = later[0]
            return (f"{_sentence_start(thing)} isn't on {when_text}. Next airing: "
                    f"{first['when']} on {first['channel_number']} {first['channel_name']}.")
        if mode == 'at':
            return f"Nothing in the guide {where}." if where else "Nothing found."
        return f"I couldn't find {thing or 'anything'} {where or 'in the guide for the next week'}."

    first = results[0]
    head = first['title'] + (f" ({first['episode_title']})" if first['episode_title'] else '')
    on = f"{first['channel_number']} {first['channel_name']}"
    n = len(results)
    if all(r['mention_only'] for r in results):
        return (f"No show called “{thing}”, but {n} {'listing mentions' if n == 1 else 'listings mention'} it"
                + (f" {where}" if where else '') + '.')
    if mode == 'at':
        if n == 1:
            return f"{_sentence_start(where)}: {head} on {on}."
        noun = thing if thing in ('movies', 'sports') else 'shows'
        return f"{n} {noun} {where}." if ch_text else f"{n} {noun} on {where}."
    if wants_next or is_title or n == 1:
        lead = first['title'] if is_title else (f"Next {thing}" if thing else 'Next up')
        what = f" ({first['episode_title']})" if is_title and first['episode_title'] else (f": {head}" if not is_title else '')
        more = f" {n - 1} more after that." if n > 1 else ''
        verb = ' is on now on ' if first['airing'] else ', '
        when = '' if first['airing'] else f"{first['when']} on "
        return f"{lead}{what}{verb}{when}{on}.{more}".replace(', on now', ' on now')
    label = f"{n} {'airings' if thing else 'shows'}" + (f" of {thing}" if thing else '')
    return label + (f" {where}" if where else '') + '.'
