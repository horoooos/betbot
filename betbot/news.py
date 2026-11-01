"""Новости раз в час (в случайную минуту) по нашим видам спорта и киберспорту.

Берём свежую новость из открытых RSS-лент, бесплатная нейросеть Pollinations пересказывает её
своими словами (без новых фактов), под неё рисуется картинка. Если пересказ не удался —
новость пропускается: чужой текст дословно бот не публикует. Ночью (01:00–09:00 МСК) новостей нет.
"""
import json
import random
import re
import time
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
           "главное к", "главное за", "главное дня", "во сколько", "начало матча", "где смотреть",
           # кино и игры — на киберспортивных сайтах их много, но к ставкам они не относятся
           "фильм", "сериал", "кинотеатр", "трейлер", "тизер", "геймплей", "скидк", "steam", "актёр", "актер")
# Фото из ленты источника — фоном под нашим оформлением. Фото принадлежат их авторам и агентствам:
# при претензии правообладателя выключите (False) — тогда картинки снова рисует нейросеть / фирменный фон.
SOURCE_PHOTOS = True
WATER = ("отражает", "вызвал интерес", "вызвало интерес", "стоит отметить", "необходимые мероприятия",
         "не указан", "без дальнейших", "завершает", "стал частью", "в календаре", "обычный график", "готова продолжать",
         "показывает, как", "таким образом", "это может", "это решение", "в результате",
         "очередной раз", "не оставил равнодушным", "подчеркнул важность", "станет важным", "это событие",
         "укрепляет позиции", "положительную динамику", "это подтверждает", "повышает шансы", "в целом")
MIN_DESC = 80  # в новости должно быть хоть какое-то содержание
ORDER = ["football", "esports", "hockey", "football", "basketball", "tennis", "esports"]
TAGS = {"football": "#футбол", "hockey": "#хоккей", "basketball": "#баскетбол", "tennis": "#теннис",
        "esports": "#киберспорт"}
