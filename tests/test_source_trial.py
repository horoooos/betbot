import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from betbot import source_trial as tr,markets,pro,texts
NOW=pd.Timestamp('2026-11-23T18:00:00Z')
E={'sport':'football','id':'1','div':'E0','state':'pre','kickoff':'2026-11-23T20:00:00Z','home':{'ru':'Брентфорд','name':'Brentford'},'away':{'ru':'Эвертон','name':'Everton'}}
C={'enabled':True,'starts_at':(NOW-pd.Timedelta(hours=1)).isoformat(),'expires_at':(NOW+pd.Timedelta(days=7)).isoformat(),'stake_pct':.5,'max_open':6}
def tip(author='a',**extra):
 return {'key':'H','author':author,'event_id':'1','div':'E0','sport':'football','kickoff':E['kickoff'],
         'published_at':(NOW-pd.Timedelta(hours=1)).isoformat(),'observed_at':NOW.isoformat(),'source':'https://example.test/forecast',
         'odds':9.0,'price_kind':'author_recorded',**extra}
def select(root,state=None,event=None):
 return tr.select(event or E,{'H':.45,'D':.3,'A':.25},{'H':2.0,'D':3.1,'A':3.2},{'H':'П1','D':'Ничья','A':'П2'},state if state is not None else {},NOW,root)
class SourceTrialTests(unittest.TestCase):
 def setUp(self):
  self.patch=patch.object(tr,'config',return_value=C);self.patch.start();self.addCleanup(self.patch.stop)
 def test_negative_model_edge_can_be_paper_tested_but_does_not_change_normal_gate(self):
  t=select({'tips':{'a':tip('a'),'b':tip('b')}})
  self.assertEqual(t['strategy'],'external_trial');self.assertEqual(t['stake'],.5)
  self.assertEqual(t['odds'],2.0);self.assertEqual(t['p'],.45);self.assertLess(t['model_edge'],0)
  self.assertEqual(pro.stake(t),0) # only the explicit trial path admits it
  self.assertEqual(t['source_count'],2)
 def test_one_crowd_author_or_repeated_copy_is_not_a_consensus(self):
  self.assertIsNone(select({'tips':{'a':tip('a'),'b':tip('a')}}))
  self.assertIsNotNone(select({'tips':{},'external_sources':{'tips':{'a':tip('named',provider='livesport')}}}))
 def test_author_quote_cannot_replace_missing_current_market(self):
  root={'tips':{'a':tip('a',key='O35'),'b':tip('b',key='O35')}}
  self.assertIsNone(select(root))
 def test_future_late_wrong_sport_and_wrong_fixture_are_excluded(self):
  for invalid in [dict(observed_at=(NOW+pd.Timedelta(seconds=1)).isoformat()),dict(published_at=E['kickoff']),dict(sport='tennis'),dict(kickoff='2026-11-24T20:00:00Z')]:
   self.assertIsNone(select({'tips':{'a':tip('a',**invalid),'b':tip('b',**invalid)}}))
  self.assertIsNone(select({'tips':{'a':tip('a'),'b':tip('b')}},event={**E,'kickoff':(NOW+pd.Timedelta(minutes=4)).isoformat()}))
 def test_stale_displayed_price_is_not_used(self):
  e={**E,'odds':{'observed_at':(NOW-pd.Timedelta(minutes=26)).isoformat()}}
  self.assertIsNone(select({'tips':{'a':tip('a'),'b':tip('b')}},event=e))
 def test_capacity_and_duplicate_publications_are_blocked(self):
  root={'tips':{'a':tip('a'),'b':tip('b')}};state={}
  t=select(root,state);tr.published(state,E,t,10,NOW)
  self.assertIsNone(select(root,state));self.assertEqual(len(state['source_trial']['picks']),1)
  full={'source_trial':{'picks':{str(i):{'status':'open'} for i in range(6)}}}
  self.assertIsNone(select(root,full))
 def test_settlement_uses_actual_results_and_preserves_half_percent_stake(self):
  state={};t=select({'tips':{'a':tip('a'),'b':tip('b')}});tr.published(state,E,t,10,NOW)
  result=pd.DataFrame([{'date':'2026-11-23','id':'1','sport':'football','main_key':'H','main_hit':False,'main_odds':2.,'main_stake':.5}])
  tr.settle(state,result,NOW);self.assertEqual(state['source_trial']['picks']['football|E0|1']['status'],'open')
  tr.settle(state,result,NOW+pd.Timedelta(hours=3));p=state['source_trial']['picks']['football|E0|1']
  self.assertEqual(p['status'],'settled');self.assertEqual(p['profit_pct'],-.5)
  with patch.object(pro,'expresses',return_value=pd.DataFrame()),patch.object(pro,'live_bets',return_value=pd.DataFrame()):
   self.assertEqual(pro.all_bets(result)[0][-1],.5)
 def test_public_text_names_trial_without_claiming_profitable_edge(self):
  t=select({'tips':{'a':tip('a'),'b':tip('b')}})
  m={**E,'main':t,'bold':{},'value':{},'probs':{'H':.45,'D':.3,'A':.25}}
  text=texts.caption(m,None)
  self.assertIn('Учтено внешних мнений',text)
  for word in ['Временный прогноз','тестовый','эксперимент']:self.assertNotIn(word,text)
  self.assertIn('модель: 45%',text);self.assertNotIn('выгодно с кэфа',text)
  self.assertLess(len(text),1024)
