"""Point-in-time STAVKA TV signals for the football score model.

Read public HTML only, keep structured facts (no articles/images), freeze inputs
before kickoff, and learn a bounded weight with chronological validation.
"""
import hashlib
import json
import math
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from . import markets as mk, names

BASE = 'https://stavka.tv'
PATH = Path(__file__).resolve().parent.parent / 'data/stavka_learning.json'
VERSION = 1
MIN_MATCHES = 100
MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
_runtime = None
SOURCE_SPORTS={'soccer':'football','ice-hockey':'hockey','basketball':'basketball','tennis':'tennis','csgo':'esports','dota2':'esports'}


def utc(value):
    t = pd.Timestamp(value)
    if t.tz is None:
        raise ValueError('Timestamp must include timezone')
    return t.tz_convert('UTC')


def market_key(label, sport='football'):
    """Only exact supported full-time football markets; never guess a line."""
    label = re.sub(r'\s+', ' ', label.upper().replace('Ё', 'Е')).strip(' .')
    if sport != 'football':
        if sport=='hockey':
            mapping={'ПОБЕДА 1':'HK_H','НИЧЬЯ':'HK_D','ПОБЕДА 2':'HK_A',
                     'ПОБЕДА 1 (С УЧЕТОМ ОТ И БУЛЛИТОВ)':'HK_ML_H','ПОБЕДА 2 (С УЧЕТОМ ОТ И БУЛЛИТОВ)':'HK_ML_A'}
        else:
            prefix={'basketball':'BB_ML_','tennis':'TN_W','esports':'ES_W'}[sport]
            sides=('H','A') if sport=='basketball' else ('1','2')
            mapping={f'ПОБЕДА {i}':prefix+side for i,side in zip((1,2),sides)}
            if sport=='esports':mapping['НИЧЬЯ']='ES_X'
            if sport=='basketball':
                mapping.update({f'ПОБЕДА {i} (С УЧЕТОМ ОТ)':prefix+side for i,side in zip((1,2),sides)})
        return mapping.get(label)
    simple = {'ПОБЕДА 1': 'H', 'ПОБЕДА 2': 'A', 'НИЧЬЯ': 'D',
              'ОБЕ ЗАБЬЮТ (ДА)': 'BTTS_Y', 'ОБЕ ЗАБЬЮТ (НЕТ)': 'BTTS_N',
              'ДВОЙНОЙ ШАНС 1X': '1X', 'ДВОЙНОЙ ШАНС X2': 'X2', 'ДВОЙНОЙ ШАНС 12': '12'}
    if label in simple:
        return simple[label]
    m = re.fullmatch(r'ТОТАЛ (БОЛЬШЕ|МЕНЬШЕ) \(([1-4][.,]5)\)', label)
    if m:
        return ('O' if m[1] == 'БОЛЬШЕ' else 'U') + m[2].replace('.', '').replace(',', '')
    return None


def public_url(url):
    p = urlsplit(urljoin(BASE, url))
    if p.scheme != 'https' or p.netloc != 'stavka.tv' or p.query:
        raise ValueError('Only canonical public HTML URLs are supported')
    sports='|'.join(SOURCE_SPORTS)
    if p.path!='/predictions' and not re.fullmatch(r'/(?:predictions|matches)/('+sports+r')',p.path) and not re.fullmatch(r'/matches/('+sports+r')/\d{2}-\d{2}-\d{4}-[a-z0-9-]+', p.path):
        raise ValueError('Unsupported source path')
    return BASE + p.path


