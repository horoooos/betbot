"""One bounded broadcast discovery pass, suitable for free GitHub runners."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from betbot import broadcasts


def publish(payload):
    # Use the existing runner service account; expose only this public result path.
    from dota_live_relay import admin_session, DB
    session = admin_session()
    url = DB + '/.settings/rules.json'
    response = session.get(url, headers={'X-Firebase-ETag': 'true'}, timeout=20)
    response.raise_for_status()
    rules = response.json()
    branch = rules.setdefault('rules', {}).get('broadcasts')
    desired = {'.read': True, '.write': False}
    if branch != desired:
        if branch is not None:
            raise RuntimeError('Existing broadcast rules require review')
        rules['rules']['broadcasts'] = desired
        headers = {'if-match': response.headers['ETag']} if response.headers.get('ETag') else {}
        response = session.put(url, json=rules, headers=headers, timeout=20)
        response.raise_for_status()
    response = session.put(DB + '/broadcasts.json', json=payload, timeout=20)
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--out', default='work/broadcasts-check.json')
    args = parser.parse_args()
    payload = broadcasts.discover(broadcasts.load_events(remote=args.remote))
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.publish:
        publish(payload)
    print(json.dumps({'at': payload['at'], 'matches': len(payload['matches']),
                      'with_streams': sum(bool(m['streams']) for m in payload['matches']),
                      'sources': payload['sources']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
