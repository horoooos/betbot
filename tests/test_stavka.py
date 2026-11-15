import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from betbot import markets as mk, stavka

NOW=pd.Timestamp('2026-11-15T12:00:00Z')
EVENT=dict(id='7',div='UNL',state='pre',kickoff='2026-11-15T19:45:00+03:00',
           home={'name':'Spain','ru':'Сборная Испании'},away={'name':'England','ru':'Сборная Англии'})


def store():
    return dict(version=1,tips={},samples={},model={'status':'collecting','weight':0.0})


def html(outcome='ПОБЕДА 1.',author='alice',home='Сборная Испании',away='Сборная Англии',date='Сегодня в 14:59 по МСК'):
    return f'''<div class="PredictionsItem PredictionsItem--soccer">
    <div class="PredictionsItemHeader"><a class="predictor-link" href="/predictors/{author}"></a><div class="date">{date}</div></div>
    <a class="PredictionsItemEvent" href="/matches/soccer/15-11-2026-spain-england#tips-1">
    <span class="team--home">{home}</span><span class="team--away">{away}</span></a>
    <span class="Rate">1.85</span><span class="outcome">{outcome}</span></div>'''


class StavkaTests(unittest.TestCase):
    def test_actual_markup_fields_and_no_prose_or_images_stored(self):
        row=stavka.parse_predictions(html(),NOW)[0]
        self.assertEqual(row['key'],'H')
        self.assertEqual(row['published_at'],'2026-11-15T11:59:00+00:00')
        self.assertEqual(row['odds'],1.85)
        self.assertNotIn('body',row)
        self.assertEqual(row['source'],'https://stavka.tv/matches/soccer/15-11-2026-spain-england')

    def test_unsupported_markets_never_misread_as_full_time(self):
        for label in ('ТОТАЛ ПЕРВОГО ТАЙМА БОЛЬШЕ (2.5).','ПОБЕДА 1 (С ОТ).','ТОТАЛ БОЛЬШЕ (3).','ТОТАЛ БОЛЬШЕ (2.25).'):
            self.assertIsNone(stavka.market_key(label))
        self.assertEqual(stavka.market_key('ТОТАЛ БОЛЬШЕ (2,5).'),'O25')
        self.assertEqual(stavka.market_key('ОБЕ ЗАБЬЮТ (НЕТ).'),'BTTS_N')

    def test_unknown_and_future_dates_excluded(self):
        self.assertFalse(stavka.parse_predictions(html(date='только что'),NOW))
        self.assertFalse(stavka.parse_predictions(html(date='Сегодня в 18:00 по МСК'),NOW))
        self.assertEqual(stavka.published_time('Вчера в 10:00 по МСК',NOW).day,14)

    def test_matching_is_unambiguous_and_preserves_sides(self):
        row=stavka.parse_predictions(html(),NOW)[0]
        self.assertEqual(stavka.match_event(row,[EVENT])['id'],'7')
        self.assertEqual(stavka.match_event({**row,'home':'Испания','away':'Англия'},[EVENT])['id'],'7')
        self.assertIsNone(stavka.match_event(row,[EVENT,{**EVENT,'id':'8'}]))
        self.assertIsNone(stavka.match_event({**row,'home':row['away'],'away':row['home']},[EVENT]))
        self.assertIsNone(stavka.match_event({**row,'home':'Испания U21'},[EVENT]))

    def test_only_public_html_urls(self):
        for url in ('https://evil.test/predictions','/api/predictions','/predictions?page=2','/profile'):
            with self.assertRaises(ValueError):stavka.public_url(url)

    def test_capture_dedup_and_original_odds_frozen(self):
        s=store();rows=stavka.parse_predictions(html(),NOW)
        self.assertEqual(stavka.ingest(s,rows,[EVENT],NOW),1)
        self.assertEqual(stavka.ingest(s,[{**rows[0],'odds':9}],[EVENT],NOW),0)
        self.assertEqual(next(iter(s['tips'].values()))['odds'],1.85)
        self.assertEqual(stavka.ingest(store(),rows,[{**EVENT,'state':'in'}],NOW),0)
        self.assertEqual(stavka.ingest(store(),rows,[EVENT],pd.Timestamp(EVENT['kickoff'])),0)

    def test_each_author_has_one_vote_per_family_and_minimum_three(self):
        s=store()
        for author in ('a','b','c'):
            stavka.ingest(s,stavka.parse_predictions(html(author=author),NOW),[EVENT],NOW)
        stavka.ingest(s,stavka.parse_predictions(html(author='a',outcome='ПОБЕДА 2.'),NOW),[EVENT],NOW)
        votes,opinions=stavka.votes_for(s,EVENT,NOW)
        self.assertEqual(sum(votes.values()),3)
        self.assertEqual(len(opinions),3)
        self.assertFalse(stavka.votes_for(s,EVENT,NOW-pd.Timedelta(minutes=1))[0])
        # Moving kickoff invalidates earlier alignment rather than training on a postponed game.
        self.assertFalse(stavka.votes_for(s,{**EVENT,'kickoff':'2026-11-16T19:45:00+03:00'},NOW)[0])

    def test_matrix_stays_normalized_and_compatible(self):
        base=mk.matrix(1.4,1.1)
        self.assertTrue(np.allclose(stavka.adjusted_matrix((1.4,1.1),{'H':9},0),base))
        m=stavka.adjusted_matrix((1.4,1.1),{'H':9,'A':1,'O25':5},.3)
        self.assertAlmostEqual(float(m.sum()),1)
        self.assertGreaterEqual(m.min(),0)
        p={k:mk._p(m,c) for k,(_,_,c) in mk.MARKETS.items()}
        self.assertAlmostEqual(p['H']+p['D']+p['A'],1)
        self.assertAlmostEqual(p['O25']+p['U25'],1)
        self.assertAlmostEqual(p['1X'],p['H']+p['D'])
        with self.assertRaises(ValueError):stavka.adjusted_matrix((1,1),{},.9)

    def test_training_waits_for_real_settled_matches(self):
        s=store();self.assertEqual(stavka.train(s,NOW)['weight'],0)
        self.assertEqual(s['model']['status'],'collecting')

    def history(self,train_home=True,valid_home=True):
        s=store()
        for i in range(120):
            day=pd.Timestamp('2026-01-01T12:00:00Z')+pd.Timedelta(days=i)
            home=train_home if i<96 else valid_home
            s['samples'][str(i)]=dict(event_id=str(i),kickoff=day.isoformat(),settled_at=(day+pd.Timedelta(hours=3)).isoformat(),
                lam=[1.2,1.2],votes={'H':12,'A':1},score=[2,0] if home else [0,2],opinions=[])
        return s

    def test_useful_signal_can_learn_positive_weight(self):
        m=stavka.train(self.history(),NOW)
        self.assertEqual(m['status'],'active')
        self.assertGreater(m['weight'],0)
        self.assertLess(m['validation_logloss'],m['validation_baseline_logloss'])

    def test_later_holdout_rejects_signal_that_stopped_working(self):
        m=stavka.train(self.history(valid_home=False),NOW)
        self.assertGreater(m['candidate_weight'],0)
        self.assertEqual(m['weight'],0)
        self.assertEqual(m['status'],'baseline_better')

    def test_training_never_uses_unavailable_outcomes(self):
        s=self.history()
        for sample in s['samples'].values():sample['settled_at']='2027-01-01T00:00:00Z'
        self.assertEqual(stavka.train(s,NOW)['settled_matches'],0)

    def test_final_settlement_excludes_extra_time_and_nonfinal(self):
        s=store();s['samples']['7']=dict(event_id='7',div='UNL',opinions=[])
        e={**EVENT,'completed':True,'status':'STATUS_FULL_TIME','detail':'AET','home':{'score':'2'},'away':{'score':'1'}}
        self.assertEqual(stavka.settle(s,[e],NOW),0)
        self.assertEqual(stavka.settle(s,[{**e,'detail':'FT'}],NOW+pd.Timedelta(hours=12)),1)
        self.assertEqual(s['samples']['7']['score'],[2,1])
        self.assertEqual(stavka.settle(s,[e],NOW),0)

    def test_source_failure_does_not_break_tick(self):
        with tempfile.TemporaryDirectory() as d,patch.object(stavka,'PATH',Path(d)/'data.json'),patch.object(stavka,'collect',side_effect=ValueError('markup changed')):
            result=stavka.tick([EVENT],NOW)
            self.assertIn('markup changed',result['error'])
            self.assertEqual(result['model']['weight'],0)

    def test_forecast_snapshot_and_no_influence_before_validation(self):
        s=store()
        for author in ('a','b','c'):
            stavka.ingest(s,stavka.parse_predictions(html(author=author),NOW),[EVENT],NOW)
        probs=mk.all_markets(1.4,1.1)
        with patch.object(stavka,'_runtime',s),patch.object(stavka,'save'):
            updated,info=stavka.adjust(EVENT,(1.4,1.1),probs,NOW)
            self.assertEqual(updated,probs)
            self.assertEqual(info['weight'],0)
            snap=copy.deepcopy(s['samples'])
            stavka.adjust(EVENT,(2,1),probs,NOW)
            self.assertEqual(s['samples'],snap)

    def test_active_model_changes_forecast_and_future_model_cannot(self):
        s=store()
        for author in ('a','b','c'):
            stavka.ingest(s,stavka.parse_predictions(html(author=author),NOW),[EVENT],NOW)
        s['model']=dict(status='active',weight=.3,trained_at=(NOW-pd.Timedelta(hours=1)).isoformat())
        probs=mk.all_markets(1.4,1.1)
        with patch.object(stavka,'_runtime',s),patch.object(stavka,'save'):
            changed,info=stavka.adjust(EVENT,(1.4,1.1),probs,NOW)
            self.assertGreater(changed['H'],probs['H'])
            self.assertEqual(info['weight'],.3)
            self.assertAlmostEqual(changed['H']+changed['D']+changed['A'],1)
            s['model']['trained_at']=(NOW+pd.Timedelta(hours=1)).isoformat()
            unchanged,info=stavka.adjust(EVENT,(1.4,1.1),probs,NOW)
            self.assertEqual(unchanged,probs)


if __name__=='__main__':unittest.main()
