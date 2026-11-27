import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from betbot import content,pro

class ExpressRegressionTests(unittest.TestCase):
    def setUp(self):self.now=pd.Timestamp('2026-11-27T10:00:00+03:00')
    def event(self,i=1,odds=None,sport='football'):
        return dict(id=str(i),div='E0',sport=sport,state='pre',kickoff=(self.now+pd.Timedelta(hours=2)).isoformat(),
                    home={'ru':'Хозяева'},away={'ru':'Гости'},odds=odds or {'H':1.5,'D':4,'A':6})
    def test_fair_market_legs_are_selectable_without_claiming_value(self):
        legs=content._favourites([self.event()],[],self.now,14,ratio=1.25)
        self.assertEqual(len(legs),1);self.assertLess(legs[0]['p']*legs[0]['odds'],1)
        self.assertAlmostEqual(legs[0]['p'],(1/1.5)/(1/1.5+1/4+1/6))
    def test_tennis_and_invalid_prices(self):
        e=self.event(odds={'H':1.5,'A':3},sport='tennis')
        self.assertTrue(content._favourites([], [e],self.now,14))
        for odds in ({'H':float('nan'),'A':2},{'H':1.5,'A':3,'est':True},
                     {'H':1.5,'A':3,'observed_at':(self.now-pd.Timedelta(hours=1)).isoformat()}):
            self.assertEqual(content._favourites([self.event(odds=odds)],[],self.now,14),[])
    def test_retry_after_empty_candidates_and_after_publication_failure(self):
        state={}
        with patch.object(content,'express',side_effect=[False,True]) as post:
            content.run(state,[],[],pd.DataFrame(),self.now,'brand')
            self.assertNotIn('content_slot',state)
            content.run(state,[],[],pd.DataFrame(),self.now+pd.Timedelta(minutes=2),'brand')
            self.assertEqual(post.call_count,1)
            content.run(state,[],[],pd.DataFrame(),self.now+pd.Timedelta(minutes=6),'brand')
            self.assertEqual(state['content_slot'],'2026-11-27-10')
        state={}
        with patch.object(content,'express',side_effect=RuntimeError('network')):
            content.run(state,[],[],pd.DataFrame(),self.now,'brand')
        self.assertNotIn('content_slot',state)
        self.assertEqual(state['content_retry']['reason'],'publication_error')
    def test_identity_includes_league_and_no_second_post_today(self):
        events=[self.event(),{**self.event(),'div':'D1'}];state={}
        with patch.object(content.card,'express_card',return_value=b'png'),patch.object(content,'_post',return_value=99) as post:
            self.assertTrue(content.express(state,events,[],self.now,'brand'))
            self.assertEqual(len(state['express']['legs']),2)
            self.assertEqual(state['express']['stake_pct'],.5)
            self.assertTrue(content.express(state,events,[],self.now,'brand'))
            self.assertEqual(post.call_count,1)
    def test_new_stakes_do_not_rewrite_historical_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'express.csv';log.write_text('date,name,legs,odds,hit\n2026-11-20,old,2,3.00,True\n',encoding='utf-8')
            ex={'legs':[{'kickoff':self.now.isoformat()}],'odds':4,'stake_pct':.5}
            with patch.object(content,'EXPRESS_LOG',log),patch.object(pro,'EXPRESS_LOG',log),patch.object(pro,'live_bets',return_value=pd.DataFrame()):
                content._log_express('new',ex,False)
                rows=pro.all_bets(pd.DataFrame(),start='2026-11-20',end='2026-11-27')
            self.assertEqual([r[2] for r in rows],[1,.5])
