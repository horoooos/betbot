"""Review scheduling and observable reasons; does not loosen betting criteria."""
import math
import pandas as pd

def due(event, previous, now, lead):
    kick=pd.Timestamp(event['kickoff'])
    if event.get('state')!='pre' or not now<kick<=now+lead or kick-now<=pd.Timedelta(minutes=5):return False
    if not previous:return True
    if previous.get('msg_id') or previous.get('status') not in ('skipped','waiting_data'):return False
    return now.timestamp()>=float(previous.get('retry_at') or 0)

def reason(tip):
    if not tip:return 'no_supported_market'
    if tip.get('est'):return 'no_real_odds'
    try:p,o=float(tip['p']),float(tip['odds'])
    except (KeyError,TypeError,ValueError):return 'invalid_probability_or_odds'
    if not math.isfinite(p) or not math.isfinite(o) or not 0<p<1 or o<=1:return 'invalid_probability_or_odds'
    return 'edge_below_minimum'

def record(state,event,why,tip=None):
    now=pd.Timestamp.now(tz='UTC');key=f"{event.get('sport','football')}|{event.get('div','')}|{event.get('id','')}"
    item={'reason':why,'checked_at':now.isoformat(),'kickoff':str(event.get('kickoff','')),
          'sport':event.get('sport','football'),'id':str(event.get('id','')),
          'home':(event.get('home') or {}).get('ru') or (event.get('home') or {}).get('name',''),
          'away':(event.get('away') or {}).get('ru') or (event.get('away') or {}).get('name','')}
    if tip:
        item['market']=tip.get('label') or tip.get('key')
        try:
            p,o=float(tip['p']),float(tip['odds'])
            if math.isfinite(p) and math.isfinite(o):item.update(probability=p,odds=o,edge=round(p*o-1,5),estimated=bool(tip.get('est')))
        except (KeyError,TypeError,ValueError):pass
    rows=state.setdefault('forecast_decisions',{});rows[key]=item
    for stale in sorted(rows,key=lambda k:rows[k].get('checked_at',''))[:-500]:del rows[stale]
    return item

def waiting(event,state,now):
    key=f"{event.get('sport','football')}|{event.get('div','')}|{event.get('id','')}"
    return {'status':'waiting_data','kickoff':event['kickoff'],'sport':event.get('sport','football'),
            'div':event.get('div'),'reason':state.get('forecast_decisions',{}).get(key,{}).get('reason','analysis_unavailable'),
            'retry_at':now.timestamp()+600}
