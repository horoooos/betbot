"""Discover public match broadcasts. No video proxy, guessed URLs or replay-as-live.

PandaScore supplies event-specific esports streams; official YouTube channels
supply live listings; ESPN supplies event-specific broadcaster/watch references.
Every result carries its evidence, observation time and expiration.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'data' / 'broadcast_sources.json'
DB = 'https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app'
SPORTS = ('football', 'hockey', 'basketball', 'tennis', 'esports')


def norm(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value)).lower()
                   if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+', text))


def public_video(url):
    """Canonical allowlisted provider URLs only; never retain tracking/auth query."""
    try:
        p = urlsplit(str(url))
        if p.scheme != 'https' or p.username or p.password or p.port:
            return None
        host, parts = (p.hostname or '').lower(), p.path.strip('/').split('/')
        if host in ('twitch.tv', 'www.twitch.tv') and len(parts) == 1:
            channel = parts[0].lower()
            if re.fullmatch(r'[a-z0-9_]{2,30}', channel) and channel not in {
                'directory', 'videos', 'downloads', 'settings', 'subscriptions', 'search'}:
                return dict(provider='twitch', channel=channel, url='https://www.twitch.tv/' + channel)
        if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
            video = (parts[0] if host == 'youtu.be' else
                     parse_qs(p.query).get('v', [''])[0] if p.path == '/watch' else
                     parts[1] if len(parts) == 2 and parts[0] == 'live' else '')
            if re.fullmatch(r'[\w-]{11}', video, flags=re.ASCII):
                return dict(provider='youtube', video_id=video, url='https://www.youtube.com/watch?v=' + video)
    except (TypeError, ValueError):
        pass
    return None


def panda_streams(raw):
    candidates = list(raw.get('streams_list') or [])
    for lang in ('russian', 'english'):
        if isinstance(raw.get(lang), dict):
            candidates.append({**raw[lang], 'language': lang})
    if raw.get('official_stream_url'):
        candidates.append({'raw_url': raw['official_stream_url'], 'official': True})
    out = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        video = public_video(item.get('raw_url'))
        if video:
            video.update(language=str(item.get('language') or '')[:20],
                         source='PandaScore', official=item.get('official') is True,
                         status='listed', access='unknown')
            out[video['url']] = video
    return list(out.values())


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def initial_json(html, variable):
    found = re.search(r'(?:var\s+)?' + re.escape(variable) + r'\s*=\s*', html)
    if not found:
        raise ValueError('Provider listing unavailable')
    return json.JSONDecoder().raw_decode(html[found.end():])[0]


def youtube_listing(html):
    """Accept an actual LIVE badge, never the word LIVE in a video title."""
    data = initial_json(html, 'ytInitialData')
    out = {}
    for node in walk(data):
        if 'videoRenderer' in node:
            item = node['videoRenderer']
            live = any(x.get('style') in ('LIVE', 'BADGE_STYLE_TYPE_LIVE_NOW')
                       for x in walk([item.get('badges'), item.get('thumbnailOverlays')]))
            title = ''.join(x.get('text', '') for x in item.get('title', {}).get('runs', []))
            vid = item.get('videoId')
        elif 'lockupViewModel' in node:
            item = node['lockupViewModel']
            live = any(x.get('badgeStyle') == 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE'
                       or x.get('text', '').upper() == 'LIVE' for x in walk(item.get('contentImage')))
            title = item.get('metadata', {}).get('lockupMetadataViewModel', {}).get('title', {}).get('content', '')
            vid = item.get('contentId')
        else:
            continue
        video = public_video('https://www.youtube.com/watch?v=' + str(vid))
        if live and video:
            out[vid] = {**video, 'title': title}
    return list(out.values())


def title_matches(title, participants):
    """Both participants required, no last-name-only fuzzy matches or short tags."""
    title = ' ' + norm(title) + ' '
    if re.search(r'\b(highlights?|replay|rerun|обзор|повтор|запись)\b', title):
        return False
    return len(participants) == 2 and all(any(
        len(norm(alias).replace(' ', '')) >= 4 and ' ' + norm(alias) + ' ' in title
        for alias in aliases if alias) for aliases in participants)


def live_title_teams(title):
    """A discovered official match can exist even without our own forecast/schedule."""
    if re.search(r'\b(highlights?|replay|rerun|обзор|повтор|запись)\b', norm(title)):
        return None
    title = re.sub(r'^\s*LIVE\s*[-:|]?\s*', '', title, flags=re.I)
    title = re.split(r'\s[|]\s|\s-\s', title, maxsplit=1)[0]
    teams = re.split(r'\s+(?:vs?\.?|—)\s+', title, maxsplit=1, flags=re.I)
    if len(teams) == 2 and all(4 <= len(norm(t).replace(' ', '')) <= 80 for t in teams):
        return teams
    return None


def load_events(remote=False):
    try:
        events = json.loads((ROOT / 'docs/matches.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        events = []
    if remote:
        # The scan runner's checkout may be older than the latest bot update.
        events = json.loads(get_text('https://raw.githubusercontent.com/horoooos/betbot/main/docs/matches.json'))
    # Preserve the English participant names for public broadcast title matching.
    aliases = {}
    for name in ('matches.json', 'other.json'):
        try:
            data = json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))
            for event in data.values() if isinstance(data, dict) else data:
                aliases[(str(event.get('id')), event.get('div'))] = event
        except (OSError, ValueError, TypeError):
            continue
    now = time.time()
    out = []
    for event in events:
        try:
            kickoff = datetime.fromisoformat(event['kickoff']).timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        if event.get('state') == 'post' or not now - 8*3600 <= kickoff <= now + 24*3600:
            continue
        old = aliases.get((str(event.get('id')), event.get('div')), {})
        event = {**event, 'participants': event.get('participants') or
                 [[event.get(side, ''), (old.get(side) or {}).get('name', '')] for side in ('home', 'away')]}
        out.append(event)
    try:
        native = json.loads(get_text(DB + '/esportsLive/index.json')) or {}
        for game in (native.get('games') or {}).values():
            if game.get('state') != 5 or now - game.get('at', 0) > 90 or len(game.get('teams', [])) != 2:
                continue
            a, b = [t['name'] for t in game['teams']]
            out.append(dict(sport='esports', div='DOTA', id='dota-' + str(game['match_id']),
                            home=a, away=b, kickoff=datetime.fromtimestamp(now).astimezone().isoformat(),
                            participants=[[a], [b]], state='in'))
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return out


def get_text(url):
    response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    response.raise_for_status()
    return response.content.decode('utf-8')


def check_youtube(video):
    data = initial_json(get_text(video['url'] + '&hl=en'), 'ytInitialPlayerResponse')
    details = data.get('microformat', {}).get('playerMicroformatRenderer', {}).get('liveBroadcastDetails', {})
    if details.get('isLiveNow') is not True:
        return None
    return {**video, 'status': 'live', 'access': 'public',
            'embeddable': data.get('playabilityStatus', {}).get('playableInEmbed') is True,
            'evidence': 'Official channel LIVE listing and watch-page isLiveNow'}


def discover(events=None, config=None):
    from . import esports
    now = int(time.time())
    events = load_events() if events is None else events
    config = config or json.loads(CONFIG.read_text(encoding='utf-8'))
    results, report = {}, []

    def record(event):
        key = ':'.join(str(event.get(k) or '') for k in ('sport', 'div', 'id'))
        return results.setdefault(key, {k: event.get(k) for k in
            ('sport', 'div', 'id', 'home', 'away', 'kickoff', 'participants')} | {'streams': []})

    for event in events:
        record(event)

    # Direct event metadata: all available tournament tiers, independent of forecasts.
    for code, game in esports.GAMES.items():
        count, errors = 0, 0
        if esports.enabled():
            for kind in ('running', 'upcoming'):
                try:
                    response = requests.get(esports.API + '/' + game + '/matches/' + kind,
                                            params={'per_page': 100}, timeout=20,
                                            headers={'Authorization': 'Bearer ' + os.environ['PANDASCORE_TOKEN']})
                    response.raise_for_status()
                    batch = response.json()
                    if not isinstance(batch, list):
                        raise ValueError('Unexpected match list')
                except (requests.RequestException, ValueError):
                    errors += 1
                    continue
                for raw in batch:
                    event = esports._normalize(code, raw)
                    if not event:
                        continue
                    kickoff = datetime.fromisoformat(event['kickoff']).timestamp()
                    if not now - 12*3600 <= kickoff <= now + 24*3600:
                        continue
                    e = {**event, 'home': event['home']['name'], 'away': event['away']['name'],
                         'participants': [[event['home']['name']], [event['away']['name']]]}
                    row = record(e)
                    for stream in panda_streams(raw):
                        # Being listed on a running fixture doesn't prove a channel is live.
                        row['streams'].append({**stream, 'checked_at': now, 'expires_at': now + 900,
                                              'evidence': 'Event-specific broadcast URL in match metadata'})
                        count += 1
                    if not any(x.get('sport') == 'esports' and x.get('div') == code and x.get('id') == e['id'] for x in events):
                        events.append(e)
        report.append({'source': 'PandaScore ' + code,
                       'status': ('partial' if errors else 'ok') if esports.enabled() else 'no_credentials',
                       'found': count, 'errors': errors})

    def scan_channel(channel):
        identity = channel.get('channel_id') or channel.get('handle', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', identity):
            raise ValueError('Invalid configured channel')
        path = 'channel/' + identity if channel.get('channel_id') else '@' + identity
        return channel, youtube_listing(get_text('https://www.youtube.com/' + path + '/streams?hl=en'))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scan_channel, c): c for c in config.get('youtube', [])}
        for future in concurrent.futures.as_completed(futures):
            channel = futures[future]
            try:
                _, videos = future.result()
                found = 0
                for video in videos:
                    matches = [e for e in events if e.get('sport') in channel['sports']
                               and title_matches(video['title'], e['participants'])
                               and datetime.fromisoformat(e['kickoff']).timestamp() <= now + 1200]
                    if not matches and len(channel['sports']) == 1:
                        teams = live_title_teams(video['title'])
                        if teams:
                            matches = [dict(sport=channel['sports'][0], div='', id='youtube-' + video['video_id'],
                                            home=teams[0], away=teams[1], participants=[[teams[0]], [teams[1]]],
                                            kickoff=datetime.fromtimestamp(now).astimezone().isoformat())]
                    if not matches:
                        continue
                    try:
                        verified = check_youtube(video)
                    except (requests.RequestException, ValueError, KeyError, TypeError):
                        continue
                    if not verified:
                        continue
                    for e in matches:
                        record(e)['streams'].append({**verified, 'source': channel['name'], 'official': True,
                                                     'checked_at': now, 'expires_at': now + 600})
                        found += 1
                report.append({'source': channel['name'], 'status': 'ok', 'live_listings': len(videos), 'found': found})
            except (requests.RequestException, ValueError, KeyError, TypeError):
                report.append({'source': channel['name'], 'status': 'unavailable', 'found': 0})

    # ESPN watch references may require subscription or be geoblocked. Never mark free/live.
    def espn_event(event):
        path = event.get('path') or ''
        if not re.fullmatch(r'(soccer|hockey|basketball|tennis)/[a-zA-Z0-9._-]+', path) or not str(event.get('id', '')).isdigit():
            return event, []
        raw = json.loads(get_text('https://site.api.espn.com/apis/site/v2/sports/' + path + '/summary?event=' + str(event['id'])))
        return event, espn_streams(raw)

    espn_count, espn_errors = 0, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(espn_event, e) for e in events if e.get('sport') != 'esports']
        for job in concurrent.futures.as_completed(jobs):
            try:
                event, streams = job.result()
                for stream in streams:
                    record(event)['streams'].append({**stream, 'checked_at': now, 'expires_at': now + 900})
                    espn_count += 1
            except (requests.RequestException, ValueError, KeyError, TypeError):
                espn_errors += 1
    report.append({'source': 'ESPN event broadcasts', 'status': 'partial' if espn_errors else 'ok', 'found': espn_count, 'errors': espn_errors})
    for row in results.values():
        row['streams'] = list({s['url']: s for s in row['streams']}.values())
        row['searched_at'] = now
    return {'at': now, 'interval': 300, 'sports': list(SPORTS), 'matches': list(results.values()), 'sources': report}


def espn_streams(raw):
    out = {}
    # Video highlights and generic event summary links are deliberately excluded.
    for node in walk(raw.get('header', {})):
        for link in node.get('links', []) if isinstance(node.get('links'), list) else []:
            if not isinstance(link, dict) or 'watch' not in (link.get('rel') or []):
                continue
            url = link.get('href', '')
            p = urlsplit(url)
            if (p.scheme == 'https' and p.hostname in ('www.espn.com', 'espn.com')
                    and p.path.startswith('/watch/') and not p.username and not p.password and not p.port):
                # ESPN IDs are public identifiers; no arbitrary tokens/query strings.
                query = parse_qs(p.query)
                public_id = query.get('id', [''])[0]
                clean = 'https://www.espn.com' + p.path
                if public_id and re.fullmatch(r'[a-zA-Z0-9-]+', public_id):
                    clean += '?id=' + public_id
                out[clean] = dict(provider='external', url=clean, source='ESPN', status='listed',
                                  access='unknown', official=True, embeddable=False,
                                  evidence='Event-specific watch link; subscription/region may apply')
    return list(out.values())
