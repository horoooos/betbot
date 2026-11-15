"""Edit the user's two existing forecast cards; never create a new post."""
import json
import os
import re
import sys
from pathlib import Path
import pandas as pd
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from betbot import card,live,pages,sports,telegram,texts


def main():
    stored=json.loads(Path('data/other.json').read_text(encoding='utf-8'))
    channel=json.loads(Path('data/channel.json').read_text(encoding='utf-8'))['posts']
    for key in os.environ['MATCH_KEYS'].split(','):
        key=key.strip()
        if not re.fullmatch(r'(ATP|WTA|CS2|DOTA)\|\d+',key):raise ValueError('Unsupported match key')
        m=stored[key];mid=int(m['msg_id']);post=channel.get(str(mid),{})
        if not all(n['ru'] in pages._plain(post.get('html','')) for n in (m['home'],m['away'])):
            raise ValueError('Stored message does not match the requested fixture')
        center=sports.public_model_label(m.get('center',''));tip=m['main']
        image=card.match_card(sports.league_plain(m['div']),texts.when(pd.Timestamp(m['kickoff'])),m['home'],m['away'],m['bar'],
            tip['label'],center,'АИ СТАВИТ',sport=m['sport'],odds=f"{'≈' if tip.get('est') else ''}{tip['odds']:.2f}")
        caption=telegram.tag(sports.caption(m,texts.when(pd.Timestamp(m['kickoff']))))
        if len(caption)>1024:raise ValueError('Caption would be truncated')
        media=json.dumps(dict(type='photo',media='attach://cover',caption=caption,parse_mode='HTML'),ensure_ascii=False)
        result=telegram._call('editMessageMedia',message_id=mid,media=media,
            reply_markup=telegram._keyboard(live.buttons(m,m['sport'],m['home']['ru'],m['away']['ru'])),files={'cover':('forecast.png',image,'image/png')})
        if result.get('message_id')!=mid or not result.get('photo'):raise ValueError('Photo update not confirmed')
        print('UPDATED_FORECAST',f'https://t.me/aistavvit/{mid}',flush=True)
        for p in channel.values():
            heading=pages._plain(p['html']).split('\n',1)[0]
            own_analysis='ПОЛНЫЙ РАЗБОР:' in heading and all(t['ru'] in heading for t in (m['home'],m['away']))
            if p.get('reply')!=mid and not own_analysis:continue
            text=sports.public_model_label(p['html'])
            if text==p['html']:continue
            text=re.sub(r' rel="[^"]*"','',text)
            telegram._call('editMessageText',message_id=int(p['id']),text=text,parse_mode='HTML',disable_web_page_preview=True)
            print('UPDATED_ANALYSIS',p['id'],flush=True)


if __name__=='__main__':
    try:main()
    except requests.RequestException:raise SystemExit('Network request failed; bot credential hidden') from None
