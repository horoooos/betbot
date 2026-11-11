"""Фото по теме поста: герой новости (игрок, тренер, клуб) или сама тема — из открытых источников.

Порядок поиска:
1. Wikidata: находим человека/клуб по имени и проверяем, что это спорт (описание, профессия);
2. Wikimedia Commons: фото из его карточки и его альбома (категории) — каждый раз новое, без повторов;
3. поиск по всей Wikimedia Commons: по английскому имени, иначе — по теме (матч этого вида спорта);
4. ничего — вызывающий рисует фирменный фон.

Все фото — под свободными лицензиями; автора и лицензию возвращаем, чтобы подписать на картинке.
Использованные адреса храним в state["img_used"], чтобы одна картинка не повторялась в постах.
"""
from __future__ import annotations

import random
import re
from html import unescape

import requests

UA = {"User-Agent": "AIStavitBot/1.0 (https://horoooos.github.io/betbot/)"}
WD = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
SPORT_EN = {"football": "football", "hockey": "ice hockey", "basketball": "basketball", "tennis": "tennis",
            "esports": "esports"}
SPORTY = ("футбол", "хокке", "теннис", "баскетбол", "киберспорт", "клуб", "спортсмен", "игрок", "тренер", "вратар",
          "нападающ", "защитник", "полузащит", "сборн", "команд", "стадион", "арена", "лига",
          "football", "soccer", "hockey", "tennis", "basketball", "esports", "player", "team", "club", "coach",
          "dota", "counter-strike", "gamer", "stadium", "athlete", "sport")
NOT_NAMES = {"Глава", "Тренер", "Главный", "Бывший", "Защитник", "Форвард", "Нападающий", "Вратарь", "Президент",
             "Капитан", "Сборная", "Россия", "России", "Чемпионат", "Лига", "Матч", "Итоги", "Источник", "Стало",
             "Известно", "Обладатель", "Пресс", "Официально", "Инсайдер", "Журналист", "Агент", "Легенда"}
KEEP = 300   # сколько последних картинок помним, чтобы не повторяться


def names(title: str, text: str = "") -> list[str]:
    """Кто в новости: люди «Имя Фамилия», команды «в кавычках» и латиницей, одиночные фамилии."""
    src = title + " . " + text[:500]
    persons, teams, singles = [], [], []
    for m in re.finditer(r"«([^»]{2,30})»(\s+[А-ЯЁ][а-яё]+)?", src):            # «Динамо» Махачкала
        teams.append((m.group(1) + (m.group(2) or "")).strip())
    for m in re.finditer(r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]+)?)", src):
        if m.group(1) not in NOT_NAMES and m.group(2) not in NOT_NAMES:     # Андрей Канчельскис
            persons.append(m.group(0))
    for m in re.finditer(r"\b([A-Z][\w.&-]{2,}(?:\s+[A-Z][\w.&-]+)*)", src):  # Virtus.pro, Arteezy
        teams.append(m.group(1))
    for m in re.finditer(r"(?<![«\w-])([А-ЯЁ][а-яё]{3,})", src):             # Канчельскис, Мбаппе
        if m.group(1) not in NOT_NAMES:
            singles.append(m.group(1))
    out: list[str] = []
    for n in persons + teams + singles:
        if n not in out and not any(n in o for o in out):
            out.append(n)
    return out[:6]


def _get(url: str, **params) -> dict:
    try:
        r = requests.get(url, params=params, headers=UA, timeout=15)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html or ""))).strip()


def _commons_files(entity: dict) -> list[str]:
    """Файлы Commons про человека/клуб: фото из карточки (P18) + до 30 фото из его категории (P373)."""
    claims = entity.get("claims", {})
    files = [c["mainsnak"]["datavalue"]["value"] for c in claims.get("P18", []) if c["mainsnak"].get("datavalue")]
    cat = next((c["mainsnak"]["datavalue"]["value"] for c in claims.get("P373", []) if c["mainsnak"].get("datavalue")), None)
    if cat:
        r = _get(COMMONS, action="query", format="json", list="categorymembers", cmtitle=f"Category:{cat}",
                 cmtype="file", cmlimit=40)
        files += [m["title"].split(":", 1)[1] for m in r.get("query", {}).get("categorymembers", [])]
    return [f for f in dict.fromkeys(files) if re.search(r"\.(jpe?g|png|webp)$", f, re.I)]


def _commons_info(files: list[str], min_w: int = 600, min_h: int = 400) -> list[dict]:
    """Адрес картинки 1280px, размеры, автор и лицензия для файлов Commons."""
    out = []
    for i in range(0, len(files), 20):
        r = _get(COMMONS, action="query", format="json", prop="imageinfo", iiprop="url|size|extmetadata",
                 iiurlwidth=1280, titles="|".join("File:" + f for f in files[i:i + 20]))
        for p in r.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            if ii.get("width", 0) < min_w or ii.get("height", 0) < min_h:
                continue
            out.append({"url": ii.get("thumburl") or ii.get("url"), "w": ii.get("width"), "h": ii.get("height"),
                        "title": p.get("title", ""),
                        "author": _strip(meta.get("Artist", {}).get("value", ""))[:40],
                        "license": _strip(meta.get("LicenseShortName", {}).get("value", "")),
                        "source": "Wikimedia Commons"})
    return out


