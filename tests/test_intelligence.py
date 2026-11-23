import copy,json,unittest
from unittest.mock import patch
import pandas as pd
from betbot import intelligence as iq,stavka,markets,stavka_sports
NOW=pd.Timestamp('2026-11-23T12:00:00Z')
E={'id':'123','div':'E0','sport':'football','state':'pre','kickoff':'2026-11-24T16:30:00Z',
   'home':{'name':'Zenit','ru':'Зенит'},'away':{'name':'Krylya Sovetov','ru':'Крылья Советов'}}
URL='https://www.livesport.ru/tips/football/2026/11/24/zenit-krylya/'
def page(pub='2026-11-23T10:00:00Z',kick=E['kickoff'],label='Тотал больше 2.5',price='1.90',name='Зенит — Крылья Советов'):
    ld=[{'@type':'NewsArticle','datePublished':pub,'author':{'name':'Иван Экспертов'},'headline':name},
        {'@type':'SportsEvent','startDate':kick,'name':name}]
    return '<h1>'+name+'</h1><script type="application/ld+json">'+json.dumps(ld)+'</script><section class="article-text"><p>Ставка: '+label+' за <strong>'+price+'</strong>.</p><table><tr><th>Удары</th><td>12</td></tr></table></section>'
class IntelligenceTests(unittest.TestCase):
    def test_public_structured_opinion_is_never_a_current_quote(self):
        rows=iq.parse('livesport',page(),URL,[E],NOW)
        tip=next(r for r in rows if r.get('key'))
        self.assertEqual(tip['key'],'O25');self.assertEqual(tip['price_kind'],'author_recorded')
        self.assertEqual(tip['author'],'expert:иван экспертов')
        self.assertEqual(rows[0]['tables'],[[['Удары','12']]])
        self.assertNotIn('articleBody',rows[0]);self.assertNotIn('odds',rows[0])
    def test_postkick_future_and_wrong_kickoff_pages_are_excluded(self):
        for markup in [page(pub='2026-11-25T10:00:00Z'),page(kick='2026-11-25T16:30:00Z'),page(pub='2026-11-23T12:01:00Z')]:
            self.assertEqual(iq.parse('livesport',markup,URL,[E],NOW),[])
    def test_two_named_teams_order_and_unique_fixture_are_required(self):
        self.assertIsNone(iq.title_match('Зенит — Крылья Советов',[E,{**E,'id':'456'}]))
        self.assertIsNone(iq.title_match('Крылья Советов — Зенит',[E]))
        self.assertIsNone(iq.title_match('Зенит — Крылья Советов 2',[{**E,'away':{'name':'Reserve','ru':'Крылья Советов 2'}}],sport='tennis'))
        self.assertIs(iq.title_match('Зенит — Крылья Советов',[E]),E)
    def test_market_units_not_guessed(self):
        for label in ['Тотал угловых больше 2.5','Тотал первого тайма больше 2.5','Победа Зенита с форой (-1.5)']:
            self.assertIsNone(iq.market_key(label,E))
        for sport in ['hockey','basketball']:self.assertIsNone(iq.market_key('П1',{**E,'sport':sport}))
        self.assertEqual(iq.market_key('П1',{**E,'sport':'tennis'}),'TN_W1')
        self.assertEqual(iq.market_key('П2',{**E,'sport':'esports'}),'ES_W2')
    def test_unmodeled_markets_are_audited_without_entering_model(self):
        rows=iq.parse('livesport',page(label='Тотал угловых больше 9.5'),URL,[E],NOW)
        self.assertEqual(len(rows),2);self.assertIsNone(rows[1]['key'])
    def test_ssrf_queries_and_redirects_not_supported(self):
        for url in ['https://evil.test/tips/a/','http://www.livesport.ru/tips/','https://www.livesport.ru/tips/?token=secret','https://www.livesport.ru/away?x']:
            with self.assertRaises(ValueError):iq.canonical('livesport',url)
    def test_source_failure_does_not_break_collection(self):
        with patch.object(iq,'fetch',side_effect=TimeoutError):
            # Network errors in requests have a bounded unavailable result.
            import requests
            with patch.object(iq,'fetch',side_effect=requests.Timeout):
                rows,status=iq.collect_provider('livesport',[E],NOW)
        self.assertEqual(rows,[]);self.assertEqual(status['status'],'unavailable')
        self.assertNotIn('https',str(status.get('error')))
    def test_robots_disallow_prevents_article_requests(self):
        with patch.object(iq,'fetch',return_value='User-agent: *\nDisallow: /tips/') as fetch:
            rows,status=iq.collect_provider('livesport',[E],NOW)
        self.assertEqual(fetch.call_count,1);self.assertEqual(status['status'],'robots_disallowed')
    def test_http_challenge_is_not_a_healthy_empty_feed(self):
        class Response:
            status_code=200;content=b'<title>Just a moment...</title>'
            def raise_for_status(self):pass
        class Client:
            def get(self,*a,**kw):return Response()
        with self.assertRaises(ValueError):iq.fetch('livesport',URL,Client())
    def test_nested_learning_never_replaces_the_production_store(self):
        root={'tips':{'original':{}},'samples':{},'model':{'status':'collecting','weight':0}}
        ext=iq.pool(root)
        for i in range(3):ext['tips'][str(i)]={'author':str(i),'event_id':'123','div':'E0','kickoff':E['kickoff'],'published_at':'2026-11-23T10:00:00Z','observed_at':NOW.isoformat(),'key':'H','odds':2,'source':URL}
        base=markets.all_markets(1.6,1.1)
        with patch.object(stavka,'_runtime',root),patch.object(stavka,'save') as save:
            result,info=iq.adjust_football(E,(1.6,1.1),base,NOW)
        self.assertEqual(info['weight'],0);self.assertEqual(result,base)
        self.assertIn('E0|123',ext['samples']);self.assertIn('original',root['tips'])
        self.assertIs(save.call_args[0][0],root)
    def test_collector_backoff_and_first_observation_are_preserved(self):
        root={};row=next(r for r in iq.parse('livesport',page(),URL,[E],NOW) if r.get('key'))
        with patch.object(iq,'collect_provider',return_value=([row],{'status':'ok'})) as collect:
            iq.tick(root,[E],NOW);iq.tick(root,[E],NOW+pd.Timedelta(minutes=1))
        self.assertEqual(collect.call_count,len(iq.PROVIDERS));self.assertEqual(len(iq.pool(root)['tips']),1)
        self.assertEqual(iq.pool(root)['model']['weight'],0)

    def test_dossier_uses_only_prematch_events_and_retains_missing_data(self):
        from betbot import espn
        due={**E,'kickoff':(NOW+pd.Timedelta(hours=1)).isoformat(),'slug':'eng.1'}
        past={**due,'id':'past','state':'post'};store={}
        with patch.object(espn,'summary',return_value={'injuries':{'1':[('Игрок','Out')]},'lineups':{}}) as summary:
            iq.enrich(store,[due,past],NOW,clock=lambda:NOW);iq.enrich(store,[due,past],NOW+pd.Timedelta(minutes=1),clock=lambda:NOW+pd.Timedelta(minutes=1))
        self.assertEqual(summary.call_count,1)
        dossier=store['dossiers']['E0|123'];self.assertIn('injuries',dossier['facts'])
        self.assertNotIn('lineups',dossier['facts']);self.assertNotIn('E0|past',store['dossiers'])
        self.assertEqual(dossier['observed_at'],NOW.isoformat())

    def test_late_network_response_cannot_be_stamped_as_prematch_information(self):
        from betbot import espn
        due={**E,'kickoff':(NOW+pd.Timedelta(minutes=6)).isoformat(),'slug':'eng.1'}
        store={}
        with patch.object(espn,'summary',return_value={'lineups':{'1':{'starters':['player']}}}):
            iq.enrich(store,[due],NOW,clock=lambda:NOW+pd.Timedelta(minutes=7))
        self.assertEqual(store['dossiers']['E0|123']['status'],'too_late')
        self.assertNotIn('facts',store['dossiers']['E0|123'])

    def test_external_totals_and_btts_really_reach_the_model(self):
        import numpy as np
        root={};store=iq.pool(root)
        for i in range(3):
            store['tips'][str(i)]={'author':str(i),'event_id':'123','div':'E0','kickoff':E['kickoff'],
               'published_at':'2026-11-23T10:00:00Z','observed_at':NOW.isoformat(),'key':'O35','odds':2.2,'source':URL}
        votes,opinions=stavka.votes_for(store,E,NOW)
        self.assertEqual(votes['O35'],3);self.assertEqual(len(opinions),3)
        old=stavka.adjusted_matrix((1.6,1.1),votes,.3)
        new=stavka.adjusted_matrix((1.6,1.1),votes,.3,extended=True)
        mask=np.add.outer(np.arange(old.shape[0]),np.arange(old.shape[1]))>3.5
        self.assertGreater(new[mask].sum(),old[mask].sum());self.assertAlmostEqual(float(new.sum()),1)
        self.assertTrue(np.isfinite(new).all());self.assertTrue((new>=0).all())
