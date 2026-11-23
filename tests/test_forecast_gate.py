import unittest
import pandas as pd
from betbot import forecast_gate as gate

class ReviewRetryTests(unittest.TestCase):
    def test_retry_missing_quotes_for_every_sport_without_reposting(self):
        now=pd.Timestamp('2026-11-23T12:00:00Z');lead=pd.Timedelta(minutes=80)
        for sport in ('football','hockey','basketball','tennis','esports'):
            event={'state':'pre','sport':sport,'kickoff':now+pd.Timedelta(minutes=30)}
            self.assertTrue(gate.due(event,{'status':'skipped'},now,lead))
            self.assertFalse(gate.due(event,{'status':'waiting_data','retry_at':now.timestamp()+600},now,lead))
            self.assertTrue(gate.due(event,{'status':'waiting_data','retry_at':now.timestamp()-1},now,lead))
            self.assertFalse(gate.due(event,{'status':'reviewed','msg_id':123},now,lead))
            self.assertFalse(gate.due(event,{'status':'waiting_data','msg_id':123},now,lead))
    def test_never_publish_after_start_or_outside_review_window(self):
        now=pd.Timestamp('2026-11-23T12:00:00Z');lead=pd.Timedelta(minutes=80)
        for minutes in (-1,0,4,90):
            self.assertFalse(gate.due({'state':'pre','kickoff':now+pd.Timedelta(minutes=minutes)},None,now,lead))
    def test_reasons_do_not_confuse_model_only_odds_with_no_edge(self):
        self.assertEqual(gate.reason({'est':True}),'no_real_odds')
        self.assertEqual(gate.reason({'p':.5,'odds':1.9}),'edge_below_minimum')
        state={};event={'id':'1','sport':'tennis','div':'ATP','kickoff':'2026-11-23T13:00:00Z'}
        gate.record(state,event,'no_real_odds',{'p':.5,'odds':1.86,'est':True})
        saved=gate.waiting(event,state,pd.Timestamp('2026-11-23T12:00:00Z'))
        self.assertEqual(saved['reason'],'no_real_odds')
