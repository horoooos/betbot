"""Keyless Valve Dota positions -> dedicated, publicly readable Firebase path.

Runs on GitHub's runner. Credentials stay there. No fabricated positions or scores.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import time

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

DB = 'https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app'
VALVE = 'https://www.dota2.com/webapi/'
PATH = 'esportsLive'


def snapshot(raw, now=None):
    """Only render complete real frames; starting lobbies have zero coordinates."""
    if not isinstance(raw, dict):
        return None
    match = raw.get('match') or {}
    teams = raw.get('teams') or []
    players = [p for t in teams for p in (t.get('players') or [])]
    if len(players) != 10 or not any(p.get('x') or p.get('y') for p in players):
        return None
    def pos(p):
        x, y = float(p.get('x', 0)), float(p.get('y', 0))
        if not math.isfinite(x) or not math.isfinite(y) or abs(x) > 2 or abs(y) > 2:
            raise ValueError('Invalid coordinate')
        return x, y
    out = dict(match_id=str(match['match_id']), at=int(now or time.time()), game_time=match.get('game_time'),
               timestamp=match.get('timestamp'), state=match.get('game_state'), teams=[], buildings=[])
    gold_graph = (raw.get('graph_data') or {}).get('graph_gold') or []
    if gold_graph:
        step = max(1, math.ceil(len(gold_graph) / 120))
        out['gold_graph'] = gold_graph[::step]
        if (len(gold_graph) - 1) % step:
            out['gold_graph'].append(gold_graph[-1])
    for t in teams:
        out['teams'].append(dict(id=str(t.get('team_id') or ''), name=t.get('team_name') or '',
            team=t['team_number'], score=t.get('score'), networth=t.get('net_worth'), players=[dict(
                id=str(p.get('playerid')), name=p.get('name', ''), hero=p.get('heroid'),
                x=pos(p)[0], y=pos(p)[1], level=p.get('level'), kills=p.get('kill_count'),
                deaths=p.get('death_count'), assists=p.get('assists_count'), networth=p.get('net_worth'),
                gold=p.get('gold'), last_hits=p.get('lh_count'), denies=p.get('denies_count'),
                abilities=(p.get('abilities') or [])[:32], items=(p.get('items') or [])[:16],
                hp=p.get('health'), max_hp=p.get('max_health'), mana=p.get('mana'), max_mana=p.get('max_mana'))
                for p in t.get('players') or []]))
    for b in raw.get('buildings') or []:
        out['buildings'].append(dict(x=pos(b)[0], y=pos(b)[1], team=b.get('team'), type=b.get('type'),
                                     destroyed=bool(b.get('destroyed'))))
    return out


def admin_session():
    info = json.loads(os.environ['FIREBASE_SA'])
    credentials = service_account.Credentials.from_service_account_info(info, scopes=[
        'https://www.googleapis.com/auth/firebase.database', 'https://www.googleapis.com/auth/userinfo.email'])
    return AuthorizedSession(credentials)


def configure(session):
    # Preserve every existing rule; expose only new match telemetry, never writes.
    url = DB + '/.settings/rules.json'
    r = session.get(url, headers={'X-Firebase-ETag': 'true'}, timeout=20)
    if not r.ok:
        raise RuntimeError(f'Cannot read database rules: HTTP {r.status_code}')
    rules = r.json()
    branch = rules.setdefault('rules', {}).get(PATH)
    desired = {'.read': True, '.write': False}
    if branch != desired:
        if branch is not None:
            raise RuntimeError('Existing telemetry rules require review; no rule overwritten')
        rules['rules'][PATH] = desired
        put = session.put(url, json=rules, headers={'if-match': r.headers['ETag']} if r.headers.get('ETag') else {}, timeout=20)
        if not put.ok:
            raise RuntimeError(f'Cannot configure telemetry read: HTTP {put.status_code}')
    print('Dedicated live-data read enabled; browser writes denied', flush=True)


def fetch_frame(game):
    r = requests.get(VALVE + 'IDOTA2MatchStats/GetRealtimeStats/v001',
                     params={'server_steam_id': game['server_steam_id']}, timeout=12)
    r.raise_for_status()
    frame = snapshot(r.json())
    if frame:
        for team in frame['teams']:
            if not team['name']:
                team['name'] = game.get('radiant_name' if team['team'] == 2 else 'dire_name', '')
    return frame


def collect():
    r = requests.get(VALVE + 'IDOTA2League/GetLiveGames/v001', timeout=15)
    r.raise_for_status()
    data = r.json()
    games = data.get('games') or data.get('result', {}).get('games') or []
    # Named tournament matches first; never publish anonymous player/account data.
    games = [g for g in games if g.get('radiant_name') and g.get('dire_name') and g.get('server_steam_id')]
    frames = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(fetch_frame, g): g for g in games[:12]}
        for future in concurrent.futures.as_completed(pending):
            try:
                frame = future.result()
                if frame:
                    frames[frame['match_id']] = frame
            except (requests.RequestException, ValueError, KeyError, TypeError):
                pass
    return {'at': int(time.time()), 'games': frames, 'source': 'Valve', 'interval': 10}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=float, default=0)
    parser.add_argument('--configure', action='store_true')
    args = parser.parse_args()
    session = admin_session()
    if args.configure:
        configure(session)
    deadline = time.monotonic() + args.hours * 3600
    errors = 0
    while True:
        started = time.monotonic()
        try:
            payload = collect()
            r = session.put(DB + '/' + PATH + '.json', json=payload, timeout=20)
            if not r.ok:
                raise RuntimeError(f'Telemetry write HTTP {r.status_code}')
            print(f"Live frames: {len(payload['games'])}, at {payload['at']}", flush=True)
            errors = 0
        except Exception as exc:
            # Do not log request URLs, tokens or credential-bearing exception text.
            print(f'Live relay retry: {type(exc).__name__}', flush=True)
            errors += 1
            if errors >= 10:
                raise RuntimeError('Repeated live relay failures') from None
        if time.monotonic() >= deadline:
            break
        time.sleep(max(1, (min(120, 10 * 2**errors) if errors else 10) - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
