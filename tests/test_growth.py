import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from betbot import growth,growth_campaigns as campaigns

NOW=pd.Timestamp('2026-11-22T18:00:00Z')
def news(i,sport='football',**kw):
    return dict(id=i,title='Новость '+str(i),sport=sport,t=NOW-pd.Timedelta(hours=i),body='Первый факт.\n\nВторой факт.',url=f'news/{i}.html',complete=True,**kw)

class GrowthTests(unittest.TestCase):
    def test_digest_is_fresh_complete_diverse_and_has_no_repeats(self):
        rows=[news(1),news(2),news(3,'tennis'),news(25),{**news(4),'complete':False},{**news(5),'title':'Новость 1'}]
        self.assertEqual([n['id'] for n in growth.select_digest(rows,NOW)],[1,3,2])
        item=growth.digest_item(rows,NOW)
        self.assertIn('Первый факт.',item['body']);self.assertIn('news/3.html',item['body'])
        self.assertIsNone(growth.digest_item(rows,NOW+pd.Timedelta(days=3)))

    def test_catalog_includes_matches_without_predictions(self):
        from betbot import pages,pages_extra
        match={'id':'x','home':'Новая команда','away':'Соперник','sport':'esports','league':'Тестовый турнир','kickoff':NOW.isoformat(),'url':'matches.html'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(pages,'DOCS',Path(tmp)),patch.object(pages_extra,'DOCS',Path(tmp)):
            Path(tmp,'matches.json').write_text(json.dumps([match]),encoding='utf-8')
            pages_extra.build_teams([],[],NOW)
            self.assertTrue(Path(tmp,pages_extra.team_url('esports','Новая команда')).exists())
            urls=growth.build([],[],NOW)
            self.assertTrue(any(u.startswith('tournaments/league-') for u in urls))
            catalog=json.loads(Path(tmp,'topics.json').read_text(encoding='utf-8'))['topics']
            self.assertTrue(any(t['kind']=='team' and t['name']=='Новая команда' for t in catalog))

    def test_topics_separate_sports_and_match_exact_team(self):
        sub={'topics':{growth.topic_key('team','football','Спартак'):True}}
        self.assertTrue(campaigns.matches_interest(sub,'football','Спартак','Динамо'))
        self.assertFalse(campaigns.matches_interest(sub,'hockey','Спартак','Динамо'))
        self.assertFalse(campaigns.matches_interest(sub,'football','Спартак-2','Динамо'))

    def test_notification_not_replayed_and_token_not_persisted(self):
        from betbot import push
        state={};subscriber={'t':'private-device-token','interests':{'topics':{growth.topic_key('team','football','Спартак'):True},'events':{'start':True,'result':True}}}
        e={'id':'1','state':'pre','sport':'football','home':{'ru':'Спартак','score':'0'},'away':{'ru':'Динамо','score':'0'}}
        with patch.object(push,'enabled',return_value=True),patch.object(push,'_token',return_value='server-token'),patch.object(push,'_subscribers',return_value={'secret-key':subscriber}),patch.object(push,'_send',return_value=True) as send:
            campaigns.notify([e],[],state,NOW)
            self.assertFalse(send.called)
            campaigns.notify([{**e,'state':'in'}],[],state,NOW)
            campaigns.notify([{**e,'state':'in'}],[],state,NOW)
            self.assertEqual(send.call_count,1)
            self.assertNotIn('secret-key',json.dumps(state));self.assertNotIn('private-device-token',json.dumps(state))

    def test_report_separates_counts_from_telegram_subscriptions(self):
        data={'2026-11-21':{'x':{'r':'telegram','a':{'share':2}}},'2026-11-22':{'x':{'r':'telegram','a':{'follow':1}},'y':{'r':'Яндекс'}}}
        r=growth.summarize_visits(data)
        self.assertEqual(r['unique_visitors'],2);self.assertEqual(r['returning_visitors'],1)
        self.assertEqual(r['sources']['telegram']['visitor_days'],2)
        self.assertEqual(r['events']['follow'],1);self.assertNotIn('telegram_subscribers',r)

    def test_digest_ambiguous_send_does_not_repeat(self):
        from betbot import telegram,pages
        with tempfile.TemporaryDirectory() as tmp,patch.object(campaigns,'DIGEST',Path(tmp)/'digest.json'),patch.object(pages,'DOCS',Path(tmp)),patch.object(campaigns,'_news',return_value=[news(1),news(2),news(3)]),patch.object(telegram,'send_photo',side_effect=TimeoutError) as send:
            state={};campaigns.run(state,NOW);campaigns.run(state,NOW)
            self.assertEqual(send.call_count,1)
            self.assertEqual(state['growth']['digest_status'],'delivery_requires_review')

if __name__=='__main__':unittest.main()