class TrialExpiryTests(unittest.TestCase):
 def test_config_auto_expires_and_does_not_restart_seven_days_on_reboot(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'config.json';path.write_text(json.dumps(C))
   with patch.object(tr,'CONFIG',path):
    self.assertIsNotNone(tr.config(NOW));self.assertIsNone(tr.config(NOW+pd.Timedelta(days=8)))
    self.assertIsNone(tr.config(NOW-pd.Timedelta(days=1)))
    path.write_text('{bad');self.assertIsNone(tr.config(NOW))

 def test_permanent_fallback_remains_enabled_after_the_old_expiry(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'config.json'
   c={**C,'permanent':True,'fallback_only':True,'expires_at':None}
   path.write_text(json.dumps(c))
   with patch.object(tr,'CONFIG',path):
    self.assertIsNotNone(tr.config(NOW+pd.Timedelta(days=365)))
    c['enabled']=False;path.write_text(json.dumps(c));self.assertIsNone(tr.config(NOW))
    c['enabled']=True;c['permanent']=False;path.write_text(json.dumps(c));self.assertIsNone(tr.config(NOW))
 def test_permanent_mode_cannot_silently_replace_the_regular_selector(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'config.json';path.write_text(json.dumps({**C,'permanent':True,'fallback_only':False}))
   with patch.object(tr,'CONFIG',path):self.assertIsNone(tr.config(NOW))

class SourcePresentationTests(unittest.TestCase):
 def test_reposted_message_alias_changes_only_navigation(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'reposts.json';p.write_text(json.dumps({'reposts':{'10':{'status':'done','message_id':20}}}))
   records={'a':{'id':'1','msg_id':10,'main':{'strategy':'external_trial','stake':.5,'odds':2.0}},'b':{'msg_id':10,'main':{'strategy':'model_value'}}}
   with patch.object(tr,'REPOSTS',p):tr.remap(records);tr.remap(records)
   self.assertEqual(records['a']['msg_id'],20);self.assertEqual(records['a']['original_msg_id'],10)
   self.assertEqual(records['a']['main']['stake'],.5);self.assertEqual(records['b']['msg_id'],10)
 def test_public_source_analysis_has_no_outbound_links_or_test_labels(self):
  tip={'strategy':'external_trial','stake':.5,'odds':2.0,'source_count':2,'source_refs':[{'source':'https://example.test/a'}]}
  text=tr.explanation(tip)
  for word in ['href=','https://','тестовый','эксперимент','Временный']:self.assertNotIn(word,text)
  self.assertEqual(tr.without_links('<b>Разбор</b> <a href="https://example.test">источник</a> https://example.test/a'),'<b>Разбор</b> источник')

 def test_old_cached_captions_are_cleaned_without_changing_the_pick(self):
  text='🎯 Прогноз\nП2 · кэф 1.92\n\n🧪 <b>Временный прогноз по внешним мнениям</b> · 25 мн.\nПроценты — оценка модели. Перевес не подтверждён; результат учитывается для обучения.\n\n🧪 Учёт в виртуальном банке: 0.5% · эксперимент'
  cleaned=tr.public_text(text)
  self.assertIn('П2 · кэф 1.92',cleaned)
  self.assertIn('0.5%',cleaned)
  self.assertNotIn('Временный',cleaned);self.assertNotIn('эксперимент',cleaned)

 def test_recovery_entry_import_order_works_in_a_fresh_process(self):
  import subprocess,sys
  run=subprocess.run([sys.executable,'-c','from betbot import card,sports,texts,source_trial,telegram,vk_rss'],capture_output=True)
  self.assertEqual(run.returncode,0,run.stderr.decode('utf-8',errors='replace'))
 def test_recovered_analysis_keeps_the_original_pick_without_outbound_links(self):
  tip={'strategy':'external_trial','key':'H','label':'П1','p':.45,'odds':2.0,'stake':.5,'source_count':2,'source_refs':[]}
  text=tr.recovery_analysis({**E,'main':tip})
  self.assertIn('П1',text);self.assertIn('2.00',text);self.assertNotIn('https://',text)
