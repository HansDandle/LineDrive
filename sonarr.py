"""Sonarr handoff: after LineDrive records an episode, unmonitor it in Sonarr so Sonarr doesn't
also download it.

Only the episode's monitored flag changes. LineDrive never moves, imports or deletes anything in
Sonarr, so Sonarr doesn't need to see the recordings folder. Shows Sonarr doesn't have, episodes
it already has a file for and ones that are already unmonitored are left alone.
"""
import re

import requests

TIMEOUT = 15


def norm(title):
    """'The Office (US)' -> 'office', 'Law & Order: SVU' -> 'law and order svu'"""
    t = re.sub(r'\s*\([^)]*\)\s*$', '', str(title or '')).lower().replace('&', ' and ')
    t = re.sub(r'[^a-z0-9]+', ' ', t).strip()
    return re.sub(r'^the ', '', t)


def series_matches(series_list, title):
    """Sonarr series whose title or an alternate title is this show's (a regional suffix like
    '(US)' is ignored, so 'Ghosts' can match more than one)"""
    want = norm(title)
    if not want:
        return []
    return [s for s in series_list
            if want in {norm(s.get('title'))} | {norm(a.get('title')) for a in s.get('alternateTitles') or []}]


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_episode(episodes, season=None, number=None, air_date=None, episode_title=None):
    """The episode a recording is, by season and episode number, else the only one that aired on
    air_date (YYYY-MM-DD), else the only one with that title. None if it can't be told."""
    season, number = _int(season), _int(number)
    want = norm(episode_title)

    def agrees(e):
        # Titles that disagree mean another show with the same name: a rerun of the original
        # 'Scrubs' is numbered S01E05 too, and may air the day the revival's S01E05 does
        have = norm(e.get('title'))
        return not (want and have and have != want)

    if season is not None and number is not None:
        hit = [e for e in episodes if e.get('seasonNumber') == season and e.get('episodeNumber') == number]
        if hit and agrees(hit[0]):
            return hit[0]
    if air_date:
        hit = [e for e in episodes if e.get('airDate') == air_date and e.get('seasonNumber') and agrees(e)]
        if len(hit) == 1:
            return hit[0]
    if want:
        hit = [e for e in episodes if norm(e.get('title')) == want]
        if len(hit) == 1:
            return hit[0]
    return None


def label(series, episode):
    return f"{series.get('title')} S{episode.get('seasonNumber', 0):02d}E{episode.get('episodeNumber', 0):02d}"


class Sonarr:
    def __init__(self, url, api_key):
        self.base = url.rstrip('/') + '/api/v3'
        self.headers = {'X-Api-Key': api_key}

    def _get(self, path, **params):
        r = requests.get(self.base + path, headers=self.headers, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def status(self):
        return self._get('/system/status')

    def handoff(self, title, season=None, number=None, air_date=None, episode_title=None):
        """Unmonitor the recorded episode. Returns (changed, message)."""
        candidates = series_matches(self._get('/series'), title)
        if not candidates:
            return False, f"{title} isn't in Sonarr"
        for series in candidates:
            ep = find_episode(self._get('/episode', seriesId=series['id']), season, number, air_date, episode_title)
            if ep is None:
                continue
            name = label(series, ep)
            if ep.get('hasFile'):
                return False, f"Sonarr already has {name}"
            if not ep.get('monitored'):
                return False, f"{name} is already unmonitored in Sonarr"
            r = requests.put(self.base + '/episode/monitor', headers=self.headers, timeout=TIMEOUT,
                             json={'episodeIds': [ep['id']], 'monitored': False})
            r.raise_for_status()
            return True, f"Unmonitored {name} in Sonarr so it won't download it"
        return False, f"Couldn't tell which episode of {title} this is in Sonarr"
