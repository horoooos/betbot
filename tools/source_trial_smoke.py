"""Read-only source fallback simulation. Never sends Telegram/VK posts."""
import json,sys,html
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from betbot import source_trial as tr,stavka,stavka_markets,markets,sports,card,texts
out=Path('work/trial-proof');out.mkdir(parents=True,exist_ok=True)
now=pd.Timestamp.now(tz='UTC');root=stavka.load();state={};examples=[];checks=[]
for m in json.loads(Path('docs/matches.json').read_text(encoding='utf-8')):
    if m.get('state')!='pre' or not now+pd.Timedelta(minutes=5)<pd.Timestamp(m['kickoff'])<=now+pd.Timedelta(minutes=90):continue
    e={k:m.get(k) for k in ('sport','div','id','state','kickoff','bo')}
    for i,side in enumerate(('home','away')):
        aliases=(m.get('participants') or [[],[]])[i];e[side]={'name':aliases[-1] if aliases else m[side],'ru':m[side]}
    with patch.object(stavka,'save'):e=stavka_markets.ensure(e,now,root)
    odds=e.get('odds') or {}
    if not stavka_markets.complete_odds(e):continue
    if e['sport']=='football':
        lam=markets.implied_lambdas(markets.fair([odds['H'],odds['D'],odds['A']]),None,None)
        probs=markets.all_markets(*lam);real={k:odds[k] for k in ('H','D','A')};labels={k:markets.label(k) for k in markets.MARKETS};bar=(probs['H'],probs['D'],probs['A'])
    else:
        a=sports.analyse(e,{})
        if not a:continue
        probs,real,labels,bar=a['probs'],a['real'],a['labels'],a['bar']
    t=tr.select(e,probs,real,labels,state,pd.Timestamp.now(tz='UTC'),root)
    checks.append({'home':e['home']['ru'],'away':e['away']['ru'],'eligible':bool(t),'real_markets':len(real)})
    if t:
        examples.append({'event':e,'tip':t,'bar':bar})
    if len(checks)>=10:break
report={'at':now.isoformat(),'config':tr.config(now),'checked':checks,'examples':examples}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert tr.config(now),'Trial config must be active'
if examples:
    x=examples[0];e=x['event'];t=x['tip']
else:
    # The UI proof uses a marked fixture when no real source-backed match is due.
    e={'sport':'football','div':'E0','kickoff':(now+pd.Timedelta(hours=1)).isoformat(),'home':{'name':'Brentford','ru':'Брентфорд'},'away':{'name':'Everton','ru':'Эвертон'}}
    t={'strategy':'external_trial','p':.45,'odds':2.,'label':'П1','stake':.5,'source_count':2};x={'bar':(.45,.3,.25)}
png=card.match_card('Анализ матча',texts.when(pd.Timestamp(e['kickoff'])),e['home'],e['away'],x['bar'],t['label'],'Оценка матча по доступным данным','@aistavvit',sport=e['sport'],odds=f"{t['odds']:.2f}")
(out/'preview.png').write_bytes(png)
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#090d20;color:#f4f5ff;font:18px/1.6 system-ui;max-width:850px;margin:32px auto;padding:24px}img{width:100%;border-radius:16px}article{padding:24px;background:#151d3b;border-radius:20px}h1{color:#ffcf00}</style><h1>Резервный отбор прогнозов</h1><article><p>'+('Реальный кандидат, без публикации' if examples else 'Демонстрационный пример оформления')+'</p><img src="preview.png"><p>'+tr.note(t).replace('\n','<br>')+'</p><p>Виртуальный банк: 0,5%. Резервный отбор действует постоянно.</p></article>',encoding='utf-8')
print('Source-backed candidates:',len(examples),'checked markets:',len(checks))
