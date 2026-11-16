"""Complete published forecast history, including predictions awaiting settlement."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import live, pages


def collect(results, published, events=()):
    rows = {}
    identity = lambda m: (m.get('sport') or 'football', m.get('div') or '', str(m['id']))
    current = {identity(e): e for e in events}
    for r in results.to_dict('records'):
        key = identity(r)
        ok = str(r.get('main_hit', '')).lower() in ('true', '1', '1.0')
        rows[key] = dict(id=str(r['id']), sport=key[0], div=key[1], home=str(r['home']), away=str(r['away']),
            kickoff=str(r['date'])[:10] + 'T00:00:00+03:00', date=str(r['date'])[:10],
            label=str(r['main_label']), odds=float(r['main_odds']), score=str(r.get('score') or ''),
            status='won' if ok else 'lost', est=str(r.get('main_est')).lower() in ('true', '1', '1.0'), url='', watch='', telegram='', lives=[])
    for m in published.values():
        if not m.get('msg_id') or not m.get('main') or not m.get('id'):
            continue
        h, a = m.get('home', {}).get('ru'), m.get('away', {}).get('ru')
        if not h or not a or not m.get('kickoff'):
            continue
        key = identity(m)
        ko = pd.Timestamp(m['kickoff'])
        if ko.tzinfo is None:
            ko = ko.tz_localize('Europe/Moscow')
        ko = ko.tz_convert('Europe/Moscow')
        day = ko.strftime('%Y-%m-%d')
        btn = live._tracker(m, key[0], h, a)
        row = rows.get(key) or dict(id=str(m['id']), sport=key[0], div=key[1], home=h, away=a,
            label=m['main']['label'], odds=m['main'].get('odds'), est=bool(m['main'].get('est')), score='', lives=[],
            status='in' if current.get(key, {}).get('state') == 'in' else 'pending')
        row.update(kickoff=ko.isoformat(), date=day,
            url=f"predictions/{day}-{pages.slug(h+' '+a,60)}-{m['id']}.html",
            watch=btn[1].replace(pages.SITE, '') if btn else '', telegram=f"https://t.me/aistavvit/{m['msg_id']}")
        rows[key] = row
    return sorted(rows.values(), key=lambda r: (r['kickoff'], r['id']), reverse=True)


def write(results, docs: Path):
    data = docs.parent / 'data'
    def load(path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return default
    published = {**load(data / 'matches.json', {}), **load(data / 'other.json', {})}
    rows = collect(results, published, load(docs / 'matches.json', []))
    from . import pro
    hosts = {(r['date'], r['home'] + ' — ' + r['away']): r for r in rows}
    for row in pro.live_bets().to_dict('records'):
        host = hosts.get((str(row.get('date'))[:10], str(row.get('match'))))
        if host is not None:
            hit = row.get('hit')
            host['lives'].append(dict(label=str(row.get('label') or ''), odds=float(row.get('min_odds') or 0),
                ok=None if hit is None or pd.isna(hit) else str(hit).lower() in ('true', '1', '1.0')))
    for row in rows:
        if row.get('url') and not (docs / row['url']).exists():
            row['url'] = ''
    text = json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (docs / 'forecast-feed.json').write_text(text, encoding='utf-8')
    return rows
