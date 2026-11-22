"""Discovery pages and opt-in retention, built only from existing sports data."""
from __future__ import annotations
import hashlib
import html
import json
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://horoooos.github.io/betbot/'
SPORTS = {'football':'Футбол','hockey':'Хоккей','basketball':'Баскетбол','tennis':'Теннис','esports':'Киберспорт'}

def topic_key(kind, sport, name=''):
    return kind + '-' + hashlib.sha256(f'{sport}|{name.casefold().strip()}'.encode()).hexdigest()[:20]

def topic(kind, sport, name=''):
    return {'id':topic_key(kind,sport,name),'kind':kind,'sport':sport,'name':name or SPORTS.get(sport,sport),
            'label':(name+' · ' if name else '')+SPORTS.get(sport,sport)}

def topics_for(sport, home='', away='', league=''):
    rows=[topic('sport',sport)]
    rows += [topic('team',sport,n) for n in (home,away) if n]
    if league:rows.append(topic('league',sport,league))
    return rows

def select_digest(news, now, limit=5):
    """Fresh, complete, distinct news, with sport diversity before recency."""
    now=pd.Timestamp(now);fresh=[];seen=set()
    for n in sorted(news,key=lambda x:pd.Timestamp(x['t']),reverse=True):
        title=re.sub(r'\W+',' ',n['title'].casefold()).strip()
        if (not n.get('complete',True) or n.get('digest') or not now-pd.Timedelta(hours=24)<=pd.Timestamp(n['t'])<=now
                or title in seen):continue
        seen.add(title);fresh.append(n)
    chosen=[];sports=set()
    for n in fresh:
        if n.get('sport') not in sports:chosen.append(n);sports.add(n.get('sport'))
        if len(chosen)>=limit:return chosen
    ids={str(n['id']) for n in chosen}
    return (chosen+[n for n in fresh if str(n['id']) not in ids])[:limit]

def digest_item(news, now):
    from .postimg import plain
    chosen=select_digest(news,now)
    if len(chosen)<3:return None
    day=pd.Timestamp(now).tz_convert('Europe/Moscow').strftime('%Y-%m-%d')
    paras=[]
    for n in chosen:
        text=plain(n['body']).strip()
        first=re.split(r'\n\s*\n',text)[0]
        paras.append('<b>'+html.escape(n['title'])+'</b>\n'+html.escape(first)+
                     '\n<a href="'+SITE+n['url']+'">Читать новость полностью</a>')
    return {'id':int('88'+day.replace('-','')),'title':'Главное в спорте за '+pd.Timestamp(now).strftime('%d.%m'),
            'sport':chosen[0]['sport'],'t':pd.Timestamp(now),'photo':None,'digest':True,'complete':True,
            'url':'digest/'+day+'.html','body':'\n\n'.join(paras),'items':[str(n['id']) for n in chosen],
            'desc':'Главные спортивные новости за последние 24 часа. Полные материалы и источники внутри.'}

def share_card(title, subtitle, path):
    """Original typographic artwork; no third-party broadcast footage."""
    from PIL import Image,ImageDraw
    from . import card
    image=Image.new('RGB',(1200,630));d=ImageDraw.Draw(image)
    for y in range(630):d.line((0,y,1200,y),fill=(12+int(y/55),17+int(y/65),40+int(y/35)))
    d.rounded_rectangle((750,-180,1350,470),radius=180,fill=(31,42,83))
    d.text((60,48),'АИ СТАВИТ',font=card.font(30,'ExtraBold'),fill='#ffc400')
    words=title.split();lines=[];line='';font=card.font(56,'ExtraBold')
    for word in words:
        if d.textlength((line+' '+word).strip(),font=font)>1060 and line:lines.append(line);line=word
        else:line=(line+' '+word).strip()
    if line:lines.append(line)
    # Fit the full title; never crop a team name or a headline.
    size=56
    while (len(lines)>4 or any(d.textlength(x,font=font)>1060 for x in lines)) and size>24:
        size-=2;font=card.font(size,'ExtraBold');lines=[];line=''
        for word in words:
            if d.textlength((line+' '+word).strip(),font=font)>1060 and line:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        if line:lines.append(line)
    for i,line in enumerate(lines):d.text((60,155+i*(size+12)),line,font=font,fill='white')
    d.text((60,505),subtitle,font=card.font(26,'Bold'),fill='#abb9db')
    d.line((60,565,1140,565),fill='#ffc400',width=3)
    d.text((60,585),'horoooos.github.io/betbot · @aistavvit',font=card.font(20,'Bold'),fill='#ffc400')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);image.save(path,'JPEG',quality=88)

