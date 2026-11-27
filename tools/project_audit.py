"""Read-only production health report. Never posts, edits or places bets."""
import json,os,sys,re,xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd,requests
from betbot import card,sports,content,pro,vk,vk_rss_audit,vk_rss
out=Path('work/project-audit');out.mkdir(parents=True,exist_ok=True)
report={'at':pd.Timestamp.now(tz='UTC').isoformat()}
state=json.loads(Path('data/state.json').read_text(encoding='utf-8'))
report['service_errors']={k:v for k,v in state.items() if ('err' in k.lower() or 'error' in k.lower()) and v}
posts=json.loads(Path('data/channel.json').read_text(encoding='utf-8'))['posts']
report['latest_main']=[{'id':k,'t':v.get('t'),'title':re.sub('<[^>]+>','',v.get('html',''))[:140],'photo':bool(v.get('photo'))} for k,v in sorted(posts.items(),key=lambda kv:int(kv[0]))[-12:]]
report['mirror']={k:state.get(k) for k in ('dz_last','dz_err','dz_last_delivery')}
report['expresses']={k:{f:(state.get(k) or {}).get(f) for f in ('day','done','msg','odds','stake_pct')} for k in ('express','express_risk')}
picks=state.get('source_trial',{}).get('picks',{})
report['learning']={k:state.get(k) for k in ('learned','learn_error','weights','stavka')}
report['fallback_statuses']=dict(Counter(v.get('status') for v in picks.values()))
report['unsettled']=[{k:p.get(k) for k in ('sport','id','kickoff','status')} for p in picks.values() if p.get('status')=='open']
site='https://horoooos.github.io/betbot/'
report['public_pages']=[]
for path in ('','news/','predictions/','live.html','esports.html','rss-vk-article.xml','matches.json'):
 try:
  r=requests.get(site+path,timeout=25)
  report['public_pages'].append({'path':path,'status':r.status_code,'bytes':len(r.content)})
 except requests.RequestException:report['public_pages'].append({'path':path,'error':'network'})
feed=requests.get(site+'rss-vk-article.xml',timeout=25);root=ET.fromstring(feed.content)
ns={'c':'http://purl.org/rss/1.0/modules/content/'}
report['feed_images']=[]
for item in root.findall('channel/item')[:6]:
 img=item.find('enclosure');url=img.get('url') if img is not None else ''
 report['feed_images'].append({'title':item.findtext('title'),'image_decodes':vk_rss.public_image_ready(url),'has_image_in_body':'<img ' in item.findtext('c:encoded','',ns)})
report['vk_api']={}
for name in ('VK_TOKEN','VK_USER_TOKEN'):
 if not os.environ.get(name):continue
 info={}
 for method,params in [('wall.getById',{'posts':'-228963529_913,-228963529_915'}),('photos.getWallUploadServer',{'group_id':vk.GROUP_ID})]:
  try:
   result=vk._call(method,_tok=os.environ[name],**params)
   if method=='wall.getById':
    items=result if isinstance(result,list) else result.get('items',[])
    info[method]=[{'id':p.get('id'),'types':[a.get('type') for a in p.get('attachments',[])],'cover':vk_rss_audit.cover_evidence(p.get('attachments',[]))} for p in items]
   else:info[method]={'upload_server_available':bool(result.get('upload_url'))}
  except RuntimeError as exc:info[method]={'error':str(exc)[:180]}
 report['vk_api'][name]=info
# No sends: compare corrected selection on today's real schedule / quotes.
try:
 from betbot.espn import scoreboard
 from betbot.leagues import ALL
 from run import REVIEW_LEAGUES,professional
 now=pd.Timestamp.now(tz='Europe/Moscow')
 days=[now.strftime('%Y%m%d'),(now+pd.Timedelta(days=1)).strftime('%Y%m%d')]
 football=[e for e in scoreboard({k:ALL[k][3] for k in REVIEW_LEAGUES},days) if professional(e,state.get("cup_teams",{}))]
 other=sports.fetch(now)
 from betbot import stavka
 stavka._runtime=stavka.load()
 for e in football+other:
  for side in ("home","away"):e[side].setdefault("ru",e[side].get("name",side))
 normal=content._favourites(football,other,now,14);risky=content._risky_legs(football,other,now)
 report['express_candidates']={'fixtures':len(football)+len(other),'normal':len(normal),'risky':len(risky),'tennis_normal':sum(e['sport']=='tennis' for e in normal),'with_quotes':sum(bool((e.get('odds') or {}).get('H')) for e in football+other)}
 for kind,legs in [('normal',normal[:3]),('risky',risky[:5])]:
  if not legs:continue
  odds=1.;p=1.
  for leg in legs:odds*=leg['odds'];p*=leg['p']
  (out/(kind+'.png')).write_bytes(card.express_card(legs,odds,p,str(now.date()),'АИ СТАВИТ'))
except Exception as exc:report['express_candidate_error']=type(exc).__name__+': '+str(exc)[:100]
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
