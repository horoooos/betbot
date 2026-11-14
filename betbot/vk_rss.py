"""Presentation of native VK RSS posts; image uploading stays with VK import."""
import re

from . import vk

SPORTS = {"football": "#Футбол", "hockey": "#Хоккей", "basketball": "#Баскетбол",
          "tennis": "#Теннис", "esports": "#Киберспорт"}
LEAGUES = ("РПЛ", "КХЛ", "АПЛ", "NHL", "NBA", "ATP", "WTA", "CS2", "Dota")


def hashtags(news):
    from .photos import NOT_NAMES
    text = news["title"] + ". " + news["body"][:500]
    tags = [SPORTS.get(news.get("sport"), "#Спорт")]
    tags += ["#" + league for league in LEAGUES if re.search(r"\b" + re.escape(league) + r"\b", text, re.I)][:1]
    excluded = NOT_NAMES | {"Игрок", "Обладатель", "Кубка", "Лиги", "Лига", "Европы", "Спорт", "День", "Тест"}
    entities = []
    for first, last in re.findall(r"(?=\b([А-ЯЁ][а-яё]+)[ \t]+([А-ЯЁ][а-яё]{2,})\b)", text):
        if first not in excluded and last not in excluded:
            entities.append("#" + first + last)
    for quoted in re.findall(r"«([^»\n]{2,25})»", text):
        if re.fullmatch(r"[А-ЯЁA-Z][\w .-]+", quoted) and len(quoted.split()) <= 3:
            entities.append("#" + re.sub(r"[^\wА-Яа-яЁё]", "", quoted))
    tags += list(dict.fromkeys(entities))[:2]
    tags += ["#НовостиСпорта", "#АИСТАВИТ"]
    return " ".join(dict.fromkeys(tags))


def prepare(news, links):
    canonical = vk.SITE + news["url"]
    short = vk._short(canonical, {"vk_shortlinks": links})
    body = re.sub(r"\n{3,}", "\n\n", news["body"]).strip()
    tags = hashtags(news)
    return {**news, "rss_link": "https://" + short, "body": body + "\n\n" + tags}
