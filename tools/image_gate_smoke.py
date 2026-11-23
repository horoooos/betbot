"""Read-only real cover validation; never publishes a test post."""
import sys,json,html,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from betbot.vk_rss import public_image_ready
out=Path('work/image-proof');out.mkdir(parents=True,exist_ok=True)
r=requests.get('https://horoooos.github.io/betbot/rss-vk.xml',params={'check':int(time.time())},timeout=20);r.raise_for_status()
items=ET.fromstring(r.content).findall('channel/item')[:5]
pairs=[(i.findtext('title'),i.find('enclosure').get('url')) for i in items if i.find('enclosure') is not None]
with ThreadPoolExecutor(max_workers=3) as workers:checks=list(workers.map(lambda x:{'title':x[0],'photo':x[1],'valid':public_image_ready(x[1])},pairs))
missing='https://horoooos.github.io/betbot/rss-images/image-gate-missing-cover.jpg'
report={'covers':checks,'missing_cover_rejected':not public_image_ready(missing)}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['missing_cover_rejected']
assert any(c['valid'] for c in checks),'No real public cover could be validated'
c=next(c for c in checks if c['valid'])
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#090d20;color:#f4f5ff;font:18px/1.6 system-ui;max-width:850px;margin:36px auto;padding:24px}img{width:100%;border-radius:16px}.ok{color:#28cf82}article{padding:24px;background:#151d3b;border-radius:20px}</style><h1>Проверка обложки новости</h1><article><img src="'+html.escape(c['photo'],quote=True)+'"><h2>'+html.escape(c['title'])+'</h2><p class="ok">✓ Изображение скачано и полностью открыто</p><p class="ok">✓ Отсутствующая обложка отклонена</p><p>Без подтверждённой картинки новость не передаётся в RSS.</p></article>',encoding='utf-8')
print('Decoded real covers:',sum(c['valid'] for c in checks),'of',len(checks),'missing cover rejected:',report['missing_cover_rejected'])
