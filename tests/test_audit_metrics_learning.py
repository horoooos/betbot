import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from betbot import engine, pages, pro, site, sports
from tools.reconcile_spreads import reconcile
import run


class AuditRegressionTests(unittest.TestCase):
    def results(self):
        return pd.DataFrame([dict(date=day, main_odds=2, main_hit=hit, main_stake=1,
                                  bold_odds=np.nan, bold_hit=np.nan)
                             for day, hit in [('2026-11-11', True), ('2026-11-12', False), ('2026-11-14', True)]])

    def test_bank_filters_period_and_fills_inactive_days(self):
        with patch.object(pro, 'expresses', return_value=pd.DataFrame()), patch.object(pro, 'live_bets', return_value=pd.DataFrame()):
            bets = pro.all_bets(self.results(), start='2026-11-12', end='2026-11-12')
            self.assertEqual(bets, [(2, False, 1)])
            days = pro.bank_daily(self.results(), today=pd.Timestamp('2026-11-14'))
            self.assertEqual([p['date'] for p in days], ['2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14'])
            self.assertEqual(days[1]['bank'], 9900)
            self.assertEqual(days[2]['bank'], 9900)
            self.assertEqual(days[2]['n'], 0)
            self.assertEqual(days[-1]['bank'], 9999)
            self.assertEqual(pro.bank_daily(self.results(), today=pd.Timestamp('2026-11-13'))[-1]['bank'], 9900)

    def test_chart_interpolation_never_invents_a_peak(self):
        path = site._smooth([0, 1, 2], [0, 100, 101])
        segments = re.findall(r'C([\d.-]+),([\d.-]+) ([\d.-]+),([\d.-]+) ([\d.-]+),([\d.-]+)', path)
        previous = 0
        for segment in segments:
            _, a, _, b, _, end = map(float, segment)
            values = [(1-t)**3*previous + 3*(1-t)**2*t*a + 3*(1-t)*t*t*b + t**3*end for t in np.linspace(0,1,101)]
            self.assertGreaterEqual(min(values), min(previous,end)-0.1)
            self.assertLessEqual(max(values), max(previous,end)+0.1)
            previous = end

    def test_article_metadata_bypasses_short_redirect_but_text_keeps_short_link(self):
        news = dict(id=1, title='🎮 Team Spirit разгромили в финале', body='Первый абзац.\n\nПоследний абзац.',
                    sport='esports', t='2026-11-15T10:00:00Z', url='news/1.html', desc='Описание', photo='https://example.test/a.jpg')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'vk_rss_since.txt').write_text('2026-11-14T09:00:00Z')
            (root/'vk_rss_format_since.txt').write_text('2026-11-14T09:00:00Z')
            image=root/'docs/rss-images/1.jpg';image.parent.mkdir(parents=True);image.write_bytes(b'jpeg')
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',root/'docs'),patch('betbot.vk._short',return_value='vk.cc/test'):
                item=ET.fromstring(pages._vk_rss([news],pd.Timestamp('2026-11-15T11:00:00Z'),article=True)).find('channel/item')
        self.assertEqual(item.findtext('link'),pages.SITE+'news/1.html')
        self.assertEqual(item.findtext('title'),'Team Spirit разгромили в финале')
        self.assertIn('vk.cc/test',item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'))

    def test_final_model_never_sees_future_results(self):
        history=pd.DataFrame({'Div':['E0']*3,'Date':pd.to_datetime(['2025-01-01','2026-01-01','2027-01-01'])})
        with patch.object(engine,'PoissonModel') as model:
            engine.fit_full(history,'E0',pd.Timestamp('2026-01-01'))
        fitted=model.return_value.fit.call_args.args[0]
        self.assertEqual(fitted['Date'].tolist(),[pd.Timestamp('2025-01-01')])

    def test_training_failure_keeps_weights_and_does_not_mark_success(self):
        state={'learned':'2026-11-14','weights':{'1X2':0.3,'OU25':0.3}}
        now=pd.Timestamp('2026-11-15T12:00:00+03:00')
        with patch.object(run,'load_history',side_effect=RuntimeError('data unavailable')):
            self.assertFalse(run.learn(state,now))
        self.assertEqual(state['learned'],'2026-11-14')
        self.assertEqual(state['weights']['1X2'],0.3)
        self.assertEqual(state['learn_error'],'data unavailable')
        self.assertEqual(state['learn_retry_at'],now.timestamp()+3600)

    def test_shared_weight_uses_temporal_holdout_and_rejects_a_worse_model(self):
        count=300
        df=pd.DataFrame(dict(Date=pd.date_range('2025-01-01',periods=100).repeat(3),
                            k_H=[0.4]*count,k_D=[0.2]*count,k_A=[0.4]*count,k_O25=[0.5]*count,
                            m_xgH=[3.0]*count,m_xgA=[0.4]*count,
                            FTHG=[3]*240+[0]*60,FTAG=[0]*240+[3]*60))
        diagnostics={}
        with patch('betbot.markets.implied_lambdas',return_value=(1.2,1.2)) as market:
            weights=engine.fit_weights_lambda(df,diagnostics=diagnostics)
        self.assertEqual(weights,{'1X2':0.0,'OU25':0.0})
        self.assertGreater(diagnostics['candidate_weight'],0)
        self.assertEqual(diagnostics['train_rows'],240)
        self.assertEqual(diagnostics['validation_rows'],60)
        self.assertEqual(market.call_args.args[1:],(2.5,0.5))

    def test_handicap_settlement_uses_published_line_not_final_feed(self):
        self.assertTrue(sports.won('BB_SPR_H',{'hs':132,'as':120,'spread_h':None},{'label':'Ф1 (-6.5)'}))
        self.assertTrue(sports.won('BB_SPR_A',{'hs':114,'as':121,'spread_h':-30},{'label':'Ф2 (+5.5)'}))
        self.assertFalse(sports.won('BB_SPR_A',{'hs':127,'as':101},{'label':'Ф2 (+6.5)'}))

    def test_historical_correction_is_narrow_and_idempotent(self):
        frame=pd.DataFrame([dict(id='1',div='NBA',date='2026-10-29',score='132:120',main_key='BB_SPR_H',
                                 main_label='Ф1 (-6.5)',main_hit=False,main_odds=1.9)])
        corrected,changes=reconcile(frame)
        self.assertEqual(len(changes),1)
        self.assertTrue(corrected.at[0,'main_hit'])
        self.assertEqual(corrected.at[0,'main_odds'],1.9)
        self.assertFalse(reconcile(corrected)[1])

    def test_push_lines_are_not_recommended_until_refunds_are_supported(self):
        analysis=dict(probs={'BB_SPR_H':.6,'BB_O220.0':.7,'BB_ML_H':.6},
                      labels={'BB_SPR_H':'Ф1 (-6.0)','BB_O220.0':'ТБ 220','BB_ML_H':'П1'},real={})
        with patch('betbot.markets.choose',return_value=('BB_ML_H',None)) as choose:
            sports.pick(analysis,{})
        self.assertEqual(choose.call_args.args[0],['BB_ML_H'])

    def test_repeated_result_does_not_duplicate_because_of_id_type(self):
        match=dict(id='123',div='E0',kickoff='2026-11-15T12:00:00+03:00',home={'ru':'А'},away={'ru':'Б'},
                   main=dict(key='H',label='П1',p=.6,odds=1.8,est=False),main_hit=True)
        with tempfile.TemporaryDirectory() as directory, patch.object(run,'RESULTS',Path(directory)/'results.csv'):
            run.add_result(match,'1:0','football')
            run.add_result(match,'1:0','football')
            self.assertEqual(len(run.read_results()),1)


if __name__=='__main__':
    unittest.main()
