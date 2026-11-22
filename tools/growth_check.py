"""Build and inspect growth features using current checkout data, without sending."""
import json
import sys
import shutil
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from betbot import pages,pages_extra,growth,growth_campaigns,news_video

out=Path('work/growth-preview');out.mkdir(parents=True,exist_ok=True)
now=pd.Timestamp.now(tz='UTC')
store={int(k):v for k,v in json.loads(Path('data/channel.json').read_text(encoding='utf-8'))['posts'].items()}
news=pages._news(store)
matches=json.loads(Path('docs/matches.json').read_text(encoding='utf-8'))
for name in ['matches.json','site.css','fb.js','growth.js','favicon.ico','og.png']:
    shutil.copy2(Path('docs')/name,out/name)
# Isolated output; never overwrite live state, forecasts, RSS or production pages.
pages.DOCS=pages_extra.DOCS=out
pages_extra.build_teams([],news,now)
urls=growth.build(news,[],now)
chosen=growth.select_digest(news,now)
if not chosen:raise RuntimeError('No recent news to exercise real-data generation')
frames=news_video.frames(chosen[0]);frames[0].save(out/'news-video-frame.png')
if '--video' in sys.argv:
    clip=news_video.render(chosen[0])
    if not clip:raise RuntimeError('News video failed to render')
    (out/'news-preview.mp4').write_bytes(clip)
report={'at':now.isoformat(),'topics':len(json.loads((out/'topics.json').read_text(encoding='utf-8'))['topics']),
        'teams':len(list((out/'teams').glob('*.html')))-1,'tournaments':sum(u.startswith('tournaments/league-') for u in urls),
        'digest_items':[n['title'] for n in chosen],'video_frames':len(frames),'sent_messages':0}
(out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
