"""Independent temporal calibration for hockey, basketball, tennis, CS2 and Dota."""
import copy
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import sports
from .stavka import MIN_MATCHES, utc


def group(event):
    sport=event.get('sport','football')
    return 'esports:'+event['div'] if sport=='esports' else sport


def winner_keys(event):
    sport=event['sport']
    if sport=='hockey':return ('HK_ML_H','HK_ML_A')
    if sport=='basketball':return ('BB_ML_H','BB_ML_A')
    if sport=='tennis':return ('TN_W1','TN_W2')
    return ('ES_W1','ES_X','ES_W2') if event.get('bo')==2 else ('ES_W1','ES_W2')


def opinions(store,event,keys,at):
    authors={}
    for t in sorted(store['tips'].values(),key=lambda t:t['published_at']):
        if t.get('sport','football')!=event['sport'] or t['div']!=event['div'] or t['event_id']!=str(event['id']) or t['key'] not in keys:
            continue
        if utc(t['observed_at'])>utc(at) or utc(t['published_at'])>=utc(event['kickoff']) or abs((utc(t['kickoff'])-utc(event['kickoff'])).total_seconds())>300:
            continue
        authors.setdefault(t['author'],t)
    return list(authors.values()) if len(authors)>=3 else []


def author_weights(store,category,at):
    stats={}
    for s in store['samples'].values():
        if s.get('group')!=category or not s.get('settled_at') or s.get('void') or utc(s['settled_at'])>=utc(at):continue
        for t in s['opinions']:
            count,edge=stats.get(t['author'],(0,0.0))
            hit=t['key']==s['keys'][s['outcome']]
            stats[t['author']]=(count+1,edge+int(hit)-1/t['odds'])
    return {a:math.exp(float(np.clip(edge/(n+20),-.3,.3))) for a,(n,edge) in stats.items()}


def adjust(event,analysis,now,store=None):
    from . import stavka
    store=store if store is not None else stavka._runtime
    info=dict(status='insufficient_opinions',weight=0.0)
    if store is None or event.get('state')!='pre' or utc(event['kickoff'])<=utc(now)+pd.Timedelta(minutes=5):return analysis,info
    keys=winner_keys(event)
    if not all(k in analysis['probs'] for k in keys):return analysis,info
    tips=opinions(store,event,keys,now)
    if not tips:return analysis,info
    category=group(event)
    weights=author_weights(store,category,now)
    p=np.array([analysis['probs'][k] for k in keys],float);p/=p.sum()
    counts=np.array([sum(weights.get(t['author'],1.0) for t in tips if t['key']==k) for k in keys])
    q=(counts+5*p)/(counts.sum()+5)
    sid=f'{event["div"]}|{event["id"]}'
    store['samples'].setdefault(sid,dict(sport=event['sport'],group=category,event_id=str(event['id']),div=event['div'],
        kickoff=utc(event['kickoff']).isoformat(),captured_at=utc(now).isoformat(),keys=list(keys),baseline=p.tolist(),
        consensus=q.tolist(),opinions=[{k:t[k] for k in ('author','key','odds','source','observed_at')} for t in tips]))
    model=store.get('sport_models',{}).get(category,{'status':'collecting','weight':0.0})
    weight=float(model.get('weight',0)) if model.get('status')=='active' else 0.0
    if model.get('trained_at') and utc(model['trained_at'])>utc(now):weight=0.0
    if not 0<=weight<=.5:raise ValueError('Invalid external signal weight')
    result=analysis
    if weight:
        target=(1-weight)*p+weight*q
        if len(keys)==3:  # BO2: keep all three mutually exclusive series outcomes.
            result=copy.deepcopy(analysis)
            result['probs'].update(dict(zip(keys,map(float,target))))
            result['bar']=tuple(map(float,target))
        else:
            odds={**event.get('odds',{}),'H':1/target[0],'A':1/target[1]}
            if event['sport']=='basketball':
                sm=sports.SIGMA.get(event['div'],(12.0,17.0))[0]
                odds['spread']=-sm*norm.ppf(target[0])
            result=sports.analyse({**event,'odds':odds},{})
            if result is None:raise ValueError('Could not rebuild sports probabilities')
            if event['sport']=='basketball' and 'BB_SPR_H' in analysis['probs']:
                sp=float(event['odds']['spread']);mu=result['model']['mu']
                result['probs']['BB_SPR_H']=float(norm.cdf((mu+sp)/sm))
                result['probs']['BB_SPR_A']=1-result['probs']['BB_SPR_H']
            # Model inputs change; published bookmaker prices/lines never do.
            result['real']=copy.deepcopy(analysis['real'])
            result['labels']=copy.deepcopy(analysis['labels'])
    stavka.save(store)
    return result,dict(status=model['status'],weight=weight,authors=len(tips),group=category,snapshot=sid,source='https://stavka.tv')


def settle(store,events,now):
    by_id={(e.get('sport','football'),e['div'],str(e['id'])):e for e in events}
    changed=0
    for s in store['samples'].values():
        if s.get('sport','football')=='football' or s.get('settled_at'):continue
        e=by_id.get((s['sport'],s['div'],s['event_id']))
        if not e or not e.get('completed') or utc(e['kickoff'])>=utc(now):continue
        if abs((utc(s['kickoff'])-utc(e['kickoff'])).total_seconds())>300:continue
        f=sports.final(e)
        if not f:continue
        if f.get('void'):
            s.update(void=True,settled_at=utc(now).isoformat());changed+=1;continue
        if len(s['keys'])==3:
            outcome=0 if f['hs']>f['as'] else 1 if f['hs']==f['as'] else 2
        else:
            if f['hs']==f['as']:continue
            outcome=0 if f['home_won'] else 1
        s.update(outcome=outcome,settled_at=utc(now).isoformat(),score=[f['hs'],f['as']]);changed+=1
    return changed


def train(store,now):
    models={}
    for category in ('hockey','basketball','tennis','esports:CS2','esports:DOTA'):
        rows=[s for s in store['samples'].values() if s.get('group')==category and s.get('settled_at')
              and not s.get('void') and utc(s['settled_at'])<utc(now)]
        rows=sorted(rows,key=lambda s:s['kickoff'])[-3000:]
        model=dict(status='collecting',weight=0.0,settled_matches=len(rows),required_matches=MIN_MATCHES,trained_at=utc(now).isoformat())
        if len(rows)>=MIN_MATCHES:
            cutoff=utc(rows[int(len(rows)*.8)]['kickoff']).normalize()
            early=[s for s in rows if utc(s['kickoff'])<cutoff and utc(s['settled_at'])<cutoff]
            late=[s for s in rows if utc(s['kickoff'])>=cutoff]
            if len(early)>=60 and len(late)>=20:
                def loss(data,w):
                    return float(np.mean([-math.log(max((1-w)*s['baseline'][s['outcome']]+w*s['consensus'][s['outcome']],1e-12)) for s in data]))
                candidate=min((loss(early,float(w)),float(w)) for w in np.linspace(0,.5,11))[1]
                baseline=loss(late,0);control=loss(late,candidate)
                weight=candidate if control<baseline-.001 else 0.0
                model.update(status='active' if weight else 'baseline_better',weight=weight,candidate_weight=candidate,
                    train_matches=len(early),validation_matches=len(late),validation_from=cutoff.isoformat(),
                    validation_logloss=control if weight else baseline,validation_baseline_logloss=baseline)
            else:model['status']='insufficient_temporal_split'
        models[category]=model
    store['sport_models']=models
    return models
