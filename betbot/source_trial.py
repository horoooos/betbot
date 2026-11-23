"""Expiring paper-bank fallback from external picks. Never places bookmaker bets."""
import json,math
from html import escape
from pathlib import Path
import pandas as pd
from . import stavka
CONFIG=Path(__file__).resolve().parents[1]/'data/external_trial.json'


def config(now):
    try:
        c=json.loads(CONFIG.read_text(encoding='utf-8'))
        if c.get('enabled') is not True or not stavka.utc(c['starts_at'])<=stavka.utc(now)<stavka.utc(c['expires_at']):return None
        if not 0<float(c['stake_pct'])<=1 or not 1<=int(c['max_open'])<=6:return None
        return c
    except (OSError,ValueError,KeyError,TypeError):return None


def select(event,probs,real,labels,state,now,root=None):
    c=config(now)
    if not c or event.get('state')!='pre' or stavka.utc(event['kickoff'])<=stavka.utc(now)+pd.Timedelta(minutes=5):return None
    stamp=(event.get('odds') or {}).get('observed_at')
    if stamp:
        try:
            if not pd.Timedelta(0)<=stavka.utc(now)-stavka.utc(stamp)<=pd.Timedelta(minutes=25):return None
        except (ValueError,TypeError):return None
    ledger=state.setdefault('source_trial',{}).setdefault('picks',{})
    sid=f"{event.get('sport','football')}|{event['div']}|{event['id']}"
    if sid in ledger or sum(v.get('status')=='open' for v in ledger.values())>=int(c['max_open']):return None
    root=stavka._runtime if root is None else root
    if not root:return None
    rows=[]
    for pool in [root,root.get('external_sources',{})]:
        for tip in pool.get('tips',{}).values():
            if str(tip.get('event_id'))!=str(event['id']) or tip.get('div')!=event['div']:continue
            if tip.get('sport','football')!=event.get('sport','football'):continue
            try:
                if abs((stavka.utc(tip['kickoff'])-stavka.utc(event['kickoff'])).total_seconds())>300:continue
                if not stavka.utc(tip['published_at'])<=stavka.utc(tip['observed_at'])<=stavka.utc(now):continue
                if stavka.utc(tip['published_at'])>=stavka.utc(event['kickoff']):continue
            except (KeyError,ValueError,TypeError):continue
            k=tip.get('key');price=real.get(k);p=probs.get(k)
            if k not in labels or not isinstance(price,(int,float)) or not math.isfinite(price) or not 1.4<=price<=4.0:continue
            if not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<p<1:continue
            # A named recommendation must still have that exact currently modeled market.
            rows.append(tip)
    # One author's first pick per match; don't count repeated/syndicated copies as votes.
    authors={}
    for t in sorted(rows,key=lambda t:t['published_at']):authors.setdefault(t['author'],t)
    groups={}
    for t in authors.values():groups.setdefault(t['key'],[]).append(t)
    candidates=[]
    for k,tips in groups.items():
        editorial=any(t.get('provider') in ('legalbet','livesport','metaratings','rb','vseprosport') for t in tips)
        if len(tips)<2 and not editorial:continue
        # Rank by distinct support, then number of publishers; don't invent expert probabilities.
        providers={t.get('provider','public_predictions') for t in tips}
        candidates.append((len(tips),len(providers),k,tips))
    if not candidates:return None
    _,_,k,tips=max(candidates,key=lambda v:(v[0],v[1],v[2]))
    p=float(probs[k]);price=round(float(real[k]),2)
    return dict(key=k,label=labels[k],p=round(p,4),odds=price,est=False,stake=float(c['stake_pct']),
        strategy='external_trial',trial_expires_at=c['expires_at'],probability_origin='baseline_model',
        model_edge=round(p*price-1,5),source_count=len(tips),
        source_refs=[{f:t.get(f) for f in ('author','provider','source','published_at','observed_at','odds','price_kind')} for t in tips])


def published(state,event,tip,mid,now):
    if tip.get('strategy')!='external_trial':return
    sid=f"{event.get('sport','football')}|{event['div']}|{event['id']}"
    state.setdefault('source_trial',{}).setdefault('picks',{}).setdefault(sid,
        {'status':'open','id':str(event['id']),'sport':event.get('sport','football'),'div':event['div'],
         'kickoff':event['kickoff'],'published_at':stavka.utc(now).isoformat(),'msg_id':mid,'tip':tip})


def settle(state,results,now):
    picks=state.get('source_trial',{}).get('picks',{})
    if results is None or results.empty:return
    for pick in picks.values():
        if pick.get('status')!='open' or stavka.utc(pick['kickoff'])>=stavka.utc(now):continue
        rows=results[results['id'].astype(str).str.replace(r'\.0$','',regex=True)==pick['id']]
        if 'sport' in rows:rows=rows[rows['sport'].fillna('football')==pick['sport']]
        rows=rows[rows['main_key']==pick['tip']['key']]
        if rows.empty:continue
        row=rows.iloc[-1];hit=str(row.get('main_hit')).lower()
        if hit not in ('true','false','1','0','1.0','0.0'):continue
        won=hit in ('true','1','1.0');price=pick['tip']['odds'];stake=pick['tip']['stake']
        pick.update(status='settled',settled_at=stavka.utc(now).isoformat(),hit=won,
                    profit_pct=round(stake*(price-1) if won else -stake,5))


def note(tip):
    if tip.get('strategy')!='external_trial':return ''
    return (f"🧪 <b>Временный прогноз по внешним мнениям</b> · {tip['source_count']} мн.\n"
            "Проценты — оценка модели. Перевес не подтверждён; результат учитывается для обучения.")


def explanation(tip):
    if tip.get('strategy')!='external_trial':return ''
    refs=list(dict.fromkeys(t.get('source') for t in tip['source_refs'] if t.get('source')))[:3]
    links=' · '.join(f'<a href="{escape(url,quote=True)}">Источник {i}</a>' for i,url in enumerate(refs,1))
    return note(tip)+'\n\n'+links+'\n\n'+f"Учёт: {tip['stake']:g}% виртуального банка. Коэффициент на момент проверки: {tip['odds']:.2f}."
