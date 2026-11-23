import unittest
from unittest.mock import patch
import pandas as pd
from betbot import markets,pro,editorial,news,stavka,stavka_markets as sm

NOW=pd.Timestamp('2026-11-23T17:00:00Z')
EVENT={'sport':'football','div':'E0','id':'1','state':'pre','kickoff':(NOW+pd.Timedelta(hours=1)).isoformat(),
       'home':{'name':'Brentford','ru':'Брентфорд'},'away':{'name':'Everton','ru':'Эвертон'}}
URL='https://stavka.tv/matches/soccer/23-11-2026-brentford-everton'
def header(prices):
    return '<div class="MatchHeaderRates">'+''.join('<button><span class="outcome">'+k+'</span><span class="rate">'+str(p)+'</span><img alt="winline"></button>' for k,p in prices.items())+'</div>'

class SofterEditorialTests(unittest.TestCase):
    def test_one_to_three_percent_edge_is_admitted_without_approving_negative_edge(self):
        self.assertGreater(pro.stake({'p':.5,'odds':2.04,'est':False}),0)
        self.assertEqual(pro.stake({'p':.5,'odds':1.9,'est':False}),0)
        self.assertEqual(pro.stake({'p':.8,'odds':2,'est':True}),0)
        self.assertNotIn('без явного перевеса',pro.stake_line({'stake':1.0}))
        chosen,_=markets.choose(['H','A'],{'H':.75,'A':.25},{'H':1.4,'A':3.},lambda k:{'H':.75,'A':.25}[k])
        self.assertEqual(chosen,'H')
    def test_football_gets_a_complete_same_book_three_way_header(self):
        q=sm.parse_quotes(header({'П1':2.33,'X':3.45,'П2':3.05}),URL,EVENT,NOW)
        self.assertEqual(q['odds'],{'H':2.33,'D':3.45,'A':3.05})
        self.assertIsNone(sm.parse_quotes(header({'П1':2.33,'П2':3.05}),URL,EVENT,NOW))
        self.assertIsNone(sm.parse_quotes(header({'П1':2.33,'X':3.45,'П2':3.05}),URL.replace('23-11','21-11'),EVENT,NOW))
    def test_regulation_draw_prices_are_not_sold_as_overtime_winner(self):
        for sport in ['basketball','hockey']:
            e={**EVENT,'sport':sport}
            self.assertIsNone(sm.parse_quotes(header({'П1':2.34,'X':14,'П2':1.76}),URL,e,NOW))
        self.assertIsNone(sm.parse_quotes(header({'П1':1.8,'П2':2.0}),URL,{**EVENT,'sport':'esports','bo':2},NOW))
    def test_on_demand_fills_missing_prices_and_preserves_a_complete_existing_line(self):
        store={'match_pages':{'E0|1':URL}}
        with patch.object(stavka,'fetch',return_value=header({'П1':2.33,'X':3.45,'П2':3.05})) as fetch,patch.object(stavka,'save'):
            filled=sm.ensure(EVENT,NOW,store)
            self.assertEqual(filled['odds']['D'],3.45)
            self.assertEqual(EVENT.get('odds'),None)
            sm.ensure(EVENT,NOW+pd.Timedelta(minutes=1),store)
            self.assertEqual(fetch.call_count,1)
            old={**EVENT,'odds':{'H':2.4,'D':3.5,'A':3.}}
            self.assertIs(sm.ensure(old,NOW,store),old)
    def test_failures_back_off_and_do_not_publish_author_prices_as_live_quotes(self):
        store={'match_pages':{'E0|1':URL}}
        with patch.object(stavka,'fetch',side_effect=TimeoutError) as fetch,patch.object(stavka,'save'):
            self.assertIs(sm.ensure(EVENT,NOW,store),EVENT)
            self.assertIs(sm.ensure(EVENT,NOW+pd.Timedelta(minutes=2),store),EVENT)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(store['quote_status']['E0|1']['status'],'unavailable')
    def test_humanize_keeps_facts_and_paragraphs_and_does_not_print_the_command(self):
        text='/humanize\nВот более человечный вариант:\nКоманда выиграла 2:1.\n\nМатч состоялся 23 ноября.\n\n\n#футбол'
        out=editorial.clean(text)
        self.assertEqual(out,'Команда выиграла 2:1.\n\nМатч состоялся 23 ноября.\n\n#футбол')
        self.assertNotIn('1200–2500',news.STRONG_STYLE+news.PROMPT)

    def test_rewrite_applies_editorial_and_keeps_validated_paragraphs(self):
        body='Команда выиграла матч со счётом 2:1. Встреча прошла в Москве. Тренер отметил хорошую игру защиты. Во втором тайме футболисты забили решающий гол и сохранили преимущество до финального свистка.'
        item={'title':'Команда победила в матче в Москве','desc':body,'body':body}
        answer={'sport':'football','title':'Победа в Москве: команда выиграла со счётом 2:1','text':body.replace(' Встреча','\n\nВстреча')}
        with patch.object(news,'_ask',return_value=(answer,True)) as ask:
            result=news._rewrite(item)
        self.assertIsNotNone(result)
        self.assertIn('2:1',result['text'])
        self.assertIn('\n\n',result['text'])
        self.assertIn(editorial.HUMANIZE_STYLE,ask.call_args[0][0][0]['content'])

    def test_verified_slug_aliases_find_the_same_fixture_without_fuzzy_matching(self):
        e={**EVENT,'home':{'name':'Brøndby IF','ru':'Брондбю'},'away':{'name':'FC Midtjylland','ru':'Мидтьюлланн'}}
        url='https://stavka.tv/matches/soccer/23-11-2026-broendby-midtjylland'
        self.assertIs(stavka.event_for_url(url,[e]),e)
        self.assertIsNone(stavka.event_for_url(url,[e,{**e,'id':'other'}]))
        self.assertIsNone(stavka.event_for_url(url.replace('broendby','broendby-reserves'),[e]))
