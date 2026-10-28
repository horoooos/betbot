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
    "football": ["https://www.championat.com/rss/news/football/", "https://www.sports.ru/rss/main.xml"],
    "hockey": ["https://www.championat.com/rss/news/hockey/"],
    "basketball": ["https://www.championat.com/rss/news/basketball/"],
    "tennis": ["https://www.championat.com/rss/news/tennis/"],
    "esports": ["https://www.championat.com/rss/news/cybersport/", "https://www.cybersport.ru/rss/materials"],
}
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
    "Ты редактор спортивного Telegram-канала. Перескажи новость своими словами, живо и коротко. "
    "СТРОГО: используй только факты из исходника, ничего не добавляй и не додумывай, не пиши про источник. "
    "Ответь только JSON без пояснений: {\"title\": \"заголовок до 70 символов\", "
    "\"text\": \"2–3 предложения\", \"emoji\": \"один подходящий эмодзи\", "
    "\"image_prompt\": \"короткое описание картинки по-английски, без текста и без реальных лиц\"}"
)


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html or ""))).strip()


def _items(sport: str) -> list[dict]:
    out = []
    for url in FEEDS[sport]:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = _clean(it.findtext("title"))
            guid = it.findtext("guid") or it.findtext("link") or title
            try:
                when = pd.Timestamp(it.findtext("pubDate")).tz_convert("UTC")
            except Exception:
                when = pd.Timestamp.now(tz="UTC")
            if title:
                out.append({"id": guid, "title": title, "desc": _clean(it.findtext("description"))[:700], "when": when})
    return sorted(out, key=lambda x: x["when"], reverse=True)


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
    return {"title": title, "text": text, "emoji": str(data.get("emoji") or "")[:4],
            "image_prompt": str(data.get("image_prompt") or "")[:300]}


def run(state: dict, now: pd.Timestamp, brand: str) -> None:
    """Вызывается каждый запуск; публикует одну новость, когда подошло случайное время."""
    if not (9 <= now.hour or now.hour < 1):
        return
    nxt = state.get("news_next")
    if nxt and now < pd.Timestamp(nxt):
        return
    seen = state.setdefault("news_seen", [])
    i = state.get("news_i", 0)
    for shift in range(len(ORDER)):
        sport = ORDER[(i + shift) % len(ORDER)]
        fresh = [x for x in _items(sport) if x["id"] not in seen and x["when"] > now.tz_convert("UTC") - pd.Timedelta(hours=6)]
        for item in fresh[:3]:
            seen.append(item["id"])
            news = _rewrite(item)
            if not news:
                continue
            prompt = f"{SCENE[sport]}, {news['image_prompt']}, cinematic, high detail, no text, no faces"
            png = card.ai_card(prompt, news["title"], TAGS[sport].lstrip("#").capitalize(), brand)
            telegram.send_photo(png, f"{news['emoji'] or EMOJI[sport]} <b>{escape(news['title'])}</b>\n\n"
                                     f"{escape(news['text'])}\n\n{TAGS[sport]}")
            state["news_i"] = (i + shift + 1) % len(ORDER)
            state["news_next"] = (now + pd.Timedelta(minutes=random.randint(45, 80))).isoformat()
            del seen[:-500]
            print(f"Новость ({sport}): {news['title']}")
            return
    state["news_next"] = (now + pd.Timedelta(minutes=20)).isoformat()  # не вышло — попробуем позже
