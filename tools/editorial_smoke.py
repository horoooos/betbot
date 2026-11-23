"""Read-only live smoke check. Never sends social posts or writes production data."""
import json,sys,html
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from betbot import news,pages,stavka,stavka_markets
out=Path('work/news-proof');out.mkdir(parents=True,exist_ok=True)
now=pd.Timestamp.now(tz='UTC');report={'at':now.isoformat(),'quotes':[]}
# Probe upcoming project fixtures, not invented matches; don't persist the probe store.
events=[]
for m in json.loads(Path('docs/matches.json').read_text(encoding='utf-8')):
    if m.get('state')!='pre' or not now+pd.Timedelta(minutes=5)<pd.Timestamp(m['kickoff'])<now+pd.Timedelta(days=1):continue
    e={k:m.get(k) for k in ['sport','div','id','state','kickoff','bo']}
    for i,side in enumerate(['home','away']):
        aliases=(m.get('participants') or [[],[]])[i]
        e[side]={'name':aliases[-1] if aliases else m[side],'ru':m[side]}
    events.append(e)
store={}
with patch.object(stavka,'save'):
    for e in events[:12]:
        r=stavka_markets.ensure(e,now,store)
        report['quotes'].append({'sport':e['sport'],'home':e['home']['name'],'away':e['away']['name'],
            'status':store.get('quote_status',{}).get(f"{e['div']}|{e['id']}",{}),
            'complete':stavka_markets.complete_odds(r),'odds':r.get('odds')})
posts=json.loads(Path('data/channel.json').read_text(encoding='utf-8'))['posts']
items=pages._news({int(k):v for k,v in posts.items()})
n=next(n for n in items if len(news._clean(n['body']))>600)
body=news._clean(n['body']);item={'title':n['title'],'desc':body[:600],'body':body}
# Limit model discovery to the first free configured candidate per provider.
models=news._models
with patch.object(news,'_models',side_effect=lambda *a:models(*a)[:1]):
    result=news._rewrite(item)
report['editorial']={'source_title':n['title'],'result':result}
(out/'editorial-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert result,'No validated editorial response from free providers'
assert '/humanize' not in result['text']
content=''.join('<p>'+html.escape(p)+'</p>' for p in result['text'].split('\n\n'))
(out/'editorial.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>body{background:#090d20;color:#f4f5ff;font:18px/1.6 system-ui;max-width:720px;margin:40px auto;padding:24px}article{background:#141c3c;border-radius:20px;padding:28px}h1{font-size:27px;line-height:1.3}small{color:#aeb9d8}p{margin:20px 0}</style><small>Проверка редакторского стиля · без публикации</small><article><h1>'+html.escape(result['title'])+'</h1>'+content+'</article>',encoding='utf-8')
print('Live quote checks:',len(report['quotes']),'complete:',sum(q['complete'] for q in report['quotes']))
print('Validated editorial paragraphs:',len(result['text'].split('\n\n')))
