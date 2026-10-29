"""Новости раз в час (в случайную минуту) по нашим видам спорта и киберспорту.

Берём свежую новость из открытых RSS-лент, бесплатная нейросеть Pollinations пересказывает её
своими словами (без новых фактов), под неё рисуется картинка. Если пересказ не удался —
новость пропускается: чужой текст дословно бот не публикует. Ночью (01:00–09:00 МСК) новостей нет.
"""
import json
import random
import re
import xml.etree.ElementTree as ET
from html import escape, unescape

import pandas as pd
import requests

from . import card, telegram

FEEDS = {
    "football": ["https://www.championat.com/rss/news/football/"],
    "hockey": ["https://www.championat.com/rss/news/hockey/"],
    "basketball": ["https://www.championat.com/rss/news/basketball/"],
    "tennis": ["https://www.championat.com/rss/news/tennis/"],
    "esports": ["https://www.championat.com/rss/news/cybersport/", "https://www.cybersport.ru/rss/materials"],
}
# общие ленты обо всём спорте — из них берём только новости, у которых рубрика/заголовок про нужный вид спорта
MIXED = ["https://www.sports.ru/rss/main.xml", "https://www.sport-express.ru/services/materials/news/se/"]
WORDS = {"football": ("футбол", "рпл", "лига чемпионов", "апл"), "hockey": ("хоккей", "кхл", "нхл"),
         "basketball": ("баскетбол", "нба", "единая лига"), "tennis": ("теннис", "atp", "wta"),
         "esports": ("киберспорт", "cs2", "cs 2", "dota", "дота", "counter-strike", "major", "мейджор", "navi",
                     "team spirit", "the international", "iem", "blast", "pgl")}
MAX_TRIES = 3  # попыток пересказа за один запуск — чтобы новости не задерживали live и прогнозы
# служебные материалы — не новости: расписания, итоги тура, трансляции, таблицы, чужие прогнозы
SERVICE = ("расписание", "результаты", "трансляц", "где смотреть", "смотреть онлайн", "онлайн", "таблица",
           "прогноз", "коэффициент", "ставк", "анонс", "текстовая", "видеообзор", "видео", "фото", "календар",
           "обзор тура", "обзор матч", "лучшие моменты", "голы матча", "live", "прямой эфир", "тест", "опрос",
           "главное к", "главное за", "главное дня",
           # кино и игры — на киберспортивных сайтах их много, но к ставкам они не относятся
           "фильм", "сериал", "кинотеатр", "трейлер", "тизер", "геймплей", "скидк", "steam", "актёр", "актер")
MIN_DESC = 80  # в новости должно быть хоть какое-то содержание
ORDER = ["football", "esports", "hockey", "football", "basketball", "tennis", "esports"]
TAGS = {"football": "#футбол", "hockey": "#хоккей", "basketball": "#баскетбол", "tennis": "#теннис",
        "esports": "#киберспорт"}
EMOJI = {"football": "⚽️", "hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "esports": "🎮"}
# чтобы нейросеть рисовала именно наш вид спорта (а не, например, американский футбол)
SCENE = {"football": "association football (soccer), round black and white soccer ball, European stadium",
         "hockey": "ice hockey, ice rink, puck and sticks", "basketball": "basketball court, orange basketball, hoop",
         "tennis": "tennis court, tennis racket and yellow ball", "esports": "esports arena, gaming PC, gamepad, neon"}
TEXT_API = "https://text.pollinations.ai/openai"
PROMPT = (
    "Ты редактор русскоязычного спортивного Telegram-канала. Перескажи новость своими словами, живо и коротко. "
    "Заголовок и текст пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, имена — русскими буквами. "
    "СТРОГО: используй только факты из исходника. Не добавляй оценок, мнений, реакции болельщиков или "
    "«обсуждений» — если в исходнике мало фактов, пиши коротко. Не пиши про источник. "
    "Ответь только JSON без пояснений: {\"sport\": \"football|hockey|basketball|tennis|esports|other\", "
    "\"title\": \"заголовок до 70 символов\", "
    "\"text\": \"1–2 предложения: перефразируй только то, что есть в описании, не длиннее его\", "
    "\"emoji\": \"один подходящий эмодзи\", "
    "\"image_prompt\": \"короткое описание картинки по-английски, без текста и без реальных лиц\"}"
)


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html or ""))).strip()