def build(news, matches, now):
    from . import pages,pages_extra
    docs=pages.DOCS;upcoming=json.loads((docs/'matches.json').read_text(encoding='utf-8')) if (docs/'matches.json').exists() else []
    catalog={t['id']:t for s in SPORTS for t in [topic('sport',s)]};leagues={}
    for m in matches+upcoming:
        sp=m.get('sport','football')
        for t in topics_for(sp,m.get('home',''),m.get('away',''),m.get('league','')):catalog[t['id']]=t
        if m.get('league'):leagues.setdefault((sp,m['league']),{})[str(m.get('id',m.get('url')))]=m
    urls=['follow.html','tournaments/','digest/']
    cards=[]
    for (sp,name),rows in sorted(leagues.items()):
        t=topic('league',sp,name);url='tournaments/'+t['id']+'.html';t['url']=url;catalog[t['id']]['url']=url
        games=sorted(rows.values(),key=lambda m:str(m.get('kickoff','')),reverse=True)[:24]
        body='<p class="tag">'+html.escape(SPORTS.get(sp,sp))+'</p><h1>'+html.escape(name)+'</h1><p class="muted">Матчи, результаты и новости турнира. Обновляется автоматически.</p>'
        body+='<a class="btn gold" href="../follow.html?topic='+t['id']+'">Следить за турниром</a><div class="grid" style="margin-top:20px">'
        for m in games:
            link=m.get('url') or 'matches.html';score=str(m.get('score') or (str(m.get('hs'))+':'+str(m.get('as')) if m.get('hs') is not None and m.get('as') is not None else ''))
            body+='<a class="card" href="../'+html.escape(link,quote=True)+'"><b>'+html.escape(m.get('home','')+' — '+m.get('away',''))+'</b><p class="muted">'+html.escape(str(m.get('kickoff',''))[:16]+' '+score)+'</p></a>'
        body+='</div>';related=[n for n in news if n.get('sport')==sp and name.casefold() in (n['title']+' '+n['body']).casefold()][:6]
        if related:body+='<h2>Новости турнира</h2><div class="grid">'+''.join(pages._news_card(n,'../') for n in related)+'</div>'
        image='share/'+t['id']+'.jpg'
        if not (docs/image).exists():share_card(name,'Матчи · результаты · новости',docs/image)
        pages._write(docs/url,pages.page('../',name+' — матчи и новости · АИ СТАВИТ',name+': расписание, результаты и спортивные новости.',SITE+url,body,'teams',SITE+image))
        urls.append(url);cards.append('<a class="card" href="../'+url+'"><b>'+html.escape(name)+'</b><p class="muted">'+html.escape(SPORTS.get(sp,sp))+' · '+str(len(rows))+' матчей</p></a>')
    for t in catalog.values():
        if t['kind']=='team':t['url']=pages_extra.team_url(t['sport'],t['name'])
    pages._write(docs/'topics.json',json.dumps({'topics':list(catalog.values()),'at':pd.Timestamp(now).isoformat()},ensure_ascii=False))
    pages._write(docs/'tournaments/index.html',pages.page('../','Турниры — матчи и новости','Турниры по всем видам спорта.',SITE+'tournaments/','<h1>Турниры</h1><div class="grid">'+''.join(cards)+'</div>','teams'))
    body='<h1>Мой <span>спорт</span></h1><p class="muted">Выберите команды, турниры и виды спорта. Уведомления приходят только по выбранным интересам. Настройки хранятся для этого браузера.</p><div id="growthPreferences" class="card">Загружаем интересы…</div>'
    pages._write(docs/'follow.html',pages.page('','Мой спорт — персональные уведомления','Выбор команд, турниров и видов спорта. Начало матча, результат и новости.',SITE+'follow.html',body,'teams'))
    from .growth_campaigns import saved_digest
    digest=saved_digest() or digest_item(news,now)
    if digest:
        cover=docs/'share'/('digest-'+pd.Timestamp(digest['t']).strftime('%Y-%m-%d')+'.jpg')
        if not cover.exists():share_card(digest['title'],'Главные новости · без повторов',cover)
        digest['photo']=SITE+'share/'+cover.name
        pages._write(docs/digest['url'],pages.page('../',digest['title'],digest['desc'],SITE+digest['url'],'<h1>'+html.escape(digest['title'])+'</h1><img style="width:100%;border-radius:20px" src="../share/'+cover.name+'" alt="Обложка новостей">'+''.join('<div class="card" style="margin-top:16px">'+p.replace('\n','<br>')+'</div>' for p in digest['body'].split('\n\n')),'news',digest['photo']))
        urls.append(digest['url'])
    archives=sorted((docs/'digest').glob('20*.html'),reverse=True)[:30]
    pages._write(docs/'digest/index.html',pages.page('../','Главное в спорте — ежедневный дайджест','Подборки проверенных спортивных новостей за день.',SITE+'digest/','<h1>Главное <span>за день</span></h1><div class="grid">'+''.join('<a class="card" href="'+f.name+'">Новости за '+f.stem+'</a>' for f in archives)+'</div>','news'))
    return urls

def summarize_visits(days):
    sources={};content={};events={'share':0,'follow':0,'unfollow':0,'telegram_click':0};visitors=set();returning=set()
    for day,rows in sorted((days or {}).items()):
        for vid,row in (rows or {}).items():
            if not isinstance(row,dict):continue
            source=str(row.get('r','Прямой заход'))[:40];s=sources.setdefault(source,{'visitor_days':0,'follow':0,'share':0,'telegram_click':0})
            if row.get('kind')!='event':s['visitor_days']+=1
            material=str(row.get('c') or row.get('p') or 'не указан')[:120];content.setdefault(material,{'visitor_days':0,'follow':0,'share':0});content[material]['visitor_days']+=int(row.get('kind')!='event')
            if row.get('kind')!='event':
                if vid in visitors:returning.add(vid)
                visitors.add(vid)
            for event,count in (row.get('a') or {}).items():
                if event in events and isinstance(count,(int,float)) and 0<=count<=1000:
                    events[event]+=count
                    if event in s:s[event]+=count
                    if event in content[material]:content[material][event]+=count
    return {'unique_visitors':len(visitors),'returning_visitors':len(returning),'sources':sources,'content':dict(sorted(content.items(),key=lambda x:-x[1]['visitor_days'])[:30]),'events':events,
            'note':'События браузера, а не подтверждённые подписки Telegram. Источники считаются по дням; блокировщики могут уменьшать счётчики.'}
