import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from betbot import stavka,stavka_markets,sports
from test_stavka import html,store,NOW

EVENT=dict(id='77',div='ATP',sport='tennis',state='pre',kickoff=(NOW+pd.Timedelta(hours=1)).isoformat(),
           home={'id':'1','name':'Daniil Medvedev','ru':'Даниил Медведев'},
           away={'id':'2','name':'Flavio Cobolli','ru':'Флавио Коболли'})
SOURCE='https://stavka.tv/matches/tennis/15-11-2026-medvedev-daniil-cobolli-flavio'
QUOTES='''<div class="MatchHeaderRates"><button><span class="outcome">П1</span><span class="rate">1.70</span><img alt="winline"></button>
<button><span class="outcome">П2</span><span class="rate">2.20</span><img alt="winline"></button></div>'''


class StavkaMarketsTests(unittest.TestCase):
    def test_collector_upgrade_runs_once_immediately_and_keeps_failure_backoff(self):
        s=store();s['last_attempt']=NOW.isoformat();s['model']['trained_at']=NOW.isoformat();s['sport_models']={'tennis':{}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(stavka,'PATH',Path(tmp)/'store.json'),patch.object(stavka,'_runtime',None),patch.object(stavka,'collect',side_effect=ValueError('source unavailable')) as collect:
            stavka.save(s)
            stavka.tick([],NOW)
            stavka.tick([],NOW+pd.Timedelta(minutes=2))
            self.assertEqual(collect.call_count,1)
            stavka.tick([],NOW+pd.Timedelta(minutes=21))
            self.assertEqual(collect.call_count,2)

    def test_collector_saves_all_outcomes_and_public_pair_separately(self):
        markup=html(outcome='ТОТАЛ БОЛЬШЕ (21.5).',home='Даниил Медведев',away='Флавио Коболли').replace('/matches/soccer/15-11-2026-spain-england',SOURCE)
        def fetch(url,session):
            if url==stavka.BASE+'/predictions/tennis':return markup
            if url==SOURCE:return QUOTES+markup
            return '<html></html>'
        s=store()
        with patch.object(stavka,'fetch',side_effect=fetch):
            stavka.collect(s,[EVENT],NOW)
        self.assertEqual(len(s['tips']),1)
        row=next(iter(s['tips'].values()))
        self.assertEqual(row['key'],'TN_GO21.5')
        self.assertIsNone(row['model_key'])
        self.assertEqual(row['price_kind'],'author_recorded')
        self.assertEqual(s['quotes']['ATP|77']['odds'],{'H':1.7,'A':2.2})
        e=stavka_markets.supplement(EVENT,NOW,s)
        self.assertEqual(e['odds']['H'],1.7)

    def test_tennis_units_and_first_set_are_never_mixed(self):
        for label,key in [('ТОТАЛ БОЛЬШЕ (21.5).','TN_GO21.5'),('ТОТАЛ ПО СЕТАМ БОЛЬШЕ (2.5).','TN_SO2.5'),
                          ('ФОРА 1 (-3,5).','TN_GH1_-3.5'),('ФОРА 1 ПО СЕТАМ (-1.5).','TN_SH1_-1.5'),
                          ('ИНДИВИДУАЛЬНЫЙ ТОТАЛ 2 МЕНЬШЕ (12.5).','TN_IG2U12.5'),('ТОЧНЫЙ СЧЕТ 2:1.','TN_S2:1')]:
            self.assertEqual(stavka.market_key(label,'tennis'),key)
        for label in ('ТОТАЛ ПЕРВОГО СЕТА БОЛЬШЕ (9.5).','ПОБЕДА 1 В ПЕРВОМ СЕТЕ.','ТОТАЛ БОЛЬШЕ (21.25).'):
            self.assertIsNone(stavka.market_key(label,'tennis'))
        self.assertEqual(stavka_markets.modeled_key('TN_SH1_-1.5',EVENT),'TN_S2:0')
        self.assertIsNone(stavka_markets.modeled_key('TN_SH1_-1.5',dict(EVENT,bo5=True)))
        self.assertIsNone(stavka_markets.modeled_key('TN_GO21.5',EVENT))
        self.assertIsNone(stavka_markets.modeled_key('TN_S2:0',dict(EVENT,bo5=True)))

    def test_unknown_labels_are_archived_without_a_fake_model_key_or_live_price(self):
        markup=html(outcome='ЭЙСЫ БОЛЬШЕ (10.5).',home='Даниил Медведев',away='Флавио Коболли').replace('/matches/soccer/15-11-2026-spain-england',SOURCE)
        self.assertEqual(stavka.parse_predictions(markup,NOW),[])
        rows=stavka.parse_predictions(markup,NOW,include_unknown=True)
        s=store();stavka.ingest(s,rows,[EVENT],NOW)
        self.assertEqual(s['tips'],{})
        row=next(iter(s['market_observations'].values()))
        self.assertIsNone(row['key']);self.assertEqual(row['price_kind'],'author_recorded')
        self.assertEqual(row['market_label'],'ЭЙСЫ БОЛЬШЕ (10.5).')
        self.assertNotIn('quotes',s)
        stavka.ingest(s,[dict(rows[0],odds=3.1)],[EVENT],NOW)
        self.assertEqual(row['odds'],1.85)

    def test_match_page_without_event_anchor_uses_only_trusted_context(self):
        markup=html(outcome='ТОЧНЫЙ СЧЕТ 2:0.')
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(markup,'html.parser');soup.select_one('.PredictionsItemEvent').decompose()
        context=dict(source=SOURCE,home=EVENT['home']['ru'],away=EVENT['away']['ru'])
        self.assertFalse(stavka.parse_predictions(str(soup),NOW))
        rows=stavka.parse_predictions(str(soup),NOW,context=context)
        self.assertEqual(stavka.match_event(rows[0],[EVENT])['id'],'77')
        self.assertEqual(rows[0]['key'],'TN_S2:0')

    def test_swapped_first_last_names_preserve_player_sides_and_reject_ambiguity(self):
        self.assertEqual(stavka.event_for_url(SOURCE,[EVENT])['id'],'77')
        self.assertIsNone(stavka.event_for_url(SOURCE,[dict(EVENT,home=EVENT['away'],away=EVENT['home'])]))
        self.assertIsNone(stavka.event_for_url(SOURCE,[EVENT,dict(EVENT,id='duplicate')]))

    def test_only_same_book_match_header_pair_can_supply_fresh_odds(self):
        q=stavka_markets.parse_quotes(QUOTES,SOURCE,EVENT,NOW)
        self.assertEqual(q['odds'],{'H':1.7,'A':2.2})
        s=dict(quotes={'ATP|77':q});before=copy.deepcopy(EVENT)
        e=stavka_markets.supplement(EVENT,NOW,s)
        self.assertEqual(EVENT,before)
        a=sports.analyse(e,{})
        self.assertEqual(a['real']['TN_W1'],1.7)
        self.assertEqual(a['real']['TN_W2'],2.2)
        self.assertNotIn('СТАВКА ТВ',a['center'])
        self.assertIn('winline',a['center'])
        for at in (NOW-pd.Timedelta(seconds=1),NOW+pd.Timedelta(minutes=26)):
            self.assertIs(stavka_markets.supplement(EVENT,at,s),EVENT)
        existing=dict(EVENT,odds={'H':1.8,'A':2.0,'src':'Pinnacle'})
        self.assertIs(stavka_markets.supplement(existing,NOW,s),existing)
        for markup in (QUOTES.replace('alt="winline"','alt="other"',1),QUOTES.replace('2.20','-'),QUOTES.replace('1.70','NaN'),QUOTES.replace('2.20','99'),'<div>'+QUOTES+QUOTES+'</div>'):
            self.assertIsNone(stavka_markets.parse_quotes(markup,SOURCE,EVENT,NOW))
        self.assertIsNone(stavka_markets.parse_quotes(QUOTES,SOURCE,dict(EVENT,state='in'),NOW))
        self.assertIsNone(stavka_markets.parse_quotes(QUOTES,SOURCE,dict(EVENT,kickoff=(NOW+pd.Timedelta(minutes=4)).isoformat()),NOW))