def published_time(text, now):
    """Unknown/ambiguous timestamps are excluded, not assigned today's date."""
    text = text.lower().strip()
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if not m:
        return None
    local = utc(now).tz_convert('Europe/Moscow')
    if text.startswith('сегодня'):
        day = local.normalize()
    elif text.startswith('вчера'):
        day = local.normalize() - pd.Timedelta(days=1)
    else:
        d = re.search(r'(\d{1,2})\s+([а-я]+)(?:\s+(20\d{2}))?', text)
        if not d or d[2][:3] not in MONTHS:
            return None
        year = int(d[3]) if d[3] else local.year
        day = pd.Timestamp(year=year, month=MONTHS.index(d[2][:3])+1, day=int(d[1]), tz='Europe/Moscow')
        if not d[3] and day > local + pd.Timedelta(days=1):
            day -= pd.DateOffset(years=1)
    return (day + pd.Timedelta(hours=int(m[1]), minutes=int(m[2]))).tz_convert('UTC')


def parse_predictions(html, now):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for card in soup.select('.PredictionsItem'):
        def text(selector):
            e = card.select_one(selector)
            return e.get_text(' ', strip=True) if e else ''
        try:
            event = card.select_one('a.PredictionsItemEvent')
            author = card.select_one('a.predictor-link')
            if not event or not author:
                continue
            source = public_url(event['href'])
            source_sport=urlsplit(source).path.split('/')[2]
            sport=SOURCE_SPORTS[source_sport]
            key = market_key(text('.outcome'),sport)
            published = published_time(text('.PredictionsItemHeader .date'), now)
            if not key or published is None or published > utc(now) + pd.Timedelta(minutes=1):
                continue
            odds = float(text('.Rate').replace(',', '.'))
            if not 1.01 < odds <= 100:
                continue
            slug_day = re.search(r'/matches/[^/]+/(\d{2}-\d{2}-\d{4})-', source)[1]
            author_id = author['href'].split('?')[0].rstrip('/')
            if not re.fullmatch(r'/predictors/[a-zA-Z0-9_-]+', author_id):
                continue
            # One opinion per author/event/market; edits cannot replace first facts.
            uid = hashlib.sha256(f'{source}|{author_id}|{key}'.encode()).hexdigest()[:24]
            rows.append(dict(id=uid, source=source, author=author_id, key=key, odds=odds,
                             sport=sport,discipline={'csgo':'CS2','dota2':'DOTA'}.get(source_sport),
                             home=text('.team--home'), away=text('.team--away'),
                             day=pd.to_datetime(slug_day,format='%d-%m-%Y').strftime('%Y-%m-%d'),
                             published_at=published.isoformat(), observed_at=utc(now).isoformat()))
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return rows


def normalized(team):
    return names.norm(team).replace('сборная ', '').replace('фк ', '')


def team_aliases(team):
    aliases={normalized(team.get(k,'')) for k in ('ru','name')}
    ru=team.get('ru','')
    if ru.startswith('Сборная '):
        country=normalized(ru)
        if country.endswith('ии'):
            aliases.add(country[:-2]+'ия')
        if country.endswith('ы'):
            aliases.add(country[:-1]+'а')
        if country.endswith('а'):
            aliases.add(country[:-1])
        if country.endswith('ши'):
            aliases.add(country[:-1]+'а')
    return aliases-{''}


def match_event(row, events):
    hits = []
    for event in events:
        if event.get('sport','football')!=row.get('sport','football') or (row.get('discipline') and row['discipline']!=event.get('div')):
            continue
        day = utc(event['kickoff']).tz_convert('Europe/Moscow').date()
        if abs((day - pd.Timestamp(row['day']).date()).days) > 1:
            continue
        # Exact known aliases only. Fuzzy club-name collisions can poison training.
        if normalized(row['home']) in team_aliases(event['home']) and normalized(row['away']) in team_aliases(event['away']):
            hits.append(event)
    return hits[0] if len(hits) == 1 else None


