"""Presentation of native VK RSS posts; image uploading stays with VK import."""
import re

from . import vk

SPORTS = {"football": "#футбол", "hockey": "#хоккей", "basketball": "#баскетбол",
          "tennis": "#теннис", "esports": "#киберспорт"}
EMOJI = {"football": "⚽", "hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "esports": "🎮"}
LEAGUES = ("РПЛ", "КХЛ", "АПЛ", "NHL", "NBA", "ATP", "WTA", "CS2", "Dota")


def hashtags(news):
    from .photos import NOT_NAMES
    text = news["title"] + ". " + news["body"][:500]
    tags = [SPORTS.get(news.get("sport"), "#спорт")]
    tags += ["#" + league for league in LEAGUES if re.search(r"\b" + re.escape(league) + r"\b", text, re.I)][:1]
    excluded = NOT_NAMES | {"Игрок", "Обладатель", "Кубка", "Лиги", "Лига", "Европы", "Спорт", "День", "Тест"}
    entities = []
    for first, last in re.findall(r"(?=\b([А-ЯЁ][а-яё]+)[ \t]+([А-ЯЁ][а-яё]{2,})\b)", text):
        if first not in excluded and last not in excluded:
            entities.append("#" + last)
    # Prefer the person named in the headline; avoid tagging every person
    # mentioned in the article and avoid turning declined club names into tags.
    entities = list(dict.fromkeys(entities))
    entities.sort(key=lambda tag: tag[1:].casefold() not in news["title"].casefold())
    tags += entities[:1]
    for quoted in re.findall(r"«([^»\n]{2,25})»", news["title"]):
        if re.fullmatch(r"[А-ЯЁA-Z][\w .-]+", quoted) and len(quoted.split()) <= 3:
            tags.append("#" + re.sub(r"[^\wА-Яа-яЁё]", "", quoted))
            break
    tags += ["#новостиспорта", "#спорт", "#главное", "#аиставит"]
    return " ".join(dict.fromkeys(tags))


def prepare(news, links):
    canonical = vk.SITE + news["url"]
    short = vk._short(canonical, {"vk_shortlinks": links})
    body = re.sub(r"\n{3,}", "\n\n", news["body"]).strip()
    paragraphs = []
    for i, paragraph in enumerate(re.split(r"\n\s*\n", body)):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if not re.match(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", paragraph):
            paragraph = ("📰", "📌", "💬", "📊", "🔎")[i % 5] + " " + paragraph
        paragraphs.append(paragraph)
    tags = hashtags(news).split()
    formatted = "\n\n".join(paragraphs) + "\n\n" + tags[0]
    formatted += f"\n\n📊 Подробнее на сайте 👉 {short}\n\n" + " ".join(tags[1:])
    title = news["title"].strip()
    if not re.match(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", title):
        title = EMOJI.get(news.get("sport"), "📰") + " " + title
    return {**news, "title": title, "rss_link": "https://" + short, "body": formatted}


def article_page(news):
    """ASCII transport survives importers guessing Windows-1251 for HTML."""
    from html import escape
    title = re.sub(r'^[^\wА-Яа-яЁё«"]+', '', news['title'])
    content = wall_description(news)
    description = announcement(news)
    paragraphs = ''.join('<p>'+escape(p).replace('\n','<br>')+'</p>' for p in content.split('\n\n') if p.strip())
    short = news.get('rss_link', '')
    if short:
        paragraphs = paragraphs.replace(escape(short.removeprefix('https://')), '<a href="'+escape(short,quote=True)+'">'+escape(short.removeprefix('https://'))+'</a>')
    html = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+escape(title)+'</title><meta property="og:title" content="'+escape(title,quote=True)+'">'
            '<meta name="description" content="'+escape(description,quote=True)+'"><meta property="og:description" content="'+escape(description,quote=True)+'">'
            '<meta property="og:type" content="article"><meta property="og:image" content="'+escape(news['photo'],quote=True)+'">'
            '<style>body{max-width:760px;margin:32px auto;padding:0 20px;font:18px/1.65 system-ui}img{width:100%}p{margin:1.2em 0}</style>'
            '</head><body><article><h1>'+escape(title)+'</h1><img src="'+escape(news['photo'],quote=True)+'">'+paragraphs+'</article></body></html>')
    return html.encode('ascii','xmlcharrefreplace').decode('ascii')


def wall_description(news):
    """Full article with one footer; the wall teaser is built separately."""
    short = news.get('rss_link','').removeprefix('https://')
    body = news['body']
    # Move the prepared footer once, keeping every paragraph of the news.
    marker = '\n\n'+SPORTS.get(news.get('sport'),'#спорт')
    body = body.split(marker,1)[0]
    footer = f"\n\n📊 Подробнее на сайте 👉 {short}" if short else ''
    return body+'\n\n'+hashtags(news)+footer


def announcement(news, limit=420):
    """Wall teaser: complete paragraphs/sentences, full article stays elsewhere."""
    from html import unescape
    short=news.get('rss_link','').removeprefix('https://')
    if news.get('vk_native_link'):
        # VK appends the RSS item link itself. Do not print that URL twice.
        link_line='📊 Подробнее на сайте 👇'
    else:
        link_line=f'📊 Подробнее на сайте 👉 {short}' if short else ''
    footer=hashtags(news)+(('\n\n'+link_line) if link_line else '')
    body=news['body'].split('\n\n'+SPORTS.get(news.get('sport'),'#спорт'),1)[0]
    body=unescape(re.sub(r'<[^>]+>','',body)).strip()
    budget=max(0,limit-len(footer)-2)
    chosen=[]
    for paragraph in re.split(r'\n\s*\n',body):
        paragraph=paragraph.strip()
        if not paragraph:continue
        remaining=budget-len('\n\n'.join(chosen))-(2 if chosen else 0)
        completed=paragraph if paragraph[-1:] in '.!?…»”"' else paragraph+'.'
        if len(completed)<=remaining:
            chosen.append(completed)
            if len(chosen)==2:break
        else:
            if not chosen:
                sentences=re.findall(r'.*?[.!?…](?:[»”"\')\]]*)(?=\s|$)',paragraph,flags=re.S)
                for sentence in sentences:
                    sentence=sentence.strip()
                    candidate=' '.join(chosen+[sentence])
                    if len(candidate)>budget:break
                    chosen.append(sentence)
                if chosen:chosen=[' '.join(chosen)]
            break
    summary='\n\n'.join(chosen) or 'Полный материал и подробности — в статье.'
    return summary+'\n\n'+footer
