import unittest
from betbot import pro,content
import pandas as pd

class StakeGateTests(unittest.TestCase):
    def test_market_margin_and_estimated_prices_are_not_stakes(self):
        self.assertEqual(pro.stake({'p':.5,'odds':1.90,'est':False}),0)
        self.assertEqual(pro.stake({'p':.7,'odds':2.0,'est':True}),0)
        self.assertEqual(pro.stake({'p':.5,'odds':2.02,'est':False}),0)
        self.assertEqual(pro.stake({'p':float('nan'),'odds':2.0}),0)
    def test_genuine_edge_gets_bounded_fractional_kelly(self):
        self.assertGreater(pro.stake({'p':.6,'odds':1.9,'est':False}),0)
        self.assertLessEqual(pro.stake({'p':.9,'odds':3.,'est':False}),3)
    def test_express_does_not_repackage_bookmaker_margin_as_edge(self):
        now=pd.Timestamp('2026-11-22T10:00:00Z')
        event={'state':'pre','kickoff':now+pd.Timedelta(hours=1),'odds':{'H':1.5,'D':4.,'A':6.},'home':{'ru':'А'},'away':{'ru':'Б'},'id':'1','div':'E0'}
        self.assertEqual(content._favourites([event],[],now,6),[])
        self.assertEqual(content._risky_legs([event],[],now),[])
