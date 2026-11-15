"""Read-only live check: no Telegram posts and no changes to learning storage."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from betbot import stavka
from betbot.espn import scoreboard
from betbot.leagues import ALL

now=pd.Timestamp.now(tz='UTC')
events=scoreboard({c:ALL[c][3] for c in ('UNL','FRI','E0','SP1','RUS')},
                  [(now+pd.Timedelta(days=i)).strftime('%Y%m%d') for i in (0,1)])
stored=json.loads(Path('data/matches.json').read_text(encoding='utf-8'))
for e in events:
    old=stored.get(str(e['id']),{})
    for side in ('home','away'):
        e[side]['ru']=old.get(side,{}).get('ru',e[side]['name'])
store=stavka.load()
count=stavka.collect(store,events,now)
print(json.dumps(dict(events=len(events),new_forecasts=count,source=store['source_status'],
                     preview=[{k:t[k] for k in ('source','key','odds','published_at','event_id')} for t in list(store['tips'].values())[-3:]]),ensure_ascii=False,indent=2))
