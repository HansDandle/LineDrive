"""
Request movies and shows through Jellyseerr, which hands them to Radarr/Sonarr.

Config (config.json):
    "jellyseerr": {"url": "http://localhost:5055", "api_key": "..."}
The API key is Jellyseerr's (Settings -> General -> API Key); requests made with it are
auto-approved as the admin user.
"""
import re
from urllib.parse import quote
import requests

# Jellyseerr MediaStatus values
STATUS_LABELS = {
    2: 'Waiting for approval',
    3: 'Requested',
    4: 'Partly in your library',
    5: 'In your library',
}
POSTER_BASE = 'https://image.tmdb.org/t/p/w154'


class MediaRequestError(Exception):
    pass


class Jellyseerr:
    def __init__(self, url, api_key, timeout=15):
        self.url = url.rstrip('/')
        self.headers = {'X-Api-Key': api_key}
        self.timeout = timeout

    def _get(self, path, **params):
        r = requests.get(self.url + path, params=params, headers=self.headers, timeout=self.timeout)
        if r.status_code >= 400:
            raise MediaRequestError(f"Jellyseerr said {r.status_code}: {r.text[:160]}")
        return r.json()

    def search(self, query, media_type=None, limit=6):
        """Movies/shows matching `query` (media_type 'movie' or 'tv' narrows it), with library status"""
        # Jellyseerr rejects '+' for spaces (what requests sends); it wants %20
        data = self._get('/api/v1/search?query=' + quote(query, safe='') + '&page=1')
        out = []
        for x in data.get('results', []):
            kind = x.get('mediaType')
            if kind not in ('movie', 'tv') or (media_type and kind != media_type):
                continue
            status = (x.get('mediaInfo') or {}).get('status')
            date = x.get('releaseDate') or x.get('firstAirDate') or ''
            out.append({
                'media_type': kind,
                'id': x.get('id'),
                'title': x.get('title') or x.get('name') or '',
                'year': date[:4],
                'overview': (x.get('overview') or '')[:240],
                'poster': POSTER_BASE + x['posterPath'] if x.get('posterPath') else '',
                'status': status,
                'status_label': STATUS_LABELS.get(status, ''),
                'popularity': x.get('popularity') or 0,
            })
            if len(out) >= limit:
                break
        return out

    def seasons(self, tv_id):
        """[(season_number, episode_count)] for a show, skipping specials"""
        data = self._get(f'/api/v1/tv/{int(tv_id)}')
        return [(s['seasonNumber'], s.get('episodeCount', 0)) for s in data.get('seasons', [])
                if s.get('seasonNumber', 0) > 0]

    def request(self, media_type, media_id, seasons=None):
        """Request a movie, or a show (seasons: list of numbers, or None for all). Returns Jellyseerr's reply."""
        body = {'mediaType': media_type, 'mediaId': int(media_id)}
        if media_type == 'tv':
            body['seasons'] = [int(s) for s in seasons] if seasons else [n for n, _ in self.seasons(media_id)]
        r = requests.post(self.url + '/api/v1/request', json=body, headers=self.headers, timeout=self.timeout)
        if r.status_code == 409:
            raise MediaRequestError('Already requested')
        if r.status_code >= 400:
            try:
                msg = r.json().get('message') or r.text
            except ValueError:
                msg = r.text
            raise MediaRequestError(f"Jellyseerr couldn't request it: {msg[:160]}")
        return r.json()


DOWNLOAD_VERBS = r'^(?:please\s+)?(?:download|request|get me|get|grab|add|i want|can you get)\s+'


def parse_download_request(text):
    """'download season 2 of the bear' -> ('the bear', 'tv', [2]); 'get dune part two' -> ('dune part two', None, None).
    Returns None if the text isn't a download request."""
    t = (text or '').strip().lower().rstrip('?.!')
    if not re.match(DOWNLOAD_VERBS, t):
        return None
    t = re.sub(DOWNLOAD_VERBS, '', t)
    media_type = None
    if re.search(r'\b(the\s+)?(movie|film)\b', t):
        media_type = 'movie'
        t = re.sub(r'\b(the\s+)?(movie|film)\b', ' ', t)
    seasons = None
    m = re.search(r'\bseasons?\s+(\d+)(?:\s*(?:-|to|through|and|,)\s*(\d+))?\s*(?:of\s+)?', t)
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        seasons = list(range(min(a, b), max(a, b) + 1))
        media_type = 'tv'
        t = t[:m.start()] + ' ' + t[m.end():]
    if re.search(r'\b(the\s+)?(show|series|tv show)\b', t):
        media_type = 'tv'
        t = re.sub(r'\b(the\s+)?(show|series|tv show)\b', ' ', t)
    t = re.sub(r'\b(all\s+seasons|every season|the whole thing|for me)\b', ' ', t)
    title = re.sub(r'\s+', ' ', t).strip(' -:')
    return (title, media_type, seasons) if title else None
