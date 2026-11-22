"""Original news typography: no broadcast footage or misleading game action."""
import re
from PIL import ImageDraw
from . import shorts,card
from .postimg import plain

def scene(title,text,index):
    img=shorts._bg((14,22,52),(32,21,57));d=ImageDraw.Draw(img)
    shorts._center(d,180,'АИ СТАВИТ · НОВОСТИ',44,shorts.GOLD)
    y=400
    for content,size,color in [(title,64,shorts.WHITE),(text,44,shorts.MUTED)]:
        font=card.font(size,'Bold');line='';lines=[]
        for word in content.split():
            if d.textlength((line+' '+word).strip(),font=font)>900 and line:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        if line:lines.append(line)
        for line in lines:d.text((90,y),line,font=font,fill=color);y+=size+20
        y+=80
    shorts._center(d,1720,'@aistavvit · полная новость на сайте',34,shorts.GOLD)
    return img

def frames(news):
    text=plain(news['body']);sentences=re.findall(r'.*?[.!?…](?=\s|$)',text,flags=re.S)
    # Complete sentences only; never invent facts to fill the video.
    selected=[s.strip() for s in sentences if len(s.strip())<=270][:2]
    return [scene(news['title'],'Коротко о главном',0)]+[scene('Что произошло',s,i+1) for i,s in enumerate(selected)]+[scene('Все подробности','Читайте полную новость на сайте АИ СТАВИТ',3)]

def render(news):
    return shorts.render(frames(news))
