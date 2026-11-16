import unittest
import pandas as pd
from betbot.forecast_feed import collect


class ForecastFeedTests(unittest.TestCase):
    def match(self, id='2', sport='tennis', div='ATP'):
        return dict(id=id, sport=sport, div=div, msg_id=123,
            kickoff='2026-11-16T22:30:00+03:00', home={'ru':'Первый'},away={'ru':'Второй'},
            main={'label':'П1', 'odds':1.6})

    def test_pending_published_forecasts_included_and_unpublished_excluded(self):
        m=self.match();hidden=self.match('3');hidden.pop('msg_id')
        rows=collect(pd.DataFrame(), {'a':m,'b':hidden})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'pending')
        self.assertIn('live.html?',rows[0]['watch'])

    def test_settled_match_merged_without_duplicate_and_no_sixty_row_cap(self):
        results=pd.DataFrame([dict(id=str(i),sport='tennis',div='ATP',date='2026-11-16',home='Первый',away='Второй',
            main_label='П1',main_odds=1.6,main_hit=i%2==0,score='2:0') for i in range(100)])
        rows=collect(results,{'a':self.match()},[dict(id='2',sport='tennis',div='ATP',state='in')])
        self.assertEqual(len(rows),100)
        match=next(r for r in rows if r['id']=='2')
        self.assertEqual(match['status'],'won')
        self.assertEqual(match['date'],'2026-11-16')
        self.assertTrue(match['telegram'])

    def test_live_status_and_same_id_in_different_sports_remain_separate(self):
        a=self.match();b=self.match(sport='esports',div='DOTA')
        rows=collect(pd.DataFrame(),{'a':a,'b':b},[dict(id='2',sport='esports',div='DOTA',state='in')])
        self.assertEqual(len(rows),2)
        live=next(r for r in rows if r['sport']=='esports')
        self.assertEqual(live['status'],'in')
        self.assertIn('dota.html?',live['watch'])
