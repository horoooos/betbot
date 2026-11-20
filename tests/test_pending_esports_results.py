import os
import unittest
from unittest.mock import patch
import pandas as pd
from betbot import esports, sports


class PendingEsportsTests(unittest.TestCase):
    def test_missing_finished_match_fetched_by_id_with_retry_cooldown(self):
        now = pd.Timestamp('2026-11-20T12:00:00Z')
        m = dict(id='10', div='DOTA', sport='esports', status='reviewed', kickoff='2026-11-19T10:00:00Z')
        raw = dict(id=10, status='finished', begin_at=m['kickoff'], number_of_games=3,
                   opponents=[{'opponent': {'id':1,'name':'A'}},{'opponent':{'id':2,'name':'B'}}],
                   results=[{'team_id':1,'score':2},{'team_id':2,'score':1}], winner_id=1)
        with patch.dict(os.environ, {'PANDASCORE_TOKEN':'test'}), patch.object(esports, '_get', return_value=raw) as get:
            recovered = esports.pending_results({'DOTA|10': m}, [], now)
            self.assertEqual(len(recovered), 1)
            self.assertEqual(sports.final(recovered[0])['sets'], '2:1')
            self.assertEqual(esports.pending_results({'DOTA|10':m}, [], now+pd.Timedelta(minutes=2)), [])
            get.assert_called_once_with('/matches/10')

    def test_missing_scores_are_not_silently_settled_as_zero(self):
        for a,b in [(None,None),(None,2),(0,0)]:
            self.assertIsNone(sports.final({'sport':'esports','home':{'score':a},'away':{'score':b}}))

    def test_already_available_completed_match_does_not_request_again(self):
        event=dict(id='10',div='DOTA',completed=True)
        m=dict(id='10',div='DOTA',sport='esports',status='reviewed',kickoff='2026-11-19T10:00:00Z')
        with patch.dict(os.environ, {'PANDASCORE_TOKEN':'test'}), patch.object(esports,'_get') as get:
            self.assertEqual(esports.pending_results({'x':m},[event],pd.Timestamp('2026-11-20T12:00:00Z')),[])
            get.assert_not_called()
