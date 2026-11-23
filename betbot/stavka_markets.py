"""Explicit market units; an author's recorded price is never a live quote."""
import re
import math

import pandas as pd
from bs4 import BeautifulSoup


def tennis_key(label):
    label=re.sub(r'\s+',' ',label.upper().replace('Ё','Е').replace('−','-')).strip(' .')
    m=re.fullmatch(r'ТОЧНЫЙ СЧЕТ ([0-3]):([0-3])',label)
    if m and max(int(m[1]),int(m[2])) in (2,3) and m[1]!=m[2]:
        return 'TN_S'+m[1]+':'+m[2]
    number=r'([+-]?\d{1,2}(?:[.,]5)?)'
    m=re.fullmatch(r'ТОТАЛ( ПО СЕТАМ)? (БОЛЬШЕ|МЕНЬШЕ) \('+number+r'\)',label)
    if m:
        return 'TN_'+('S' if m[1] else 'G')+('O' if m[2]=='БОЛЬШЕ' else 'U')+f'{float(m[3].replace(",",".")):g}'
    m=re.fullmatch(r'ФОРА ([12])( ПО СЕТАМ)? \('+number+r'\)',label)
    if m:
        return 'TN_'+('SH' if m[2] else 'GH')+m[1]+'_'+f'{float(m[3].replace(",",".")):g}'
    m=re.fullmatch(r'ИНДИВИДУАЛЬНЫЙ ТОТАЛ ([12]) (БОЛЬШЕ|МЕНЬШЕ) \('+number+r'\)',label)
    if m:
        return 'TN_IG'+m[1]+('O' if m[2]=='БОЛЬШЕ' else 'U')+f'{float(m[3].replace(",",".")):g}'
    return None


def modeled_key(key,event):
    """Only identities valid for the known series format, never game guesses."""
    if key in ('TN_W1','TN_W2'):return key
    need=3 if event.get('bo5') else 2
    if key and key.startswith('TN_S') and ':' in key:
        h,a=map(int,key[4:].split(':'))
        return key if max(h,a)==need and min(h,a)<need else None
    if not event.get('bo5'):
        return {'TN_SO2.5':'TN_3S','TN_SU2.5':'TN_2S','TN_SH1_-1.5':'TN_S2:0',
                'TN_SH2_-1.5':'TN_S0:2','TN_SH1_1.5':'TN_SET1','TN_SH2_1.5':'TN_SET2'}.get(key)
    return None


def parse_quotes(html,source,event,now):
    """A complete winner market from one explicitly named bookmaker."""
    from .stavka import utc
    if event.get('sport','football') not in ('football','tennis','esports','hockey','basketball') or event.get('state')!='pre' or utc(event['kickoff'])<=utc(now)+pd.Timedelta(minutes=5):return None
    source_day=re.search(r'/matches/[^/]+/(\d{2}-\d{2}-\d{4})-',source)
    if source_day:
        day=pd.to_datetime(source_day[1],format='%d-%m-%Y').date()
        if day not in {utc(event['kickoff']).date(),utc(event['kickoff']).tz_convert('Europe/Moscow').date()}:return None
    soup=BeautifulSoup(html,'html.parser')
    headers=soup.select('.MatchHeaderRates')
    if len(headers)!=1:return None
    prices={};books=set()
    for button in headers[0].select('button'):
        label=button.select_one('.outcome');rate=button.select_one('.rate');logo=button.select_one('img[alt]')
        if not label or not rate or not logo:continue
        key={'П1':'H','П2':'A','X':'D','Х':'D','Н':'D'}.get(label.get_text(strip=True))
        if not key:continue
        try:price=float(rate.get_text(strip=True).replace(',','.'))
        except ValueError:continue
        book=logo['alt'].strip().lower()
        if not book or not math.isfinite(price) or not 1.01<price<=100 or key in prices:return None
        prices[key]=price;books.add(book)
    expected={'H','D','A'} if event.get('sport','football')=='football' else {'H','A'}
    # Main three-way hockey/basketball headers describe regulation time, not our ML markets.
    # BO2 also has a draw and must not be treated as a two-way series winner.
    if event.get('sport')=='esports' and event.get('bo')==2:return None
    if set(prices)!=expected or len(books)!=1:return None
    # A malformed/swapped pair must not seed the model. Do not combine books.
    if not .9<=sum(1/p for p in prices.values())<=1.3:return None
    return dict(odds=prices,bookmaker=books.pop(),source=source,price_kind='public_displayed',
                event_id=str(event['id']),div=event['div'],kickoff=utc(event['kickoff']).isoformat(),observed_at=utc(now).isoformat())