def _items(sport: str) -> list[dict]:
    out = []
    for url in FEEDS[sport] + MIXED:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = _clean(it.findtext("title"))
            if url in MIXED or "cybersport.ru" in url:  # общие ленты (и кино/игры на Cybersport.ru) — по рубрике
                tags = " ".join(_clean(c.text) for c in it.findall("category")) + " " + title
                if not any(w in tags.lower() for w in WORDS[sport]):
                    continue
            guid = it.findtext("guid") or it.findtext("link") or title
            try:
                when = pd.Timestamp(it.findtext("pubDate")).tz_convert("UTC")
            except Exception:
                when = pd.Timestamp.now(tz="UTC")
            desc = _clean(it.findtext("description"))[:700]
            if not title or any(w in title.lower() for w in SERVICE) or len(desc) < MIN_DESC:
                continue  # служебный материал или пустая заметка — не новость
            out.append({"id": guid, "title": title, "desc": desc, "when": when})
    return sorted(out, key=lambda x: x["when"], reverse=True)


def _cyrillic(text: str) -> float:
    """Доля русских букв среди всех букв (названия команд латиницей вроде «NAVI» допускаются)."""
    letters = [c for c in text if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / max(len(letters), 1)


def _rewrite(item: dict) -> dict | None:
    body = {"model": "openai", "private": True,
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": f"Заголовок: {item['title']}\nОписание: {item['desc']}"}]}
    data = None
    for _ in range(2):  # бесплатная нейросеть иногда отвечает не по формату — даём вторую попытку
        try:
            r = requests.post(TEXT_API, json=body, timeout=90)
            raw = r.json()["choices"][0]["message"]["content"]
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            break
        except Exception:
            continue
    if not data:
        return None
    title, text = str(data.get("title", "")).strip(), str(data.get("text", "")).strip()
    if not (10 <= len(title) <= 110 and 40 <= len(text) <= 700):
        return None
    if title.lower() == item["title"].lower():  # нейросеть просто повторила заголовок — не годится
        return None
    if _cyrillic(title) < 0.4 or _cyrillic(text) < 0.4:  # ответила по-английски — в русский канал не годится
        return None
    if len(text) > 1.3 * len(item["title"] + " " + item["desc"]) + 40:  # длиннее исходника — значит, досочинила
        return None
    return {"sport": str(data.get("sport", "")).strip().lower(), "title": title, "text": text,
            "emoji": str(data.get("emoji") or "")[:4],
            "image_prompt": str(data.get("image_prompt") or "")[:300]}


def run(state: dict, now: pd.Timestamp, brand: str) -> None:
    """Вызывается каждый запуск; публикует одну новость, когда подошло случайное время."""
    if 2 <= now.hour < 8:  # ночью с 02:00 до 08:00 новостей нет
        return
    nxt = state.get("news_next")
    if nxt and now < pd.Timestamp(nxt):
        return
    seen = state.setdefault("news_seen", [])
    i = state.get("news_i", 0)
    tries = 0
    for shift in range(len(ORDER)):
        sport = ORDER[(i + shift) % len(ORDER)]
        fresh = [x for x in _items(sport) if x["id"] not in seen and x["when"] > now.tz_convert("UTC") - pd.Timedelta(hours=6)]
        for item in fresh[:5]:
            if tries >= MAX_TRIES:  # остальное — в следующий запуск (через пару минут)
                state["news_next"] = (now + pd.Timedelta(minutes=2)).isoformat()
                return
            tries += 1
            seen.append(item["id"])
            news = _rewrite(item)
            if not news or news["sport"] != sport:  # новость не про этот вид спорта (Ф-1, бокс…) — пропускаем
                continue
            prompt = f"{SCENE[sport]}, {news['image_prompt']}, cinematic, high detail, no text, no faces"
            png = card.ai_card(prompt, news["title"], TAGS[sport].lstrip("#").capitalize(), brand)
            telegram.send_photo(png, f"{news['emoji'] or EMOJI[sport]} <b>{escape(news['title'])}</b>\n\n"
                                     f"{escape(news['text'])}\n\n{TAGS[sport]}")
            state["news_i"] = (i + shift + 1) % len(ORDER)
            state["news_next"] = (now + pd.Timedelta(minutes=random.randint(40, 65))).isoformat()  # каждый час
            del seen[:-500]
            print(f"Новость ({sport}): {news['title']}")
            return
    state["news_next"] = (now + pd.Timedelta(minutes=6)).isoformat()  # не вышло — пробуем снова через несколько минут
