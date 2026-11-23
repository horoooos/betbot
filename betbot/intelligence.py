"""Bounded public-source research. Opinions are not executable bookmaker quotes.

Only structured fields and short market labels are persisted, never article bodies.
New source signals have a separate chronological validation pool from Stavka TV.
"""
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup
from . import stavka

UA='BetBot/1.0 (public pre-match research)'
PROVIDERS={
 'legalbet':('https://legalbet.ru','/tips/',r'/tips/prognoz-na-match-[a-z0-9-]+/'),
 'livesport':('https://www.livesport.ru','/tips/',r'/tips/(?:football|hockey|tennis|basketball|esports)/20\d{2}/\d{2}/\d{2}/[a-z0-9-]+/'),
 'metaratings':('https://metaratings.ru','/prognozy/',r'/prognozy/(?:futbol|hokkey|tennis|basketbol|kibersport)/[a-z0-9-]+-prognoz-[a-z0-9-]+/'),
 'rb':('https://bookmaker-ratings.ru','/forecast_homepage/',r'/tips/(?!event-)[a-z0-9-]+/'),
 'vseprosport':('https://www.vseprosport.ru','/news/statistics',r'/news/20\d{2}/\d{2}/\d{2}/[a-z0-9-]+')}
SPORT_WORDS={'football':('футбол','soccer','football','futbol'),'hockey':('хоккей','hockey','hokkey','hokkej'),
 'basketball':('баскетбол','basketball','basketbol'),'tennis':('теннис','tennis'),'esports':('киберспорт','esports','kibersport','dota','counter-strike','cs2')}


def canonical(provider,url):
    host,listing,pattern=PROVIDERS[provider];p=urlsplit(urljoin(host,url))
    if p.scheme!='https' or p.netloc!=urlsplit(host).netloc or p.query or p.username or p.fragment:
        raise ValueError('Non-canonical research URL')
    if p.path not in (listing,'/robots.txt') and not re.fullmatch(pattern,p.path):raise ValueError('Unsupported research path')
    return host+p.path


def fetch(provider,url,session=requests):
    url=canonical(provider,url)
    r=session.get(url,headers={'User-Agent':UA},timeout=(5,12),allow_redirects=False)
    r.raise_for_status()
    if r.status_code!=200 or len(r.content)>4_000_000:raise ValueError('Unexpected research response')
    # Explicit bytes decoding avoids requests guessing Latin-1 for Russian HTML.
    text=r.content.decode('utf-8-sig',errors='strict')
    if any(x in text[:8000].lower() for x in ('just a moment...','cf-chl-','captcha-container')):raise ValueError('Source challenge')
    return text


def norm(text):
    return re.sub(r'[^a-zа-яё0-9]+',' ',stavka.normalized(str(text))).strip()


def mentions(text,team):
    text=' '+norm(text)+' '
    return any(len(norm(a))>=3 and ' '+norm(a)+' ' in text for a in stavka.team_aliases(team))


def title_match(title,events,sport=None,kickoff=None,day=None):
    hits=[]
    for e in events:
        if sport and e.get('sport','football')!=sport:continue
        if kickoff is not None and abs((stavka.utc(e['kickoff'])-stavka.utc(kickoff)).total_seconds())>300:continue
        if day and stavka.utc(e['kickoff']).tz_convert('Europe/Moscow').date()!=day:continue
        if mentions(title,e['home']) and mentions(title,e['away']):
            text=' '+norm(title)+' '
            positions=[min(text.find(' '+norm(a)+' ') for a in stavka.team_aliases(e[side]) if len(norm(a))>=3 and ' '+norm(a)+' ' in text) for side in ('home','away')]
            if positions[0]<positions[1]:hits.append(e)
    return hits[0] if len(hits)==1 else None


def jsonld(soup):
    def walk(x):
        if isinstance(x,list):
            for v in x:yield from walk(v)
        elif isinstance(x,dict):
            yield x
            yield from walk(x.get('@graph',[]))
    for el in soup.select('script[type="application/ld+json"]'):
        try:yield from walk(json.loads(el.get_text()))
        except (ValueError,TypeError):continue