def complete_odds(event):
    odds=event.get('odds') or {}
    keys=('H','D','A') if event.get('sport','football')=='football' else ('H','A')
    return all(isinstance(odds.get(k),(int,float)) and math.isfinite(odds[k]) and odds[k]>1 for k in keys)


def supplement(event,now,store=None):
    """Fresh public-page fallback only; never recycle author-recorded prices."""
    from . import stavka
    from .stavka import utc
    store=store if store is not None else stavka._runtime
    old=event.get('odds') or {}
    if complete_odds(event) or not store or event.get('state')!='pre':return event
    quote=store.get('quotes',{}).get(f"{event['div']}|{event['id']}")
    if not quote or quote.get('price_kind')!='public_displayed':return event
    age=utc(now)-utc(quote['observed_at'])
    if not pd.Timedelta(0)<=age<=pd.Timedelta(minutes=25) or utc(event['kickoff'])<=utc(now)+pd.Timedelta(minutes=5):return event
    if abs((utc(quote['kickoff'])-utc(event['kickoff'])).total_seconds())>300:return event
    odds={**old,**quote['odds'],'src':quote['bookmaker'],
          'source_url':quote['source'],'observed_at':quote['observed_at'],'price_kind':'public_displayed'}
    return {**event,'odds':odds}


def ensure(event,now,store=None,session=None):
    """Fetch a verified match page only when live prices are missing; five-minute backoff."""
    from . import stavka
    store=store if store is not None else stavka._runtime
    if event.get('state')!='pre' or stavka.utc(event['kickoff'])<=stavka.utc(now)+pd.Timedelta(minutes=5):return event
    if store is None:
        try:store=stavka.load();stavka._runtime=store
        except (OSError,ValueError):return event
    filled=supplement(event,now,store)
    if complete_odds(filled):return filled
    key=f"{event['div']}|{event['id']}";attempts=store.setdefault('quote_attempts',{})
    if attempts.get(key) and stavka.utc(now)-stavka.utc(attempts[key])<pd.Timedelta(minutes=5):return filled
    attempts[key]=stavka.utc(now).isoformat()
    try:
        url=store.get('match_pages',{}).get(key)
        if not url:
            known=[t['source'] for t in store.get('tips',{}).values() if str(t.get('event_id'))==str(event['id']) and t.get('div')==event['div']]
            url=known[0] if known else None
        client=session or __import__('requests')
        if not url:
            slug=next((slug for slug,sport in stavka.SOURCE_SPORTS.items() if sport==event.get('sport','football') and (sport!='esports' or slug=={'CS2':'csgo','DOTA':'dota2'}.get(event['div']))),None)
            if not slug:return filled
            markup=stavka.fetch(stavka.BASE+'/matches/'+slug,client)
            soup=BeautifulSoup(markup,'html.parser')
            matches=[stavka.public_url(a['href']) for a in soup.select('a[href*="/matches/"]') if stavka.event_for_url(a['href'],[event])]
            url=next(iter(dict.fromkeys(matches)),None)
        if not url:return filled
        url=stavka.public_url(url)
        markup=stavka.fetch(url,client)
        quote=parse_quotes(markup,url,event,now)
        if quote:
            store.setdefault('quotes',{})[key]=quote;store.setdefault('match_pages',{})[key]=url
        store.setdefault('quote_status',{})[key]={'at':stavka.utc(now).isoformat(),'status':'fresh' if quote else 'no_supported_header'}
    except Exception as exc:
        store.setdefault('quote_status',{})[key]={'at':stavka.utc(now).isoformat(),'status':'unavailable','error':type(exc).__name__}
    finally:stavka.save(store)
    return supplement(event,now,store)