def event_for_url(url, events):
    """Conservative English slug discovery; final tips still need name matching."""
    try:
        url = public_url(url)
        source_sport=urlsplit(url).path.split('/')[2]
        day = pd.to_datetime(re.search(r'/matches/[^/]+/(\d{2}-\d{2}-\d{4})-', url)[1],format='%d-%m-%Y').date()
    except (ValueError, TypeError):
        return None
    slug = url.rsplit('/',1)[-1][11:].replace('-', '')
    hits=[]
    for e in events:
        if e.get('sport','football')!=SOURCE_SPORTS[source_sport] or (source_sport in ('csgo','dota2') and e['div']!={'csgo':'CS2','dota2':'DOTA'}[source_sport]):
            continue
        if abs((utc(e['kickoff']).tz_convert('Europe/Moscow').date()-day).days)>1:
            continue
        home, away = [re.sub('[^a-z0-9]', '', normalized(e[s].get('name',''))) for s in ('home','away')]
        if min(len(home),len(away))>=4 and home+away == slug:
            hits.append(e)
    return hits[0] if len(hits)==1 else None


def load():
    if not PATH.exists():
        return dict(version=VERSION, tips={}, samples={}, model={'weight':0.0,'status':'collecting'})
    store=json.loads(PATH.read_text(encoding='utf-8'))
    if store.get('version') != VERSION:
        raise ValueError('Unknown STAVKA learning schema')
    return store


