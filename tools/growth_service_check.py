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
rules=requests.get(push.DB+'/.settings/rules.json',params={'access_token':token},timeout=20)
if rules.ok:
    def schema(node):
        if not isinstance(node,dict):return node
        return {k:schema(v) for k,v in node.items() if k not in ('.read','.write')}
    report['validation']={k:schema(rules.json().get('rules',{}).get(k,{})) for k in ['push','visits']}

try:
    row={'t':'not-a-real-device-token','ts':int(time.time()*1000),'interests':{'topics':{'qa-only-never-match':True},'events':{'news':True}}}
    r=requests.put(push.DB+'/'+paths[0]+'.json',json=row,timeout=20)
    report['anonymous_interest_write']=r.ok
    if not r.ok:raise RuntimeError('Client interest writes rejected by existing database rules')
    r=requests.get(push.DB+'/'+paths[0]+'.json',params={'access_token':token},timeout=20)
    if not r.ok:raise RuntimeError('Firebase service check rejected: '+str(r.status_code)+' '+r.text[:120])
    assert r.json()['interests']==row['interests'];report['backend_interest_read']=True
    r=requests.put(push.DB+'/'+paths[1]+'.json',json={'r':'qa','d':'Компьютер','p':'growth-qa','t':int(time.time()*1000),'a':{'follow':1}},timeout=20)
    if not r.ok:raise RuntimeError('Firebase service check rejected: '+str(r.status_code)+' '+r.text[:120])
    row['interests']={'topics':{},'events':{'news':False}}
    r=requests.patch(push.DB+'/'+paths[0]+'.json',json={'interests':row['interests']},timeout=20)
    if not r.ok:raise RuntimeError('Firebase service check rejected: '+str(r.status_code)+' '+r.text[:120])
    r=requests.get(push.DB+'/'+paths[1]+'.json',params={'access_token':token},timeout=20)
    if not r.ok:raise RuntimeError('Firebase service check rejected: '+str(r.status_code)+' '+r.text[:120])
    assert r.json()['a']['follow']==1;report['client_event_write']=True
    r=requests.get(push.DB+'/'+paths[0]+'.json',params={'access_token':token},timeout=20)
    if not r.ok:raise RuntimeError('Subscription update read unavailable')
    assert not r.json()['interests'].get('topics');report['client_interest_unsubscribe']=True
except requests.RequestException:
    raise RuntimeError("Firebase service check unavailable; credentials hidden") from None
finally:
    cleaned=True
    for path in paths:
        try:r=requests.delete(push.DB+'/'+path+'.json',params={'access_token':token},timeout=20);cleaned=cleaned and r.ok
        except requests.RequestException:cleaned=False
    report['test_records_removed']=cleaned
    out=Path('work/growth-preview/service-report.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