def metadata(provider,soup,url,events,now):
    objects=list(jsonld(soup));articles=[v for v in objects if v.get('@type') in ('NewsArticle','Article','BlogPosting')]
    article=articles[0] if len(articles)==1 else {}
    h=soup.h1;title=h.get_text(' ',strip=True) if h else article.get('headline','')
    pub=article.get('datePublished')
    if not pub:
        el=soup.select_one('meta[property="article:published_time"],meta[itemprop="datePublished"]')
        pub=el.get('content') if el else None
    if not pub or 'экспресс' in title.lower():return None
    try:published=stavka.utc(pub)
    except (ValueError,TypeError):return None
    if published>stavka.utc(now) or published<stavka.utc(now)-pd.Timedelta(days=14):return None
    crumbs=' '.join(v.get('name','') for v in objects if v.get('@type')=='ListItem')
    # Breadcrumb text is restricted to the breadcrumb container, never unrelated recommendations.
    for el in soup.select('[itemtype*="BreadcrumbList"], [class*="breadcrumb"], [class*="Breadcrumb"]'):crumbs+=' '+el.get_text(' ',strip=True)
    sport_text=(url+' '+crumbs+' '+str(article.get('articleSection',''))).lower()
    sports=[k for k,words in SPORT_WORDS.items() if any(w in sport_text for w in words)]
    sport=sports[0] if len(sports)==1 else None
    fixtures=[v for v in objects if v.get('@type')=='SportsEvent' and v.get('startDate')]
    kick=None
    if len(fixtures)>1:return None
    if len(fixtures)==1:
        try:kick=stavka.utc(fixtures[0]['startDate'])
        except (ValueError,TypeError):return None
    elif provider=='vseprosport':
        el=soup.select_one('time.matchdate[datetime]')
        if el:
            try:kick=stavka.utc(el['datetime'])
            except ValueError:return None
    day=None
    if kick is None:
        m=re.search(r'(\d{1,2})\s+([а-я]+)(?:\s+(20\d{2}))?',title.lower())
        if not m or m[2][:3] not in stavka.MONTHS:return None
        try:day=pd.Timestamp(year=int(m[3] or stavka.utc(now).year),month=stavka.MONTHS.index(m[2][:3])+1,day=int(m[1])).date()
        except ValueError:return None
    e=title_match(title,events,sport,kick,day)
    if not e or published>=stavka.utc(e['kickoff']) or e.get('state')!='pre' or stavka.utc(e['kickoff'])<=stavka.utc(now)+pd.Timedelta(minutes=5):return None
    author=article.get('author') or {}
    if isinstance(author,list):author=author[0] if len(author)==1 else {}
    if isinstance(author,str):author={'name':author}
    name=author.get('name','')
    if not name:
        el=soup.select_one('[itemprop="author"] [itemprop="name"]')
        name=(el.get('content') or el.get_text(' ',strip=True)) if el else ''
    # Same named expert syndicated across sites gets a single author identity.
    author_id='expert:'+norm(name) if name else 'editorial:'+provider
    return e,published,author_id


def market_key(label,event):
    text=re.sub(r'\s+',' ',label.lower().replace('ё','е').replace('−','-')).strip(' .')
    if any(w in text for w in ['углов','тайм','четверт','период','карточ','офсайд','карт ','карте']):return None
    sport=event.get('sport','football')
    side={'п1':1,'п2':2,'победа 1':1,'победа 2':2}.get(text)
    if text.startswith('победа '):
        candidate=text[7:].strip(' «»')
        named=[i for i,s in enumerate(['home','away'],1) if norm(candidate) in {norm(a) for a in stavka.team_aliases(event[s])}]
        if len(named)==1:side=named[0]
    if side:
        if sport=='football':return 'H' if side==1 else 'A'
        if sport in ('tennis','esports'):return ('TN_W' if sport=='tennis' else 'ES_W')+str(side)
        # A plain P1 on hockey/basketball has ambiguous regulation/OT units.
        return None
    if sport=='football':
        if text in ('ничья','х','x'):return 'D'
        if text in ('1х','1x','х2','x2','12'):return text.upper().replace('Х','X')
        m=re.fullmatch(r'(?:тотал )?(больше|меньше|тб|тм)\s*\(?([1-4][.,]5)\)?(?: голов)?',text)
        if m:return ('O' if m[1] in ('больше','тб') else 'U')+m[2].replace('.','').replace(',','')
        if text in ('обе забьют да','обе забьют - да'):return 'BTTS_Y'
        if text in ('обе забьют нет','обе забьют - нет'):return 'BTTS_N'
    return None


def bets(provider,soup):
    if provider=='legalbet':
        for block in soup.select('.exp-forecast__bet-container'):
            label=block.select_one('.exp-forecast__bet-text');price=block.select_one('.exp-forecast__coefs-num')
            if label and price:yield label.get_text(' ',strip=True),price.get_text(strip=True)
    elif provider=='metaratings':
        for label in soup.select('[class*="BetBlock_bet__"]'):
            block=label.parent.parent;price=block.select_one('[class*="BetBlock_coef__"]')
            if price:yield label.get_text(' ',strip=True),price.get_text(strip=True)
    else:
        selector='.article-text p' if provider=='livesport' else 'p.break-words strong' if provider=='rb' else '.bet-content-tip'
        for el in soup.select(selector):
            text=el.get_text(' ',strip=True)
            m=re.fullmatch(r'(?:Ставка:|Прогноз:)\s*(.+?)\s+(?:за|с коэффициентом)\s+([0-9]+[.,][0-9]+)\s*\.?',text,re.I)
            if m:yield m[1],m[2]


