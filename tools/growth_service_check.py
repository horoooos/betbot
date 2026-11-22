"""Probe existing client permissions with disposable non-device records only."""
import json
import sys
import time
import uuid
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from betbot import push
token=push._token() if push.enabled() else None
if not token:raise RuntimeError('Backend Firebase access unavailable')
key='growth-qa-'+uuid.uuid4().hex;day=time.strftime('%Y-%m-%d',time.gmtime());report={}
paths=[f'push/{key}',f'visits/{day}/{key}']
try:
    row={'t':'not-a-real-device-token','ts':int(time.time()*1000),'interests':{'topics':{'qa-only-never-match':True},'events':{'news':True}}}
    r=requests.put(push.DB+'/'+paths[0]+'.json',json=row,timeout=20)
    report['anonymous_interest_write']=r.ok
    if not r.ok:raise RuntimeError('Client interest writes rejected by existing database rules')
    r=requests.get(push.DB+'/'+paths[0]+'.json',params={'access_token':token},timeout=20);r.raise_for_status()
    assert r.json()['interests']==row['interests'];report['backend_interest_read']=True
    r=requests.put(push.DB+'/'+paths[1]+'.json',json={'r':'qa','t':int(time.time()*1000),'a':{'follow':1}},timeout=20);r.raise_for_status()
    r=requests.patch(push.DB+'/'+paths[1]+'/a.json',json={'follow':{'.sv':{'increment':1}}},timeout=20);r.raise_for_status()
    r=requests.get(push.DB+'/'+paths[1]+'.json',params={'access_token':token},timeout=20);r.raise_for_status()
    assert r.json()['a']['follow']==2;report['client_event_increment']=True
finally:
    cleaned=True
    for path in paths:
        r=requests.delete(push.DB+'/'+path+'.json',params={'access_token':token},timeout=20);cleaned=cleaned and r.ok
    report['test_records_removed']=cleaned
    out=Path('work/growth-preview/service-report.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
