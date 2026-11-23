"""Restore user-deleted source forecasts; edit surviving ones. No new bank entries."""
import base64,datetime,html,json,os,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests
from bs4 import BeautifulSoup
from betbot import card,sports,texts,source_trial as tr,telegram,vk_rss
ROOT=Path(__file__).resolve().parents[1]
API='https://api.github.com/repos/horoooos/betbot/'
client=requests.Session();client.headers.update({'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
def api(path,body=None,method='GET'):
    r=client.request(method,API+path,json=body,timeout=40)
    if not r.ok:raise RuntimeError('GitHub recovery journal unavailable: '+str(r.status_code))
    return r.json()
def journal():
    r=client.get(API+'contents/data/source_reposts.json',timeout=30)
    if r.status_code==404:return {'reposts':{}},None
    if not r.ok:raise RuntimeError('Recovery journal unavailable')
    obj=r.json();return json.loads(base64.b64decode(obj['content'])),obj['sha']
def save(data,sha):
    body={'message':'Save source forecast republication receipts','content':base64.b64encode((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()).decode(),'branch':'main'}
    if sha:body['sha']=sha
    result=api('contents/data/source_reposts.json',body,'PUT')
    return result['content']['sha']
def exists(mid):
    r=requests.get(f'https://t.me/aistavvit/{mid}',params={'embed':1},timeout=15);r.raise_for_status();s=BeautifulSoup(r.content,'html.parser')
    if s.select_one(f'[data-post="aistavvit/{mid}"]'):return True
    err=s.select_one('.tgme_widget_message_error')
    if err and 'not found' in err.get_text().lower():return False
    raise RuntimeError('Public post availability could not be determined')
def clean(text):
    return tr.public_text(text)

if telegram.DRY:raise RuntimeError('Live Telegram credentials are required')
chat=telegram._call('getChat')
if chat.get('username','').lower()!='aistavvit':raise RuntimeError('Recovery is restricted to the owned main channel')
records={}
for name in ('matches.json','other.json'):
    records.update(json.loads((ROOT/'data'/name).read_text(encoding='utf-8')))
posts=json.loads((ROOT/'data/channel.json').read_text(encoding='utf-8')).get('posts',{})
now=pd.Timestamp.now(tz='UTC');data,sha=journal();report=[]
for m in records.values():
    if m.get('main',{}).get('strategy')!='external_trial' or not m.get('msg_id'):continue
    if not now-pd.Timedelta(days=1)<=pd.Timestamp(m['kickoff'])<=now+pd.Timedelta(days=1):continue
    old=int(m.get('original_msg_id',m['msg_id']));key=str(old)
    if data['reposts'].get(key,{}).get('status')=='done':continue
    tip=m['main'];ko=pd.Timestamp(m['kickoff']);sport=m.get('sport','football')
    caption=texts.caption(m,m.get('venue')) if sport=='football' else sports.caption(m,texts.when(ko))
    if ko<=now:
        caption='📌 <b>Прогноз, сделанный до начала матча</b>\n\n'+caption
    caption=tr.without_links(caption)
    bar=(m['probs']['H'],m['probs']['D'],m['probs']['A']) if sport=='football' else m['bar']
    center=f"xG {m['lam'][0]:.1f} : {m['lam'][1]:.1f}" if sport=='football' else m['center']
    league=texts.league_plain(m['div']) if sport=='football' else sports.league_plain(m['div'])
    png=card.match_card(league,texts.when(ko),m['home'],m['away'],bar,tip['label'],center,'@aistavvit',sport=sport,odds=f"{tip['odds']:.2f}")
    if not vk_rss.image_valid(png):raise RuntimeError('Recovery image failed validation')
    present=exists(old)
    # A sending reservation prevents an automatic second send after ambiguous failures.
    if data['reposts'].get(key,{}).get('status')=='sending':raise RuntimeError('Previous recovery requires receipt verification')
    data['reposts'][key]={'status':'sending','at':now.isoformat(),'action':'edit' if present else 'restore'};sha=save(data,sha)
    if present:
        media={'type':'photo','media':'attach://photo','caption':telegram.tag(caption),'parse_mode':'HTML'}
        telegram._call('editMessageMedia',files={'photo':('forecast.png',png,'image/png')},message_id=old,media=json.dumps(media,ensure_ascii=False),reply_markup=json.dumps({'inline_keyboard':[]}))
        mid=old
    else:mid=telegram.send_photo(png,caption,button=None)
    data['reposts'][key].update(status='done',message_id=mid,event_id=str(m['id']),original_kickoff=m['kickoff'],source_strategy=tip['strategy']);sha=save(data,sha)
    replies=[p for p in posts.values() if str(p.get('reply'))==str(old) and 0<=(pd.Timestamp(p['t'])-pd.Timestamp(m['kickoff'])+pd.Timedelta(hours=2)).total_seconds()<4*3600 and '#итог' not in p.get('html','') and '#live' not in p.get('html','')]
    edited=0
    if replies:
        for p in replies:
            if exists(int(p['id'])):
                try:
                    telegram._call('editMessageText',message_id=int(p['id']),text=clean(p['html']),parse_mode='HTML',disable_web_page_preview=True,reply_markup=json.dumps({'inline_keyboard':[]}));edited+=1
                except RuntimeError as exc:
                    if 'not modified' not in str(exc):raise
    if not present or not edited:
        body=tr.recovery_analysis(m)
        data['reposts'][key]['analysis_messages']=telegram.send(body,reply_to=mid,silent=True)
    data['reposts'][key]['analysis_done']=True;sha=save(data,sha)
    report.append({'original':old,'message_id':mid,'action':'edit' if present else 'restore','url':f'https://t.me/aistavvit/{mid}'})
Path('work').mkdir(exist_ok=True);Path('work/repost-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