EMOJI = {"football": "⚽️", "hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "esports": "🎮"}
# чтобы нейросеть рисовала именно наш вид спорта (а не, например, американский футбол)
# Картинки к новостям — по заранее заданным спортивным сюжетам: описание «по смыслу новости» нейросеть
# превращала в абстракцию без спорта (человек в лесу вместо тенниса). Несколько вариантов — чтобы не повторялись.
SCENES = {
    "football": ["packed European football stadium at night under floodlights, green pitch, soccer ball on the grass",
                 "close-up of a black and white soccer ball on a wet football pitch, stadium lights bokeh",
                 "aerial view of a football stadium full of fans, green pitch, evening",
                 "soccer goal net and ball on the goal line, stadium in the background, dramatic light"],
    "hockey": ["ice hockey arena with bright ice rink, hockey sticks and puck on the ice, arena lights",
               "close-up of a black hockey puck on fresh ice, scratches on the ice, arena lights",
               "hockey goal net on the ice rink, empty arena, dramatic lighting"],
    "basketball": ["empty basketball arena, orange basketball going into the hoop, empty seats",
                   "close-up of an orange basketball on a polished wooden court, arena lights",
                   "basketball hoop and net from below, arena spotlights"],
    "tennis": ["professional tennis court in a stadium, blue hard court, yellow tennis ball on the baseline",
               "close-up of a yellow tennis ball and racket on a clay court",
               "tennis stadium center court at night under floodlights, net and empty court",
               "grass tennis court with white lines and a tennis ball near the net"],
    "esports": ["empty esports arena with a big stage, neon lights, gaming PCs on desks",
                "close-up of a glowing gaming keyboard and mouse, neon purple and blue light",
                "esports tournament stage with big screens and spotlights, dark arena"],
}
TEXT_API = "https://text.pollinations.ai/openai"
# Сильные бесплатные нейросети (нужен бесплатный ключ в секретах GitHub). Пробуем по порядку; без ключей —
# запасная слабая Pollinations, для неё фильтр фактов строже. Названия бесплатных моделей OpenRouter иногда
# меняются — поэтому несколько кандидатов.
STRONG = [
    ("GROQ_KEY", "https://api.groq.com/openai/v1/chat/completions", ["llama-3.3-70b-versatile"]),
    ("OPENROUTER_KEY", "https://openrouter.ai/api/v1/chat/completions",
     ["deepseek/deepseek-chat-v3-0324:free", "meta-llama/llama-3.3-70b-instruct:free", "google/gemma-3-27b-it:free"]),
]
STRONG_STYLE = (
    "Пиши как автор популярного спортивного Telegram-канала: цепляющее первое предложение, живой разговорный, "
    "но грамотный язык, яркие глаголы, без канцелярита. 3–5 предложений, 350–700 символов. Факты, цифры, "
    "имена и цитаты — ТОЛЬКО из исходника, ничего не придумывай; эмоцию передавай словами, а не выдуманными деталями. "
)
PROMPT = (
    "Ты — редактор русскоязычного спортивного Telegram-канала и пишешь как живой спортивный журналист. "
    "Перескажи новость своими словами на РУССКОМ языке, имена — русскими буквами, клубы — в кавычках-ёлочках. "
    "Структура текста: 1) главное событие с конкретикой (кто, что, счёт/цифры, турнир); "
    "2) важные детали из текста статьи (статистика, обстоятельства, суть цитаты своими словами); "
    "3) что это значит или что будет дальше — ТОЛЬКО если это есть в исходнике. "
    "Если фактов мало — напиши 2 коротких предложения, не растягивай и не додумывай. "
    "СТРОГО: только факты из исходника, ничего не выдумывай. Без канцелярита и пустых фраз вроде "
    "«отметил впечатление», «стоит отметить», «это событие вызвало интерес». Не пиши про источник. "
    "Пиши грамотно, без опечаток и несуществующих слов. "
    "Ответь только JSON без пояснений: {\"sport\": \"football|hockey|basketball|tennis|esports|other\", "
    "\"title\": \"цепляющий информативный заголовок до 70 символов: кто и что сделал (не цитата, не обрывок)\", "
    "\"text\": \"3–4 предложения, 250–500 символов, по структуре выше; не повторяй заголовок слово в слово\", "
    "\"emoji\": \"один подходящий эмодзи\"}"
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
            enc = it.find("enclosure")
            photo = enc.get("url") if enc is not None and "image" in (enc.get("type") or "image") else None
            if not title or any(w in title.lower() for w in SERVICE) or len(desc) < MIN_DESC:
                continue  # служебный материал или пустая заметка — не новость
            out.append({"id": guid, "title": title, "desc": desc, "when": when, "photo": photo,
                        "link": it.findtext("link") or ""})
    return sorted(out, key=lambda x: x["when"], reverse=True)


def _article(item: dict) -> tuple[str, str | None]:
    """Полный текст статьи (первые абзацы) и фото со страницы — чтобы пересказ был содержательным."""
    if not item.get("link"):
        return "", None
    try:
        h = requests.get(item["link"], timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
    except Exception:
        return "", None
    og = re.search(r'property="og:image"\s+content="([^"]+)"', h) or re.search(r'content="([^"]+)"\s+property="og:image"', h)
    paras = [_clean(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)]
    # меню и подписи короткие, а абзацы статьи — длинные предложения
    paras = [p for p in paras if len(p) >= 60 and p.count(" ") >= 8 and "cookie" not in p.lower()]
    body = " ".join(paras)[:1800]
    if any(w in body.lower() for w in ("перенаправлен", "подождите", "javascript", "включите")):
        body = ""  # вместо статьи — заглушка сайта
    return body, (og.group(1) if og else None)


def _stems(text: str) -> set[str]:
    """Основы слов (первые 5 букв), чтобы «победил/победы/победой» считались одним словом."""
    return {w[:5] for w in re.findall(r"[а-яёa-z]{4,}", text.lower())}


STOP = {"котор", "этого", "также", "после", "время", "своей", "своих", "матче", "матча", "против", "между"}


def _numbers_ok(sentence: str, item: dict) -> bool:
    """Каждое число из текста есть в исходнике (счета, туры, возраст) — иначе нейросеть его выдумала."""
    src = item["title"] + " " + item["desc"] + " " + item.get("body", "")
    return all(n in src for n in re.findall(r"\d+", sentence))


def _grounded(text: str, item: dict, strict: bool = True) -> str:
    """Оставляет только предложения, которые опираются на исходник: все числа — из статьи, без «воды».

    strict (слабая нейросеть): ещё и ≥60% значимых слов предложения есть в статье, максимум 3 предложения.
    Сильная модель пишет живее и своими словами — для неё порог мягче (35%), до 5 предложений.
    """
    src = _stems(item["title"] + " " + item["desc"] + " " + item.get("body", ""))
    need, most = (0.6, 3) if strict else (0.35, 5)
    keep = []
    for s in re.split(r"(?<=[.!?…])\s+", text.strip()):
        words = _stems(s) - STOP
        if len(words) < 3 or any(w in s.lower() for w in WATER):
            continue
        if len(words & src) / len(words) >= need and _numbers_ok(s, item):
            keep.append(s)
    text = " ".join(keep[:most])
    return text if len(text) >= (90 if strict else 160) else ""


def _cyrillic(text: str) -> float:
    """Доля русских букв среди всех букв (названия команд латиницей вроде «NAVI» допускаются)."""
    letters = [c for c in text if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / max(len(letters), 1)


def _ask(messages: list[dict]) -> tuple[dict | None, bool]:
    """JSON-ответ нейросети и признак «сильная модель». Сначала бесплатные сильные (если есть ключ), потом Pollinations."""
    import os
    for env, url, models in STRONG:
        key = os.environ.get(env)
        if not key:
            continue
        for model in models:
            try:
                r = requests.post(url, timeout=60, headers={"Authorization": f"Bearer {key}"},
                                  json={"model": model, "temperature": 0.6, "messages": messages})
                if r.status_code != 200:
                    continue
                raw = r.json()["choices"][0]["message"]["content"]
                return json.loads(raw[raw.index("{"): raw.rindex("}") + 1]), True
            except Exception:
                continue
    body = {"model": "openai", "private": True, "temperature": 0.2, "messages": messages}
    for _ in range(2):  # бесплатная нейросеть иногда отвечает не по формату — даём вторую попытку
        try:
            raw = requests.post(TEXT_API, json=body, timeout=90).json()["choices"][0]["message"]["content"]
            return json.loads(raw[raw.index("{"): raw.rindex("}") + 1]), False
        except Exception:
            time.sleep(6)  # бесплатный доступ: при частых запросах отвечает ошибкой — ждём и повторяем
    return None, False


def _rewrite(item: dict) -> dict | None:
    user = {"role": "user", "content": f"Заголовок: {item['title']}\nОписание: {item['desc']}"
                                       + (f"\nТекст статьи: {item['body']}" if item.get("body") else "")}
    data, strong = _ask([{"role": "system", "content": STRONG_STYLE + PROMPT}, user])
    if not data:
        return None
    fix = str.maketrans({"‐": "-", "‑": "-", " ": " ", " ": " "})  # «неразрывные» дефисы и пробелы
    title, text = str(data.get("title", "")).strip().translate(fix), str(data.get("text", "")).strip().translate(fix)
    if not (10 <= len(title) <= 110 and 40 <= len(text) <= 700):
        return None
    if title.lower() == item["title"].lower():  # нейросеть просто повторила заголовок — не годится
        return None
    if any(w in text.lower() for w in WATER):  # «вода» и домыслы нейросети — такой текст не публикуем
        return None
    words = lambda s: set(re.findall(r"\w{3,}", s.lower()))  # noqa: E731
    if len(words(text) - words(title)) < 6:  # текст — тот же заголовок другими словами, читать нечего
        return None
    if _cyrillic(title) < 0.4 or _cyrillic(text) < 0.4:  # ответила по-английски — в русский канал не годится
        return None
    if len(text) > 1.6 * len(item["title"] + " " + item["desc"] + " " + item.get("body", "")) + 80:  # досочинила
        return None
    text = _grounded(text, item, strict=not strong)
    if not text or not _numbers_ok(title, item):
        return None  # после проверки фактов почти ничего не осталось — новость не выходит
    return {"sport": str(data.get("sport", "")).strip().lower(), "title": title, "text": text,
            "emoji": str(data.get("emoji") or "")[:4]}


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
        fresh.sort(key=lambda x: not x.get("photo"))  # сначала новости с фото в ленте
        for item in fresh[:5]:
            if tries >= MAX_TRIES:  # остальное — в следующий запуск (через пару минут)
                state["news_next"] = (now + pd.Timedelta(minutes=2)).isoformat()
                return
            tries += 1
            seen.append(item["id"])
            item["body"], og = _article(item)
            item["photo"] = item.get("photo") or og
            if SOURCE_PHOTOS and not item["photo"]:  # без фото новость выглядит бедно — берём следующую
                continue
            news = _rewrite(item)
            if not news or news["sport"] != sport:  # новость не про этот вид спорта (Ф-1, бокс…) — пропускаем
                continue
            prompt = f"{random.choice(SCENES[sport])}, cinematic, high detail, photorealistic, no text, no people, no players, no faces, empty scene"
            tag = TAGS[sport].lstrip("#").capitalize()
            png = card.news_card(item["photo"] if SOURCE_PHOTOS else None, news["title"], tag, brand, sport, prompt)
            telegram.send_photo(png, f"{news['emoji'] or EMOJI[sport]} <b>{escape(news['title'])}</b>\n\n"
                                     f"{escape(news['text'])}\n\n{TAGS[sport]}")
            state["news_i"] = (i + shift + 1) % len(ORDER)
            state["news_next"] = (now + pd.Timedelta(minutes=random.randint(40, 65))).isoformat()  # каждый час
            del seen[:-500]
            print(f"Новость ({sport}): {news['title']}")
            return
    state["news_next"] = (now + pd.Timedelta(minutes=6)).isoformat()  # не вышло — пробуем снова через несколько минут
