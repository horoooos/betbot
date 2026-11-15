import copy
import unittest
from unittest.mock import patch

import pandas as pd

from betbot import sports, stavka, stavka_sports, vk_rss
from test_stavka import html, store, NOW, EVENT
from html import unescape


class AllSportSignalsTests(unittest.TestCase):
    def event(self,sport,div,**extra):
        return {**EVENT,'sport':sport,'div':div,'home':{'id':'1','ru':'Альфа','name':'Alpha'},'away':{'id':'2','ru':'Бета','name':'Beta'},
                'odds':{'H':1.7,'A':2.2,'line':5.5,'over':1.9,'under':1.9},**extra}

    def prepared(self,event):
        s=store()
        category=stavka_sports.group(event)
        s['sport_models']={category:dict(status='active',weight=.3,trained_at=(NOW-pd.Timedelta(hours=1)).isoformat())}
        for i in range(3):
            s['tips'][str(i)]=dict(author=str(i),key=stavka_sports.winner_keys(event)[0],sport=event['sport'],
                div=event['div'],event_id=event['id'],kickoff=event['kickoff'],observed_at=NOW.isoformat(),
                published_at=NOW.isoformat(),source='https://stavka.tv/predictions',odds=1.7)
        return s

    def test_parsing_and_scoping_for_every_source_sport(self):
        for slug,sport in stavka.SOURCE_SPORTS.items():
            markup=html(home='Альфа',away='Бета').replace('/matches/soccer/','/matches/'+slug+'/')
            rows=stavka.parse_predictions(markup,NOW)
            self.assertEqual(rows[0]['sport'],sport)
            if sport!='football':
                self.assertTrue(rows[0]['key'].startswith(('HK_','BB_','TN_','ES_')))
            wrong={**EVENT,'sport':'basketball' if sport!='basketball' else 'football'}
            self.assertIsNone(stavka.match_event(rows[0],[wrong]))

    def test_hockey_overtime_is_never_confused_with_regulation(self):
        self.assertEqual(stavka.market_key('ПОБЕДА 1.','hockey'),'HK_H')
        self.assertEqual(stavka.market_key('ПОБЕДА 1 (С УЧЕТОМ ОТ И БУЛЛИТОВ).','hockey'),'HK_ML_H')
        self.assertIsNone(stavka.market_key('ПОБЕДА 1 НА ПЕРВОЙ КАРТЕ.','esports'))
        self.assertIsNone(stavka.market_key('ПОБЕДА 1 В ПЕРВОМ СЕТЕ.','tennis'))

    def test_nhl_full_names_match_trusted_short_names(self):
        e=self.event('hockey','NHL',home={'ru':'Бостон','name':'Boston Bruins'},away={'ru':'Тампа-Бэй','name':'Tampa Bay Lightning'})
        row=dict(sport='hockey',day='2026-11-15',home='Бостон Брюинз',away='Тампа-Бэй Лайтнинг')
        self.assertEqual(stavka.match_event(row,[e])['id'],e['id'])
        self.assertIsNone(stavka.match_event({**row,'sport':'basketball'},[e]))

    def test_all_sports_can_apply_signal_without_inventing_bookmaker_odds(self):
        for sport,div,extra in [('hockey','NHL',{}),('basketball','NBA',{'odds':{'H':1.7,'A':2.2,'spread':-3.5,'sp_h':1.9,'sp_a':1.9,'line':220.5,'over':1.9,'under':1.9}}),
                                ('tennis','ATP',{}),('esports','CS2',{'bo':3}),('esports','DOTA',{'bo':3})]:
            e=self.event(sport,div,**extra);a=sports.analyse(e,{})
            s=self.prepared(e)
            with patch.object(stavka,'save'):
                new,info=stavka_sports.adjust(e,a,NOW,s)
            keys=stavka_sports.winner_keys(e)
            self.assertGreater(new['probs'][keys[0]],a['probs'][keys[0]])
            self.assertEqual(new['real'],a['real'])
            self.assertEqual(new['labels'],a['labels'])
            self.assertEqual(info['weight'],.3)
            self.assertAlmostEqual(sum(new['probs'][k] for k in keys),1)
            self.assertEqual(len(s['samples']),1)
            if sport=='basketball':
                self.assertAlmostEqual(new['probs']['BB_SPR_H']+new['probs']['BB_SPR_A'],1)
                self.assertGreater(new['probs']['BB_SPR_H'],a['probs']['BB_SPR_H'])

    def test_bo2_preserves_draw_and_total_probability(self):
        e=self.event('esports','DOTA',bo=2)
        a=dict(probs={'ES_W1':.3,'ES_X':.4,'ES_W2':.3},bar=(.3,.4,.3),real={},labels={})
        with patch.object(stavka,'save'):
            new,_=stavka_sports.adjust(e,a,NOW,self.prepared(e))
        self.assertAlmostEqual(sum(new['bar']),1)
        self.assertGreater(new['probs']['ES_W1'],.3)

    def test_cancelled_tennis_does_not_enter_training_as_a_loss(self):
        e=self.event('tennis','ATP',completed=True,status='STATUS_RETIRED',kickoff=(NOW-pd.Timedelta(hours=2)).isoformat())
        s=store();s['samples']['x']=dict(sport='tennis',group='tennis',event_id=e['id'],div='ATP',kickoff=e['kickoff'])
        self.assertEqual(stavka_sports.settle(s,[e],NOW),1)
        self.assertTrue(s['samples']['x']['void'])
        self.assertEqual(stavka_sports.train(s,NOW)['tennis']['settled_matches'],0)

    def test_training_is_separate_for_every_sport_and_discipline(self):
        s=store()
        for i in range(120):
            t=pd.Timestamp('2026-01-01T12:00:00Z')+pd.Timedelta(days=i)
            s['samples'][str(i)]=dict(sport='basketball',group='basketball',kickoff=t.isoformat(),
                settled_at=(t+pd.Timedelta(hours=3)).isoformat(),baseline=[.5,.5],consensus=[.8,.2],outcome=0)
        models=stavka_sports.train(s,NOW)
        self.assertEqual(models['basketball']['status'],'active')
        self.assertGreater(models['basketball']['weight'],0)
        for category in ('hockey','tennis','esports:CS2','esports:DOTA'):
            self.assertEqual(models[category]['weight'],0)
            self.assertEqual(models[category]['settled_matches'],0)
        for i in range(96,120):s['samples'][str(i)]['outcome']=1
        self.assertEqual(stavka_sports.train(s,NOW)['basketball']['weight'],0)

    def test_ascii_article_survives_wrong_decoder_and_keeps_footer(self):
        n=dict(title='⚽ Газизов подготовит предложение по расширению РПЛ',photo='https://example.test/photo.jpg',
               rss_link='https://vk.cc/test',body='Первый абзац.\n\nПоследний абзац.\n\n#футбол #РПЛ\n\nПодробнее на сайте 👉 vk.cc/test',sport='football')
        page=vk_rss.article_page(n)
        self.assertTrue(page.isascii())
        for encoding in ('utf-8','windows-1251','latin-1'):
            text=unescape(page.encode('ascii').decode(encoding))
            self.assertIn('<title>Газизов подготовит предложение по расширению РПЛ</title>',text)
            self.assertIn('Подробнее на сайте',text)
            self.assertIn('#РПЛ',text)
            self.assertIn('<p>Последний абзац.</p>',text)
        announcement=vk_rss.wall_description(n)
        self.assertLess(announcement.index('#футбол'),100)
        self.assertLess(announcement.index('Подробнее на сайте'),20)
