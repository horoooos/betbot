"""Read-only esports delivery diagnosis. Never publish or print credentials."""
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests
from betbot import esports,sports,oddspapi

get=requests.get
def observed(url,*args,**kwargs):
    r=get(url,*args,**kwargs)
    if url.startswith(esports.API):
        print('PANDA_HTTP',urlsplit(url).path,r.status_code,flush=True)
    return r
requests.get=observed
print('TOKEN_CONFIGURED',esports.enabled(),flush=True)
print('CACHE_FILES',{p.name:p.stat().st_size for p in esports.CACHE.glob('*.json')},flush=True)
events=esports.fetch()
history=esports.history(refresh=False)
ratings=sports.elo(history)
print('EVENTS',dict(Counter((e['div'],e['state']) for e in events)),flush=True)
print('HISTORY',len(history),'DECISIVE',sum(m['home']['winner']!=m['away']['winner'] for m in history),'RATINGS',len(ratings),flush=True)
now=pd.Timestamp.now(tz='UTC')
for e in events:
    if e['state']!='pre' or pd.Timestamp(e['kickoff'])>now+pd.Timedelta(days=2):continue
    a=sports.analyse(e,ratings)
    print('MATCH',json.dumps(dict(div=e['div'],id=e['id'],home=e['home']['name'],away=e['away']['name'],kickoff=e['kickoff'],
        rating_home=ratings.get(e['home']['id']),rating_away=ratings.get(e['away']['id']),analysis=bool(a),
        cached_odds=bool(oddspapi.lookup(e))),ensure_ascii=False),flush=True)
