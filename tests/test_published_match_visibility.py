import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from betbot import site,sports,live


class PublishedMatchVisibilityTests(unittest.TestCase):
    def match(self,sport='tennis',div='ATP',mid='187506'):
        return dict(id=mid,sport=sport,div=div,state='pre',kickoff='2026-11-15T22:30:00+03:00',status='reviewed',msg_id=6223,
            home={'id':'1','name':'Home','ru':'Первый','score':None},away={'id':'2','name':'Away','ru':'Второй','score':None},
            main=dict(label='Победа первого',odds=1.55,p=.6),center='Линия СТАВКА ТВ / winline',bo=3)

    def test_published_tennis_and_esports_survive_missing_upstream_fixtures(self):
        a=self.match();b=self.match('esports','DOTA','1793335')
        with tempfile.TemporaryDirectory() as tmp,patch.object(site,'MATCHES',Path(tmp)/'matches.json'):
            site.matches_json([],{a['id']:a,'DOTA|1793335':b},pd.Timestamp('2026-11-15T19:00:00Z'))
            rows=json.loads(site.MATCHES.read_text(encoding='utf-8'))
        self.assertEqual({r['id'] for r in rows},{'187506','1793335'})
        tennis=next(r for r in rows if r['sport']=='tennis');es=next(r for r in rows if r['sport']=='esports')
        self.assertEqual(tennis['path'],'tennis/atp');self.assertTrue(tennis['url'].startswith('live.html?'))
        self.assertTrue(es['url'].startswith('esports.html?'));self.assertEqual(es['path'],'')
        self.assertIn('1793335',es['prediction'])
        self.assertNotIn('СТАВКА ТВ',tennis['bot']['center'])

    def test_fresh_series_score_overrides_frozen_prediction_and_missing_source_is_unknown(self):
        old=self.match('esports','DOTA','1793335');fresh=copy.deepcopy(old)
        fresh.update(state='in');fresh['home']['score']=1;fresh['away']['score']=0
        with tempfile.TemporaryDirectory() as tmp,patch.object(site,'MATCHES',Path(tmp)/'matches.json'):
            site.matches_json([fresh],{'DOTA|1793335':old},pd.Timestamp('2026-11-15T20:00:00Z'))
            row=json.loads(site.MATCHES.read_text(encoding='utf-8'))[0]
            self.assertEqual((row['state'],row['hs'],row['as']),('in',1,0))
            site.matches_json([] ,{'DOTA|1793335':old},pd.Timestamp('2026-11-15T20:00:00Z'))
            missing=json.loads(site.MATCHES.read_text(encoding='utf-8'))[0]
            self.assertEqual(missing['state'],'unknown')
            self.assertIsNone(missing['hs']);self.assertIsNone(missing['as'])

    def test_new_forecast_invalidates_site_without_waiting_for_telegram_scraper(self):
        old={};m=self.match();new={'ATP|187506':m}
        self.assertNotEqual(site.forecast_stamp(old),site.forecast_stamp(new))
        self.assertEqual(site.forecast_stamp(new),site.forecast_stamp(copy.deepcopy(new)))
        m['msg_id']=6225
        self.assertNotEqual(site.forecast_stamp({'ATP|187506':self.match()}),site.forecast_stamp(new))

    def test_source_labels_are_removed_from_new_and_legacy_display_values(self):
        for text in ('Линия СТАВКА ТВ / winline · Эло 1862 : 1786','Эло 1500 : 1600 · сигнал СТАВКА ТВ'):
            self.assertNotIn('СТАВКА ТВ',sports.public_model_label(text))
        e=self.match('esports','DOTA','1793335')
        button=live._tracker(e,'esports','Первый','Второй')
        self.assertIn('esports.html?',button[1])

