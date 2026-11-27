import unittest
from betbot import pro,content,markets
from unittest.mock import patch
import run as runner
import pandas as pd

class StakeGateTests(unittest.TestCase):
    def test_market_margin_and_estimated_prices_are_not_stakes(self):
        self.assertEqual(pro.stake({'p':.5,'odds':1.90,'est':False}),0)
        self.assertEqual(pro.stake({'p':.7,'odds':2.0,'est':True}),0)
        self.assertEqual(pro.stake({'p':.5,'odds':2.01,'est':False}),0)
        self.assertGreater(pro.stake({'p':.5,'odds':2.04,'est':False}),0)
        self.assertEqual(pro.stake({'p':float('nan'),'odds':2.0}),0)
    def test_invalid_quote_fails_closed(self):
        self.assertEqual(pro.stake({'p':None,'odds':'bad'}),0)

    def test_a_qualified_real_market_is_not_displaced_by_negative_edge(self):
        main,bold=markets.choose(['H','A'],{'H':.55,'A':.5},{'H':1.5,'A':2.1},lambda k: .9 if k=='H' else .5)
        self.assertEqual(main,'A')

    def test_negative_edge_review_does_not_send_a_forecast(self):
        tip={'key':'H','p':.5,'odds':1.9,'est':False}
        probs={'H':.5,'A':.3,'D':.2,'scores':{}}
        with patch.object(runner,'find_fixture',return_value=None),patch.object(runner,'market',return_value={}),patch.object(runner,'lambdas',return_value=(1,1)),patch.object(runner.mk,'all_markets',return_value=probs),patch.object(runner.stavka,'adjust',return_value=(probs,{})),patch.object(runner.mk,'tips',return_value=(tip,{})),patch.object(runner.telegram,'send_photo') as send:
            self.assertIsNone(runner.review({}, {}, lambda:None,lambda:None,{},{}))
            send.assert_not_called()

    def test_genuine_edge_gets_bounded_fractional_kelly(self):
        self.assertGreater(pro.stake({'p':.6,'odds':1.9,'est':False}),0)
        self.assertLessEqual(pro.stake({'p':.9,'odds':3.,'est':False}),3)
    def test_express_does_not_repackage_bookmaker_margin_as_edge(self):
        now=pd.Timestamp('2026-11-22T10:00:00Z')
        event={'state':'pre','kickoff':now+pd.Timedelta(hours=1),'odds':{'H':1.5,'D':4.,'A':6.},'home':{'ru':'А'},'away':{'ru':'Б'},'id':'1','div':'E0'}
        leg=content._favourites([event],[],now,6)[0]
        self.assertEqual(leg['probability_origin'],'market_baseline')
        self.assertLess(leg['p']*leg['odds'],1)
        self.assertEqual(pro.stake(leg),0)
        self.assertIn('перевес не подтверждён',content._express_text([leg],leg['odds'],leg['p']))
        self.assertEqual(content._risky_legs([event],[],now),[])