def save(store):
    PATH.parent.mkdir(exist_ok=True)
    temporary=PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(store,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temporary.replace(PATH)


def fetch(url, session):
    r=session.get(public_url(url),timeout=(5,10),headers={'User-Agent':'BetBot/1.0 (public pre-match research)'})
    r.raise_for_status()
    if len(r.content)>4_000_000:
        raise ValueError('Unexpectedly large source page')
    return r.text


def ingest(store, rows, events, now):
    added=0
    for row in rows:
        e=match_event(row,events)
        if not e or e.get('state')!='pre' or utc(e['kickoff']) <= utc(now)+pd.Timedelta(minutes=5):
            continue
        if utc(row['published_at']) >= utc(e['kickoff']):
            continue
        if row['id'] not in store['tips']:
            store['tips'][row['id']]={**row,'event_id':str(e['id']),'div':e['div'],'kickoff':utc(e['kickoff']).isoformat()}
            added+=1
    return added


def collect(store, events, now, session=None):
    session=session or requests
    upcoming=[e for e in events if e.get('state')=='pre' and utc(now)+pd.Timedelta(minutes=5)<utc(e['kickoff'])<=utc(now)+pd.Timedelta(days=2)]
    def read(url):
        try:
            return url,fetch(url,session),None
        except (requests.RequestException,ValueError) as exc:
            return url,None,str(exc)[:160]
    urls0=[BASE+f'/{kind}/{slug}' for slug in SOURCE_SPORTS for kind in ('predictions','matches')]
    rows=[];urls=set();errors=[];parsed_by_sport={};feeds_ok=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url,html,error in pool.map(read,urls0):
            if error:errors.append(error);continue
            soup=BeautifulSoup(html,'html.parser')
            if '/predictions/' in url:
                if not soup.select('.PredictionsItem'):
                    errors.append('Prediction markup missing: '+url);continue
                feeds_ok+=1
                got=parse_predictions(html,now);rows+=got
                parsed_by_sport[url.rsplit('/',1)[-1]]=len(got)
                urls.update(r['source'] for r in got if match_event(r,upcoming))
            else:
                for a in soup.select('a[href*="/matches/"]'):
                    if event_for_url(a['href'],upcoming):urls.add(public_url(a['href']))
        selected=[]
        offsets=store.setdefault('page_offsets',{})
        for slug in SOURCE_SPORTS:
            candidates=sorted(u for u in urls if '/matches/'+slug+'/' in u)
            if candidates:
                offset=int(offsets.get(slug,0))%len(candidates)
                selected.append(candidates[offset]);offsets[slug]=offset+1
        for url,html,error in pool.map(read,selected):
            if error:errors.append(error)
            else:rows+=parse_predictions(html,now)
    if not feeds_ok:
        raise ValueError('No public sport feed could be read: '+'; '.join(errors[:2]))
    count=ingest(store,rows,upcoming,now)
    store['source_status']=dict(last_success=utc(now).isoformat(),parsed=len(rows),added=count,discovered_matches=len(urls),pages=len(selected)+len(urls0),errors=errors,parsed_by_sport=parsed_by_sport)
    return count


def settle(store, events, now):
    """Only observed final regulation-time scores; no backfilled outcomes in features."""
    by_id={(e['div'],str(e['id'])):e for e in events if e.get('sport','football')=='football'}
    changed=0
    for sample in store['samples'].values():
        if sample.get('sport','football')!='football':
            continue
        if sample.get('settled_at'):
            continue
        e=by_id.get((sample['div'],sample['event_id']))
        if not e or not e.get('completed'):
            continue
        if 'FULL_TIME' not in e.get('status','') or any(x in (e.get('detail','').upper()) for x in ('AET','PEN','ET ')):
            continue
        try:
            score=[int(e[s]['score']) for s in ('home','away')]
        except (ValueError,TypeError,KeyError):
            continue
        if min(score)<0 or utc(sample.get('kickoff',e['kickoff']))>=utc(now):
            continue
        sample.update(score=score,settled_at=utc(now).isoformat())
        changed+=1
    return changed


def author_weights(store, at):
    totals={}
    for sample in store['samples'].values():
        if sample.get('sport','football')!='football':
            continue
        if not sample.get('settled_at') or utc(sample['settled_at'])>=utc(at):
            continue
        for tip in sample['opinions']:
            key=(tip['author'],tip['key'])
            count,edge=totals.get(key,(0,0.0))
            residual=float(mk.won(tip['key'],*sample['score']))-1/tip['odds']
            totals[key]=(count+1,edge+residual)
    return {k:math.exp(float(np.clip(edge/(count+20),-.3,.3))) for k,(count,edge) in totals.items()}


def votes_for(store, event, at):
    weights=author_weights(store,at)
    tips=[t for t in store['tips'].values() if t['event_id']==str(event['id']) and t['div']==event['div']
          and utc(t['observed_at'])<=utc(at) and utc(t['published_at'])<utc(event['kickoff'])
          and abs((utc(t['kickoff'])-utc(event['kickoff'])).total_seconds())<=300]
    # A prolific author gets at most one vote per market family, never N votes.
    families=[('H','D','A'),('O25','U25')]
    votes={}
    kept=[]
    for family in families:
        authors={}
        for tip in sorted(tips,key=lambda t:t['published_at']):
            if tip['key'] in family:
                authors.setdefault(tip['author'],tip)
        if len(authors)<3:
            continue
        for t in authors.values():
            votes[t['key']]=votes.get(t['key'],0)+weights.get((t['author'],t['key']),1.0)
            kept.append({k:t[k] for k in ('author','key','odds','source','observed_at')})
    return votes,kept


def adjusted_matrix(lam, votes, weight):
    m=mk.matrix(*lam).copy()
    if not 0<=weight<=.5:
        raise ValueError('Invalid external signal weight')
    x=np.arange(m.shape[0]);i,j=np.meshgrid(x,x,indexing='ij')
    for keys,masks in [(('H','D','A'),(i>j,i==j,i<j)),(('O25','U25'),(i+j>2.5,i+j<2.5))]:
        counts=np.array([votes.get(k,0.0) for k in keys],float)
        if counts.sum()<=0:
            continue
        p=np.array([m[mask].sum() for mask in masks])
        q=(counts+5*p)/(counts.sum()+5)  # shrink small crowds towards the baseline
        target=(1-weight)*p+weight*q
        for mask,old,new in zip(masks,p,target):
            m[mask]*=new/max(old,1e-12)
    return m/m.sum()


def train(store, now):
    samples=[s for s in store['samples'].values() if s.get('sport','football')=='football' and s.get('settled_at') and utc(s['settled_at'])<utc(now)
             and all(0<=g<=mk.MAXG for g in s['score'])]
    samples=sorted(samples,key=lambda s:s['kickoff'])[-3000:]
    model=dict(weight=0.0,status='collecting',settled_matches=len(samples),required_matches=MIN_MATCHES,trained_at=utc(now).isoformat())
    if len(samples)<MIN_MATCHES:
        store['model']=model;return model
    cutoff=utc(samples[int(len(samples)*.8)]['kickoff']).normalize()
    # Require every training outcome to have been available before validation begins.
    training=[s for s in samples if utc(s['kickoff'])<cutoff and utc(s['settled_at'])<cutoff]
    validation=[s for s in samples if utc(s['kickoff'])>=cutoff]
    if len(training)<60 or len(validation)<20:
        model['status']='insufficient_temporal_split';store['model']=model;return model
    def loss(rows,w):
        return float(np.mean([-math.log(max(adjusted_matrix(s['lam'],s['votes'],w)[tuple(s['score'])],1e-12)) for s in rows]))
    grid=[(loss(training,float(w)),float(w)) for w in np.linspace(0,.5,11)]
    candidate=min(grid)[1]
    baseline=loss(validation,0.0);control=loss(validation,candidate)
    chosen=candidate if control<baseline-0.001 else 0.0
    model.update(weight=chosen,status='active' if chosen else 'baseline_better',candidate_weight=candidate,
                 train_matches=len(training),validation_matches=len(validation),validation_from=cutoff.isoformat(),
                 validation_logloss=control if chosen else baseline,validation_baseline_logloss=baseline)
    store['model']=model
    return model


def tick(events, now):
    global _runtime
    store=load()
    changed=settle(store,events,now)
    from . import stavka_sports
    other_changed=stavka_sports.settle(store,events,now)
    last=store.get('last_attempt')
    if not last or utc(now)-utc(last)>=pd.Timedelta(minutes=20):
        store['last_attempt']=utc(now).isoformat()
        try:
            collect(store,events,now)
            store['source_error']=None
        except (requests.RequestException,ValueError) as exc:
            store['source_error']=str(exc)[:240]
    if changed or not store.get('model',{}).get('trained_at'):
        train(store,now)
    if other_changed or not store.get('sport_models'):
        stavka_sports.train(store,now)
    _runtime=store
    save(store)
    return {'model':store['model'],'sport_models':store.get('sport_models',{}),'source':store.get('source_status'),'error':store.get('source_error'),
            'tips':len(store['tips']),'snapshots':len(store['samples'])}


def adjust(event, lam, probs, now):
    """Freeze one baseline per match, then use only a previously validated weight."""
    store=_runtime
    if store is None or event.get('state')!='pre' or utc(now)>=utc(event['kickoff'])-pd.Timedelta(minutes=5):
        return probs, {'status':'no_prematch_context','weight':0.0}
    votes,opinions=votes_for(store,event,now)
    if not votes:
        return probs, {'status':'insufficient_opinions','weight':0.0}
    key=f"{event['div']}|{event['id']}"
    if key not in store['samples']:
        store['samples'][key]=dict(event_id=str(event['id']),div=event['div'],kickoff=utc(event['kickoff']).isoformat(),
            captured_at=utc(now).isoformat(),lam=list(lam),votes=votes,opinions=opinions)
    model=store['model']
    weight=float(model.get('weight',0)) if model.get('status')=='active' else 0.0
    # Never let a model trained later than this forecast affect its probabilities.
    if model.get('trained_at') and utc(model['trained_at'])>utc(now):
        weight=0.0
    result=dict(probs)
    if weight:
        m=adjusted_matrix(lam,votes,weight)
        for k,(_,_,condition) in mk.MARKETS.items():
            result[k]=mk._p(m,condition)
        result['scores']=sorted(((float(m[i,j]),f'{i}:{j}') for i in range(6) for j in range(6)),reverse=True)[:3]
        result['scores']=[(score,p) for p,score in result['scores']]
    save(store)
    return result,dict(status=model['status'],weight=weight,authors=len({t['author'] for t in opinions}),
                       votes=votes,source='https://stavka.tv',snapshot=key)