def parse(provider,markup,url,events,now):
    url=canonical(provider,url);soup=BeautifulSoup(markup,'html.parser');meta=metadata(provider,soup,url,events,now)
    if not meta:return []
    event,published,author=meta
    tables=[]
    for table in soup.select('article table, .article-text table, [itemprop="articleBody"] table')[:2]:
        matrix=[]
        for tr in table.select('tr')[:7]:
            cells=[c.get_text(' ',strip=True)[:60] for c in tr.select('th,td')[:7]]
            if cells:matrix.append(cells)
        if matrix and any(re.search(r'\d',c) for row in matrix for c in row):tables.append(matrix)
    context=dict(id=hashlib.sha256(url.encode()).hexdigest()[:24],kind='context',provider=provider,source=url,
                 sport=event.get('sport','football'),div=event['div'],event_id=str(event['id']),
                 kickoff=stavka.utc(event['kickoff']).isoformat(),published_at=published.isoformat(),
                 observed_at=stavka.utc(now).isoformat(),tables=tables)
    rows=[context]
    for label,price in bets(provider,soup):
        if len(label)>180:continue
        try:odds=float(price.replace(',','.'))
        except ValueError:continue
        if not math.isfinite(odds) or not 1.01<odds<=100:continue
        key=market_key(label,event)
        uid=hashlib.sha256((url+'|'+author+'|'+norm(label)).encode()).hexdigest()[:24]
        rows.append(dict(id=uid,provider=provider,source=url,author=author,key=key,market_label=label,odds=odds,
            price_kind='author_recorded',sport=event.get('sport','football'),div=event['div'],event_id=str(event['id']),
            kickoff=stavka.utc(event['kickoff']).isoformat(),published_at=published.isoformat(),observed_at=stavka.utc(now).isoformat()))
    return rows


def collect_provider(provider,events,now,session=requests,offset=0,clock=None):
    host,listing,_=PROVIDERS[provider];report={'at':stavka.utc(now).isoformat(),'status':'unavailable','discovered':0,'pages':0,'opinions':0,'mapped':0};rows=[]
    try:
        robots=fetch(provider,host+'/robots.txt',session);rp=RobotFileParser();rp.parse(robots.splitlines())
        if not rp.can_fetch('BetBot',host+listing):report['status']='robots_disallowed';return rows,report
        soup=BeautifulSoup(fetch(provider,host+listing,session),'html.parser');urls=[];available=set()
        for a in soup.select('a[href]'):
            try:url=canonical(provider,a['href'])
            except ValueError:continue
            if url==host+listing or not rp.can_fetch('BetBot',url):continue
            available.add(url)
            title=a.get('title') or a.get_text(' ',strip=True)
            if not title_match(title,events):
                parent=a.parent
                for _ in range(2):
                    context=parent.get_text(' ',strip=True)
                    if len(context)<=1800 and title_match(context,events):title=context;break
                    parent=parent.parent if parent.parent else parent
            if title_match(title,events):urls.append(url)
        urls=list(dict.fromkeys(urls));report['discovered']=len(urls);report['articles_available']=len(available)
        if not available:report['status']='markup_changed';return rows,report
        # Bound article requests; listings are refreshed every thirty minutes.
        start=int(offset)%len(urls) if urls else 0
        selected=(urls[start:]+urls[:start])[:6]
        report['next_offset']=start+len(selected)
        for url in selected:
            try:
                markup=fetch(provider,url,session)
                observed=(clock or (lambda:pd.Timestamp.now(tz='UTC')))()
                rows.extend(parse(provider,markup,url,events,observed));report['pages']+=1
            except (requests.RequestException,ValueError,UnicodeError):report['page_errors']=report.get('page_errors',0)+1
        report.update(status='ok',opinions=sum(r.get('kind')!='context' for r in rows),mapped=sum(bool(r.get('key')) for r in rows),contexts=sum(r.get('kind')=='context' for r in rows))
    except (requests.RequestException,ValueError,UnicodeError) as exc:
        report['error']=type(exc).__name__
    return rows,report


def pool(root):
    return root.setdefault('external_sources',dict(version=1,multi_market=True,tips={},samples={},model={'status':'collecting','weight':0.0},sport_models={}))