def _wikidata(q: str, sport: str) -> tuple[list[dict], str]:
    """Фото человека/клуба по имени через Wikidata → Commons (только если это спорт) и его английское имя."""
    found = _get(WD, action="wbsearchentities", format="json", search=q, language="ru", uselang="ru", limit=6)
    ids = [x["id"] for x in found.get("search", [])]
    if not ids:
        found = _get(WD, action="wbsearchentities", format="json", search=q, language="en", limit=6)
        ids = [x["id"] for x in found.get("search", [])]
    if not ids:
        return [], ""
    ents = _get(WD, action="wbgetentities", format="json", ids="|".join(ids), props="claims|descriptions|labels",
                languages="ru|en").get("entities", {})
    words = [w.lower()[:5] for w in re.findall(r"\w{3,}", q)]
    for eid in ids:   # по порядку релевантности поиска
        e = ents.get(eid) or {}
        desc = " ".join(d.get("value", "") for d in e.get("descriptions", {}).values()).lower()
        label = " ".join(lb.get("value", "") for lb in e.get("labels", {}).values()).lower()
        if not any(s in desc for s in SPORTY) or not all(w in label for w in words):
            continue
        en = (e.get("labels", {}).get("en") or {}).get("value", "")
        files = _commons_files(e)
        return (_commons_info(files, 250, 250) if files else []), en   # портрет может быть небольшим — карточка покажет его рамкой
    return [], ""


def _commons_search(q: str, offset: int = 0, must: tuple = ()) -> list[dict]:
    """Поиск фото по всей Wikimedia Commons (миллионы свободных фото); must — слова, одно из которых есть в названии файла."""
    r = _get(COMMONS, action="query", format="json", list="search", srnamespace=6, srlimit=30, sroffset=offset,
             srsearch=f"{q} filetype:bitmap")
    files = [x["title"].split(":", 1)[1] for x in r.get("query", {}).get("search", [])]
    files = [f for f in files if re.search(r"\.(jpe?g|png|webp)$", f, re.I)]
    if must:   # поиск по тексту описания бывает неточным — проверяем название самого файла
        files = [f for f in files if any(w in f.lower() for w in must)]
    return _commons_info(files) if files else []


TOPIC = {"football": ["football match", "soccer stadium", "football fans stadium", "football players match"],
         "hockey": ["ice hockey game", "KHL hockey", "NHL game", "ice hockey arena"],
         "basketball": ["basketball game", "NBA game", "basketball arena", "EuroLeague basketball"],
         "tennis": ["tennis match", "tennis court", "ATP tennis", "WTA tennis"],
         "esports": ["esports tournament", "esports arena", "gaming tournament", "The International Dota 2"]}


MUST = {"football": ("football", "soccer", "fc", "stadium", "match", "futbol", "fútbol", "calcio", "fußball"),
        "hockey": ("hockey", "khl", "nhl", "iihf"),
        "basketball": ("basketball", "nba", "euroleague", "basket"),
        "tennis": ("tennis", "atp", "wta", "open"),
        "esports": ("esports", "e-sports", "dota", "counter-strike", "cs2", "csgo", "major", "iem", "league of legends", "the international")}


def find(title: str, text: str = "", sport: str = "", used: list | None = None) -> dict | None:
    """Лучшее неповторяющееся фото по теме: {'url', 'author', 'license', 'source'} или None."""
    used = set(used or [])
    fresh = lambda xs: [x for x in xs if x.get("url") and x["url"] not in used]   # noqa: E731
    for q in names(title, text)[:4]:   # герой новости: Wikidata → его фото и альбом на Commons
        info, en = _wikidata(q, sport)
        pool = fresh(info)
        if not pool and en:            # своих фото нет или все уже были — ищем по английскому имени
            pool = fresh(_commons_search(en, must=(en.split()[-1].lower(),)))   # фамилия — в названии файла
        if pool:
            print(f"  фото: {q} — Wikimedia Commons ({len(pool)} шт.)")
            # главное фото из карточки (портрет) — если ещё не было; иначе любое новое из альбома
            return pool[0] if info and pool[0] is info[0] else random.choice(pool[:8])
    for _ in range(3):                 # тема: случайная выборка фото этого вида спорта — без повторов
        pool = fresh(_commons_search(random.choice(TOPIC.get(sport, TOPIC["football"])), random.randrange(0, 150, 30),
                                     must=MUST.get(sport, ())))
        if pool:
            print("  фото: по теме — Wikimedia Commons")
            return random.choice(pool)
    return None


def remember(state: dict, url: str | None) -> None:
    if url:
        used = state.setdefault("img_used", [])
        used.append(url)
        del used[:-KEEP]


def credit(ph: dict | None) -> str:
    """Подпись для картинки: «Фото: автор · лицензия»."""
    if not ph:
        return ""
    who = " · ".join(x for x in (ph.get("author"), ph.get("license")) if x)
    return f"Фото: {who}" if who else ""
