"""Private aggregate report. Raw visitor IDs and push tokens are never exported."""
import json
import html
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

    def table(rows):
        return '<table><tr><th>Источник / материал</th><th>Посещения по дням</th><th>Уведомления</th><th>Поделиться</th></tr>'+''.join('<tr><td>'+html.escape(k)+'</td><td>'+str(v['visitor_days'])+'</td><td>'+str(v.get('follow',0))+'</td><td>'+str(v.get('share',0))+'</td></tr>' for k,v in rows.items())+'</table>'
    content='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Аудитория АИ СТАВИТ</title><style>body{background:#0b1025;color:#eef2ff;max-width:1000px;margin:32px auto;padding:20px;font:17px/1.6 system-ui}h1{color:#ffc400}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:left;border-bottom:1px solid #35405d;overflow-wrap:anywhere}</style><h1>Аудитория за 7 дней</h1>'
    if data.get('status')=='ok':
        content+='<p>Уникальных посетителей: <b>'+str(data['unique_visitors'])+'</b> · Вернулись в другой день: <b>'+str(data['returning_visitors'])+'</b></p><h2>Источники</h2>'+table(data['sources'])+'<h2>Материалы</h2>'+table(data['content'])+'<p>'+html.escape(data['note'])+'</p>'
    else:content+='<p>Данные недоступны. Это не означает нулевую посещаемость.</p>'
    out.with_suffix('.html').write_text(content+'</html>',encoding='utf-8')