def tick(root,events,now):
    from . import stavka_sports
    store=pool(root)
    changed=stavka.settle(store,events,now);changed_other=stavka_sports.settle(store,events,now)
    if not store.get('last_attempt') or stavka.utc(now)-stavka.utc(store['last_attempt'])>=pd.Timedelta(minutes=30):
        store['last_attempt']=stavka.utc(now).isoformat()
        upcoming=[e for e in events if e.get('state')=='pre' and stavka.utc(now)+pd.Timedelta(minutes=5)<stavka.utc(e['kickoff'])<=stavka.utc(now)+pd.Timedelta(days=2)]
        if upcoming:
            with ThreadPoolExecutor(max_workers=3) as workers:
                for provider,(rows,report) in zip(PROVIDERS,workers.map(lambda p:collect_provider(p,upcoming,now,offset=store.get('page_offsets',{}).get(p,0)),PROVIDERS)):
                    store.setdefault('page_offsets',{})[provider]=report.get('next_offset',0)
                    store.setdefault('providers',{})[provider]=report
                    for row in rows:
                        dest=store.setdefault('contexts',{}) if row.get('kind')=='context' else store['tips'] if row['key'] else store.setdefault('observations',{})
                        dest.setdefault(row['id'],row)
        # Preserve audit records for captured training samples; trim only unused observations.
        store['observations']={k:v for k,v in store.get('observations',{}).items() if stavka.utc(v['observed_at'])>=stavka.utc(now)-pd.Timedelta(days=30)}
    enrich(store,events,now)
    if changed or not store['model'].get('trained_at'):stavka.train(store,now)
    if changed_other or not store.get('sport_models'):stavka_sports.train(store,now)
    return {'providers':store.get('providers',{}),'opinions':len(store['tips']),'snapshots':len(store['samples']),'contexts':len(store.get('contexts',{})),
            'model':store['model'],'sport_models':store.get('sport_models',{})}


def adjust_football(event,lam,probs,now):
    root=stavka._runtime
    if root is None:return probs,{'status':'unavailable','weight':0.0}
    result,info=stavka.adjust(event,lam,probs,now,store=pool(root),persist=False)
    info['source']='multi_source';stavka.save(root)
    return result,info


def adjust_sport(event,analysis,now):
    from . import stavka_sports
    root=stavka._runtime
    if root is None:return analysis,{'status':'unavailable','weight':0.0}
    # stavka_sports.adjust normally saves its root; suppress that single write for the nested pool.
    result,info=stavka_sports.adjust(event,analysis,now,store=pool(root),persist=False)
    info['source']='multi_source';stavka.save(root)
    return result,info


def enrich(store,events,now,clock=None):
    """Point-in-time factual dossiers for due ESPN matches; no heuristic probability boosts."""
    from . import espn
    cache=store.setdefault('dossiers',{})
    due=[]
    for e in events:
        if e.get('state')!='pre' or e.get('sport','football') not in ('football','hockey','basketball'):continue
        if not stavka.utc(now)+pd.Timedelta(minutes=5)<stavka.utc(e['kickoff'])<=stavka.utc(now)+pd.Timedelta(hours=2):continue
        key=f"{e['div']}|{e['id']}";old=cache.get(key,{})
        if old.get('observed_at') and stavka.utc(now)-stavka.utc(old['observed_at'])<pd.Timedelta(minutes=15):continue
        slug=e.get('slug') or str(e.get('path','')).split('/')[-1]
        if not slug:continue
        due.append((e,key,slug))
    def read(item):
        e,key,slug=item;sport={'football':'soccer','hockey':'hockey','basketball':'basketball'}[e.get('sport','football')]
        try:
            data=espn.summary(slug,e['id'],sport)
            observed=(clock or (lambda:pd.Timestamp.now(tz='UTC')))()
            if stavka.utc(e['kickoff'])<=stavka.utc(observed)+pd.Timedelta(minutes=5):return key,{'observed_at':stavka.utc(observed).isoformat(),'status':'too_late'}
            facts={k:data[k] for k in ('table','last5','h2h','lineups','injuries','leaders','venue','city') if data.get(k)}
            result={'observed_at':stavka.utc(observed).isoformat(),'kickoff':stavka.utc(e['kickoff']).isoformat(),
                    'source':espn.SUMMARY.format(sport=sport,slug=slug,id=e['id']),
                    'status':'available' if facts else 'empty','facts':facts}
        except Exception as exc:result={'observed_at':stavka.utc(now).isoformat(),'status':'unavailable','error':type(exc).__name__}
        return key,result
    if due:
        with ThreadPoolExecutor(max_workers=3) as workers:
            cache.update(workers.map(read,sorted(due,key=lambda v:v[0]['kickoff'])[:6]))



def context_for(event):
    root=stavka._runtime or {};store=root.get('external_sources',{});key=f"{event['div']}|{event['id']}"
    refs=[r for r in store.get('contexts',{}).values() if r['event_id']==str(event['id']) and r['div']==event['div']
          and abs((stavka.utc(r['kickoff'])-stavka.utc(event['kickoff'])).total_seconds())<=300]
    return {'articles':refs,'dossier':store.get('dossiers',{}).get(key)}
