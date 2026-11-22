"""Owned-channel discovery only: navigation/share buttons and a weekly invitation."""
import json
import os
from urllib.parse import urlencode
import pandas as pd

SITE='https://horoooos.github.io/betbot/'

def news_buttons(source_id=None,source='telegram'):
    buttons=[('📰 Все новости',SITE+'news/?'+urlencode({'utm_source':source,'utm_medium':'news'})),('🔔 Мой спорт',SITE+'follow.html?'+urlencode({'utm_source':source,'utm_medium':'news'}))]
    if source_id:
        buttons.append(('↗ Поделиться', 'https://t.me/share/url?'+urlencode({'url':f'https://t.me/aistavvit/{int(source_id)}'})))
    return buttons

def news_keyboard(source_id=None,source='dzen_telegram'):
    return json.dumps({'inline_keyboard':[[{'text':text,'url':url} for text,url in news_buttons(source_id,source)[:2]],*([[{'text':news_buttons(source_id,source)[-1][0],'url':news_buttons(source_id,source)[-1][1]}]] if source_id else [])]},ensure_ascii=False)

def attach_news_links(message_id):
    from . import telegram
    return telegram.add_buttons(message_id,news_buttons(message_id))

def run(state,now,results,brand,checkpoint=lambda:None):
    """At most one invitation in seven days, in the main channel only."""
    now=pd.Timestamp(now).tz_convert('Europe/Moscow')
    record=state.setdefault('promotion',{})
    record['targets']={'telegram':'enabled','dzen_telegram':'news_only','vk_rss':'news_articles_only','site':'enabled','youtube':'configured' if all(os.environ.get(k) for k in ('YT_CLIENT_ID','YT_CLIENT_SECRET','YT_REFRESH_TOKEN')) else 'requires_authorization'}
    if now.hour!=17:return False
    if record.get('next_at') and now<pd.Timestamp(record['next_at']):return False
    # Persist the campaign attempt before sending: a timeout must not spam retries.
    record.update(status='sending',attempted_at=now.isoformat(),next_at=(now+pd.Timedelta(days=7)).isoformat())
    checkpoint()
    try:
        from . import content
        message_id=content.invite(results,brand)
    except Exception as exc:
        record.update(status='delivery_requires_review',error=type(exc).__name__)
        checkpoint();return False
    record.update(status='published',message_id=message_id)
    record.pop('error',None);checkpoint();return True
