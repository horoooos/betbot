import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from betbot import esports


class EsportsCoverageTests(unittest.TestCase):
    def test_targeted_history_excludes_invalid_rows_and_reuses_cache(self):
        now = pd.Timestamp.now(tz='UTC')
        def raw(i, **changes):
            value = dict(id=i, begin_at=(now-pd.Timedelta(days=i)).isoformat(), status='finished',
                         winner_id=1, opponents=[{'opponent': {'id': t, 'name': str(t)}} for t in (1, 2)])
            value.update(changes)
            return value
        event = dict(div='DOTA', state='pre', kickoff=(now+pd.Timedelta(hours=1)).isoformat(),
                     home={'id': '1'}, away={'id': '2'})
        rows = [raw(i) for i in range(1, 7)]
        rows += [raw(1), raw(7, forfeit=True), raw(8, status='running'),
                 raw(9, begin_at=(now+pd.Timedelta(days=1)).isoformat()), raw(400)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(esports, 'CACHE', Path(tmp)), \
                patch.object(esports, 'enabled', return_value=True), patch.object(esports, '_get', return_value=rows) as api:
            for code in esports.GAMES:
                (Path(tmp)/f'{code}.json').write_text(json.dumps([esports._normalize(code, raw(50))]))
            history = esports.history(False, [event])
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.kwargs['filter[opponent_id]'], '1')
            dota = [m for m in history if m['div']=='DOTA']
            self.assertEqual({m['id'] for m in dota}, {'1','2','3','4','5','6','50'})
            self.assertEqual(len(dota), 7)
            esports.history(False, [event])
            self.assertEqual(api.call_count, 1)

    def test_failed_coverage_is_throttled(self):
        now=pd.Timestamp.now(tz='UTC')
        event=dict(div='DOTA',state='pre',kickoff=(now+pd.Timedelta(hours=1)).isoformat(),home={'id':'1'},away={'id':'2'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(esports,'CACHE',Path(tmp)), \
                patch.object(esports,'enabled',return_value=True), patch.object(esports,'_get',return_value=[]) as api:
            esports.history(False,[event])
            targeted=sum('filter[opponent_id]' in call.kwargs for call in api.call_args_list)
            esports.history(False,[event])
            self.assertEqual(targeted,2)
            self.assertEqual(sum('filter[opponent_id]' in call.kwargs for call in api.call_args_list),2)

    def test_retry_scheduler_preserves_published_and_kickoff_boundaries(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'run.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='other_review_due')
        ns={'pd':pd}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'run.py','exec'),ns)
        due=ns['other_review_due'];now=pd.Timestamp('2026-11-15T17:00:00Z');lead=pd.Timedelta(minutes=62)
        event=dict(sport='esports',state='pre',home={'ru':'Team'},kickoff=(now+pd.Timedelta(minutes=40)).isoformat())
        self.assertTrue(due(event,{'status':'skipped'},now,lead))
        self.assertFalse(due(event,{'status':'reviewed'},now,lead))
        self.assertFalse(due(event,{'status':'waiting_data','retry_at':now.timestamp()+1},now,lead))
        for minutes in (-1,4,90):
            self.assertFalse(due(dict(event,kickoff=(now+pd.Timedelta(minutes=minutes)).isoformat()),None,now,lead))
        self.assertTrue(due(dict(event,sport='tennis'),{'status':'skipped'},now,lead))
        self.assertFalse(due(dict(event,sport='hockey'),{'status':'skipped'},now,lead))
