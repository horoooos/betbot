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
