"""Build the prediction pages in isolation; never sends posts."""
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from unittest.mock import patch
from betbot import pages,source_trial as tr
out=Path('work/fallback-site');out.mkdir(parents=True,exist_ok=True)
stores={}
for f in ('matches.json','other.json'):stores.update(json.loads(Path('data',f).read_text(encoding='utf-8')))
tr.remap(stores)
posts={int(k):v for k,v in json.loads(Path('data/channel.json').read_text(encoding='utf-8'))['posts'].items()}
res=pd.read_csv('data/results.csv');now=pd.Timestamp.now(tz='Europe/Moscow')
ms=pages._matches(stores,res,posts,now)
selected=[m for m in ms if m.get('selection_mode')=='external_trial']
assert selected,'No source forecasts in the current site data'
with patch.object(pages,'DOCS',out):
    (out/'predictions').mkdir(exist_ok=True)
    (out/'predictions/index.html').write_text(pages._pred_index(ms,now),encoding='utf-8')
    for m in selected:
        (out/m['url']).write_text(pages._match_page(m,posts,ms),encoding='utf-8')
        for word in ('Временный прогноз','временный режим',' · эксперимент'):
            assert word not in (out/m['url']).read_text(encoding='utf-8'),word
for name in ('site.css','fb.js'):shutil.copy2(Path('docs')/name,out/name)
report=[{'id':m['id'],'home':m['home'],'away':m['away'],'tip':m['tip'],'odds':m['odds'],'url':m['url'],'message_id':m['msg']} for m in selected]
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Source forecasts rendered:',len(report))
