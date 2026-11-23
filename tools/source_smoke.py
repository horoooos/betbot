"""Read-only coverage proof for the current project fixture list."""
import html,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from betbot import intelligence as iq
out=Path('work/source-proof');out.mkdir(parents=True,exist_ok=True)
now=pd.Timestamp.now(tz='UTC');events=[]
for m in json.loads(Path(sys.argv[1] if len(sys.argv)>1 else 'docs/matches.json').read_text(encoding='utf-8')):
    if m.get('state')!='pre' or not now+pd.Timedelta(minutes=5)<pd.Timestamp(m['kickoff'])<=now+pd.Timedelta(days=2):continue
    e={k:m.get(k) for k in ['sport','div','id','state','kickoff','bo','path']}
    for i,side in enumerate(['home','away']):
        aliases=(m.get('participants') or [[],[]])[i]
        e[side]={'name':aliases[-1] if aliases else m[side],'ru':m[side]}
    events.append(e)
root={};report=iq.tick(root,events,now);store=iq.pool(root)
report.update(at=now.isoformat(),fixture_count=len(events),observations=len(store.get('observations',{})),
 examples=list(store['tips'].values())[:10],context_examples=list(store.get('contexts',{}).values())[:5])
(out/'sources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
rows=''.join('<tr><td>'+html.escape(p)+'</td>'+''.join('<td>'+html.escape(str(r.get(k,0)))+'</td>' for k in ['status','articles_available','discovered','pages','opinions','mapped','contexts'])+'</tr>' for p,r in report['providers'].items())
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>body{background:#090d20;color:#f4f5ff;font:16px/1.6 system-ui;padding:36px;max-width:1200px;margin:auto}h1{color:#ffcf00}section{padding:24px;border-radius:20px;background:#141c3c;margin:20px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #354165}small{color:#aab6d4}</style><h1>АИ СТАВИТ · проверка источников</h1><small>'+html.escape(now.isoformat())+'</small><section><b>Матчей в проверке: '+str(len(events))+'</b><p>Мнения авторов сохраняются отдельно от текущих коэффициентов. Вес новых источников — 0 до проверки на последующих результатах.</p></section><section><table><tr><th>Источник</th><th>Статус</th><th>Материалов</th><th>Найдено под наши матчи</th><th>Прочитано</th><th>Мнений</th><th>Понятных рынков</th><th>Контекстов</th></tr>'+rows+'</table></section>',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('examples','context_examples','model','sport_models')},ensure_ascii=False))
assert len(report['providers'])==len(iq.PROVIDERS)
assert sum(v['status']=='ok' for v in report['providers'].values())>=2,'Less than two sources accessible from this runner'
assert report['model']['weight']==0,'No unvalidated source weight allowed'
