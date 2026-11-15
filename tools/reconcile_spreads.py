"""Reconcile historical basketball handicaps using the published label and score.

Default is read-only. --apply corrects only verified boolean settlement fields
and appends an audit record; odds, predictions, dates and scores stay unchanged.
"""
import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betbot import sports


def reconcile(frame):
    corrected = frame.copy()
    changes = []
    for index, row in frame.iterrows():
        for kind in ('main', 'bold'):
            key = row.get(kind + '_key')
            if key not in ('BB_SPR_H', 'BB_SPR_A'):
                continue
            home, away = map(int, str(row['score']).split(':'))
            tip = {'label': row[kind + '_label']}
            handicap = sports.published_spread(tip)
            margin = (home-away if key == 'BB_SPR_H' else away-home) + handicap
            if margin == 0:
                raise ValueError('Push requires explicit refund handling; no automatic correction')
            new = bool(margin > 0)
            old = str(row[kind + '_hit']).lower() in ('true', '1', '1.0')
            if old == new:
                continue
            changes.append(dict(id=str(row['id']), div=row['div'], date=row['date'], kind=kind,
                                label=tip['label'], score=row['score'], old=old, new=new,
                                reason='Settlement uses handicap frozen in the published label'))
            corrected.at[index, kind + '_hit'] = new
    return corrected, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / 'data/results.csv'
    corrected, changes = reconcile(pd.read_csv(path, dtype={'id': str}))
    print(json.dumps(changes, ensure_ascii=False, indent=2))
    if args.apply and changes:
        audit_path = root / 'data/settlement_corrections.json'
        audit = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else []
        stamp = datetime.now(timezone.utc).isoformat()
        audit += [{**change, 'applied_at': stamp} for change in changes]
        temporary = path.with_suffix('.audit.tmp')
        # Preserve the recorded representation of every other CSV field.
        raw = path.read_bytes().decode('utf-8')
        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)
        changes_by_key = {(c['div'], c['id'], c['date'], c['kind']): c for c in changes}
        for row in rows:
            for kind in ('main', 'bold'):
                change = changes_by_key.get((row['div'], row['id'], row['date'], kind))
                if change:
                    row[kind + '_hit'] = str(change['new'])
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames,
                                lineterminator='\r\n' if '\r\n' in raw else '\n')
        writer.writeheader()
        writer.writerows(rows)
        temporary.write_bytes(output.getvalue().encode('utf-8'))
        temporary.replace(path)
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Applied verified corrections:', len(changes))


if __name__ == '__main__':
    main()
