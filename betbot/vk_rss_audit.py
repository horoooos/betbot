"""Check actual native-import events; never equate a generated feed with a post."""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from . import vk

FEED=Path(__file__).resolve().parents[1]/'docs/rss-vk-article.xml'


def inspect(post,items):
    text=post.get('text','')
    attachments=post.get('attachments') or []
    titles=[(a.get(a.get('type')) or {}).get('title','') for a in attachments]
    matched=next((item for item in items if item['title'] and any(item['title'].casefold() in value.casefold() for value in [text]+titles)),None)
    if not matched:return None
    compact=lambda value:re.sub(r'\s+',' ',value).strip()
    expected=compact(matched['description'])
    actual=compact(text)
    body=actual
    title=compact(matched['title'])
    if body.casefold().startswith(title.casefold()+' '):body=body[len(title):].strip()
    body=re.sub(r'\s+(?:https?://)?vk\.cc/[A-Za-z0-9]+$','',body).strip()
    tags=re.findall(r'#[\wА-Яа-яЁё]+',matched['description'])
    links=set(re.findall(r'(?:https?://)?vk\.cc/[A-Za-z0-9]+',text))
    image=any(a.get('type')=='photo' or bool((a.get('article') or {}).get('photo') or (a.get('article') or {}).get('cover') or (a.get('link') or {}).get('photo')) for a in attachments)
    checks=dict(expected_caption_present=bool(expected) and expected in actual,
                complete_layout=body==expected,
                hashtags_present=bool(tags) and all(t in text for t in tags),
                details_present='подробнее на сайте' in text.lower(),
                one_short_link=len(links)==1,long_source_absent='horoooos.github.io' not in text,
                image_present=image)
    return dict(post_id=post.get('id'),url=f"https://vk.com/wall-{vk.GROUP_ID}_{post.get('id')}",
                title=matched['title'],text=text[:4096],checks=checks,
                status='verified' if all(checks.values()) else 'needs_review')


def poll(state,now):
    token=os.environ.get('VK_TOKEN')
    if not token or not FEED.exists():return
    items=[{k:i.findtext(k,'') for k in ('title','description')} for i in ET.fromstring(FEED.read_bytes()).findall('channel/item')]
    audit=state.setdefault('vk_rss_audit',{})
    server=vk._call('groups.getLongPollServer',_tok=token,group_id=vk.GROUP_ID)
    cursor=audit.get('cursor',server['ts'])
    try:
        response=requests.get(server['server'],params=dict(act='a_check',key=server['key'],ts=cursor,wait=0),timeout=12)
        response.raise_for_status();result=response.json()
    except (requests.RequestException,ValueError):
        # Request exceptions may contain the Long Poll credential in the URL.
        raise RuntimeError('Native VK event check unavailable; credentials hidden') from None
    audit['last_poll']=now.isoformat()
    audit['cursor']=result.get('ts',server['ts'])
    if result.get('failed'):
        audit['status']='cursor_reset';return
    receipts={str(p['post_id']):p for p in audit.get('posts',[])}
    for event in result.get('updates',[]):
        if event.get('type')!='wall_post_new' or event.get('group_id')!=vk.GROUP_ID:continue
        receipt=inspect(event.get('object') or {},items)
        if receipt:
            receipt['observed_at']=now.isoformat();receipts[str(receipt['post_id'])]=receipt
            print('VK RSS actual post:',receipt['status'],receipt['url'])
    audit['posts']=list(receipts.values())[-30:]
    audit['status']='observing'
