"""Bounded news campaigns and individual opt-in notifications."""
import html
import hashlib
import json
import os
import re
from pathlib import Path
import pandas as pd
from . import growth

DIGEST=growth.ROOT/'data/growth_digest.json'

def saved_digest():
    if not DIGEST.exists():return None
    n=json.loads(DIGEST.read_text(encoding='utf-8'));n['t']=pd.Timestamp(n['t']);return n

def _news():
    from . import pages
    p=growth.ROOT/'data/channel.json'
    store={int(k):v for k,v in json.loads(p.read_text(encoding='utf-8')).get('posts',{}).items()}
    return [n for n in pages._news(store) if not n['title'].startswith('Главное в спорте за')]

def run(state,now,checkpoint=lambda:None):
    from . import telegram,pages,promotion
    now=pd.Timestamp(now).tz_convert('Europe/Moscow');day=now.strftime('%Y-%m-%d');record=state.setdefault('growth',{})
    news=_news()
    if now.hour>=20 and record.get('digest_day')!=day:
        item=growth.digest_item(news,now)
        if item:
            cover=pages.DOCS/'share'/f'digest-{day}.jpg';growth.share_card(item['title'],'Главные спортивные новости дня',cover)
            item['photo']=growth.SITE+'share/'+cover.name
            DIGEST.write_text(json.dumps({**item,'t':item['t'].isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
            record.update(digest_day=day,digest_status='sending');checkpoint()
            try:
                titles=[n for n in growth.select_digest(news,now)]
                caption='<b>'+html.escape(item['title'])+'</b>\n\n'+'\n\n'.join('• '+html.escape(n['title']) for n in titles)
                # Full article remains accessible even if five long titles exceed a caption.
                while len(caption)>850 and len(titles)>1:
                    titles.pop();caption='<b>'+html.escape(item['title'])+'</b>\n\n'+'\n\n'.join('• '+html.escape(n['title']) for n in titles)
                caption+='\n\nПолные новости — в выпуске на сайте.\n\n'+{'football':'#футбол','hockey':'#хоккей','basketball':'#баскетбол','tennis':'#теннис','esports':'#киберспорт'}[item['sport']]
                mid=telegram.send_photo(cover.read_bytes(),caption,button=[('Читать выпуск',growth.SITE+item['url']+'?utm_source=telegram&utm_medium=digest'),('Мой спорт',growth.SITE+'follow.html')])
                record.update(digest_status='published',digest_message=mid)
            except Exception as e:record.update(digest_status='delivery_requires_review',digest_error=type(e).__name__)
            checkpoint()
    # Three original text-based news videos per week, independent of betting clips.
    if now.weekday() in (1,3,5) and now.hour>=14 and record.get('video_day')!=day:
        chosen=growth.select_digest(news,now,1)
        if chosen:
            record.update(video_day=day,video_status='rendering');checkpoint()
            try:
                from . import news_video
                clip=news_video.render(chosen[0])
                if not clip:raise RuntimeError('Video render unavailable')
                out=pages.DOCS/'media'/f'news-{day}.mp4';out.parent.mkdir(exist_ok=True);out.write_bytes(clip)
                record['video_status']='sending';checkpoint()
                n=chosen[0];tag={'football':'#футбол','hockey':'#хоккей','basketball':'#баскетбол','tennis':'#теннис','esports':'#киберспорт'}[n['sport']]
                mid=telegram.send_video(clip,'📰 <b>'+html.escape(n['title'])+'</b>\n\n'+growth.SITE+n['url']+'\n\n'+tag,width=1080,height=1920,duration=14)
                record.update(video_status='published',video_message=mid)
                if all(os.environ.get(k) for k in ('YT_CLIENT_ID','YT_CLIENT_SECRET','YT_REFRESH_TOKEN')):
                    from . import shorts
                    record['youtube_error']=shorts._youtube(clip,{'yt_title':n['title'][:90]+' #shorts','yt_desc':n['title']+'\n'+growth.SITE+n['url'],'yt_tags':['спорт','новости',n['sport'],'АИ СТАВИТ']})
                else:record['youtube_status']='requires_authorization'
            except Exception as e:record.update(video_status='requires_review',video_error=type(e).__name__)
            checkpoint()

def matches_interest(interests,sport,home='',away='',league='',text=''):
    selected=interests.get('topics') or {}
    return any(selected.get(t['id']) for t in growth.topics_for(sport,home,away,league))

def notify(events,news,state,now,checkpoint=lambda:None):
    from . import push
    if not push.enabled():return
    token=push._token()
    if not token:return
    now=pd.Timestamp(now);record=state.setdefault('growth_notify',{});started=record.setdefault('started_at',now.isoformat())
    sent=record.setdefault('sent',{});previous=record.setdefault('matches',{});candidates=[]
    for e in events:
        mid=str(e.get('id'));st=e.get('state');old=previous.get(mid);previous[mid]=st
        if old is None or st==old or st not in ('in','post'):continue
        h=e.get('home') or {};a=e.get('away') or {};home=h.get('ru') or h.get('name','');away=a.get('ru') or a.get('name','')
        sport=e.get('sport','football');from .live import _league
        league=str(e.get('league') or (_league(e) if e.get('div') else '') or '')
        kind='start' if st=='in' else 'result'
        score=''
        if st=='post':
            sc=push._score(e)
            if sc:score=f' {sc[0]}:{sc[1]}'
        candidates.append({'id':mid+':'+kind,'match':mid,'kind':kind,'sport':sport,'home':home,'away':away,'league':league,
            'title':('Матч начался: ' if st=='in' else 'Матч завершён: ')+home+' — '+away+score,
            'link':growth.SITE+'matches.html'})
    for n in growth.select_digest(news,now,30):
        if pd.Timestamp(n['t'])<pd.Timestamp(started):continue
        candidates.append({'id':'news:'+str(n['id']),'kind':'news','sport':n['sport'],'title':n['title'],'link':growth.SITE+n['url'],'news':n})
    catalog_path=growth.ROOT/'docs/topics.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8')).get('topics',[]) if catalog_path.exists() else []
    day=now.strftime('%Y-%m-%d');daily=record.setdefault('daily',{})
    if daily.get('day')!=day:daily.clear();daily['day']=day
    for key,subscriber in list(push._subscribers(token).items()):
        interests=subscriber.get('interests') if isinstance(subscriber,dict) else None
        if not interests or not subscriber.get('t'):continue
        for c in candidates:
            subscriber_id=hashlib.sha256(key.encode()).hexdigest()[:24]
            receipt=subscriber_id+':'+c['id']
            if receipt in sent or not interests.get('events',{}).get(c['kind']):continue
            if c.get('match') in (subscriber.get('m') or {}):continue
            matched=matches_interest(interests,c['sport'],c.get('home',''),c.get('away',''),c.get('league',''))
            if c['kind']=='news' and not matched:
                text=(c['title']+' '+c['news']['body']).casefold()
                matched=any(t['kind']!='sport' and t['sport']==c['sport'] and interests.get('topics',{}).get(t['id']) and re.search(r'(?<!\w)'+re.escape(t['name'].casefold())+r'(?!\w)',text) for t in catalog)
            if not matched or c['kind']=='news' and daily.get(subscriber_id,0)>=5:continue
            # Receipt before transmission: ambiguous timeouts must not send twice.
            sent[receipt]=now.isoformat()
            if c['kind']=='news':daily[subscriber_id]=daily.get(subscriber_id,0)+1
            checkpoint()
            push._send(token,key,subscriber['t'],c['title'],'Ваши выбранные спортивные события',c['link'],'interest-'+c['id'])
    cutoff=now-pd.Timedelta(days=7)
    record['sent']={k:v for k,v in sent.items() if pd.Timestamp(v)>=cutoff}
    active={str(e.get('id')) for e in events};record['matches']={k:v for k,v in previous.items() if k in active}
