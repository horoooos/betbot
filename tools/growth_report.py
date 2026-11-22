"""Private aggregate report. Raw visitor IDs and push tokens are never exported."""
import json
import sys
from pathlib import Path
import pandas as pd
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from betbot import push,growth

def report():
    token=push._token() if push.enabled() else None
    if not token:return {'status':'unavailable','reason':'Firebase authorization unavailable'}
    rows={};now=pd.Timestamp.now(tz='UTC')
    for ago in range(7):
        day=(now-pd.Timedelta(days=ago)).strftime('%Y-%m-%d')
        try:r=requests.get(push.DB+'/visits/'+day+'.json',params={'access_token':token},timeout=20)
        except requests.RequestException:raise RuntimeError('Analytics unavailable; credentials hidden') from None
        if not r.ok:raise RuntimeError('Analytics read unavailable; credentials hidden')
        rows[day]=r.json() or {}
    return {'status':'ok','at':now.isoformat(),'period_days':7,**growth.summarize_visits(rows)}

if __name__=='__main__':
    out=Path('work/growth-report.json');out.parent.mkdir(exist_ok=True)
    data=report();out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(data,ensure_ascii=False))
