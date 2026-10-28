"""Русские названия команд и игроков.

Команды: Wikidata (бесплатно) → кэш в data/names_ru.json, иначе транслитерация.
Игроки: транслитерация (имён тысячи, а словаря бесплатно нет).
"""
import difflib
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

CACHE = Path(__file__).resolve().parent.parent / "data" / "names_ru.json"
API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "betbot/1.0 (football predictions telegram bot)"}
CLUB_WORDS = ("football club", "soccer club", "association football", "soccer team", "football team",
              "ice hockey team", "hockey team", "hockey club", "basketball team", "basketball club")

_cache: dict | None = None
_dirty = False

# Названия, которые Wikidata даёт неудобно длинными или непривычными
FIXED = {
    "Internazionale": "Интер", "Inter Milan": "Интер", "AC Milan": "Милан", "AS Roma": "Рома",
    "Paris Saint-Germain": "ПСЖ", "Bayern Munich": "Бавария", "Manchester United": "Манчестер Юнайтед",
    "Manchester City": "Манчестер Сити", "Atlético Madrid": "Атлетико", "Atletico Madrid": "Атлетико",
    "Borussia Dortmund": "Боруссия Д", "Borussia Mönchengladbach": "Боруссия М",
    "Bayer Leverkusen": "Байер", "RB Leipzig": "РБ Лейпциг", "Tottenham Hotspur": "Тоттенхэм",
    "Wolverhampton Wanderers": "Вулверхэмптон", "Brighton & Hove Albion": "Брайтон",
    "Newcastle United": "Ньюкасл", "West Ham United": "Вест Хэм", "Nottingham Forest": "Ноттингем Форест",
    "AFC Bournemouth": "Борнмут", "Real Madrid": "Реал Мадрид", "Barcelona": "Барселона",
    "Juventus": "Ювентус", "Napoli": "Наполи", "Lazio": "Лацио", "Zenit St Petersburg": "Зенит",
    "Spartak Moscow": "Спартак", "CSKA Moscow": "ЦСКА", "Dynamo Moscow": "Динамо", "Lokomotiv Moscow": "Локомотив",
    # NHL
    "Anaheim Ducks": "Анахайм", "Boston Bruins": "Бостон", "Buffalo Sabres": "Баффало", "Calgary Flames": "Калгари",
    "Carolina Hurricanes": "Каролина", "Chicago Blackhawks": "Чикаго", "Colorado Avalanche": "Колорадо",
    "Columbus Blue Jackets": "Коламбус", "Dallas Stars": "Даллас", "Detroit Red Wings": "Детройт",
    "Edmonton Oilers": "Эдмонтон", "Florida Panthers": "Флорида", "Los Angeles Kings": "Лос-Анджелес",
    "Minnesota Wild": "Миннесота", "Montreal Canadiens": "Монреаль", "Nashville Predators": "Нэшвилл",
    "New Jersey Devils": "Нью-Джерси", "New York Islanders": "Айлендерс", "New York Rangers": "Рейнджерс",
    "Ottawa Senators": "Оттава", "Philadelphia Flyers": "Филадельфия", "Pittsburgh Penguins": "Питтсбург",
    "San Jose Sharks": "Сан-Хосе", "Seattle Kraken": "Сиэтл", "St. Louis Blues": "Сент-Луис",
    "Tampa Bay Lightning": "Тампа-Бэй", "Toronto Maple Leafs": "Торонто", "Utah Mammoth": "Юта",
    "Utah Hockey Club": "Юта", "Vancouver Canucks": "Ванкувер", "Vegas Golden Knights": "Вегас",
    "Washington Capitals": "Вашингтон", "Winnipeg Jets": "Виннипег",
    # NBA
    "Atlanta Hawks": "Атланта Хокс", "Boston Celtics": "Бостон Селтикс", "Brooklyn Nets": "Бруклин Нетс",
    "Charlotte Hornets": "Шарлотт Хорнетс", "Chicago Bulls": "Чикаго Буллз", "Cleveland Cavaliers": "Кливленд",
    "Dallas Mavericks": "Даллас Маверикс", "Denver Nuggets": "Денвер Наггетс", "Detroit Pistons": "Детройт Пистонс",
    "Golden State Warriors": "Голден Стэйт", "Houston Rockets": "Хьюстон Рокетс", "Indiana Pacers": "Индиана Пэйсерс",
    "LA Clippers": "Клипперс", "Los Angeles Clippers": "Клипперс", "Los Angeles Lakers": "Лейкерс",
    "Memphis Grizzlies": "Мемфис Гриззлис", "Miami Heat": "Майами Хит", "Milwaukee Bucks": "Милуоки Бакс",
    "Minnesota Timberwolves": "Миннесота Тимбервулвз", "New Orleans Pelicans": "Нью-Орлеан Пеликанс",
    "New York Knicks": "Нью-Йорк Никс", "Oklahoma City Thunder": "Оклахома-Сити Тандер", "Orlando Magic": "Орландо Мэджик",
    "Philadelphia 76ers": "Филадельфия Сиксерс", "Phoenix Suns": "Финикс Санз", "Portland Trail Blazers": "Портленд",
    "Sacramento Kings": "Сакраменто Кингз", "San Antonio Spurs": "Сан-Антонио Сперс", "Toronto Raptors": "Торонто Рэпторс",
    "Utah Jazz": "Юта Джаз", "Washington Wizards": "Вашингтон Уизардс",
}

_TR = [("shch", "щ"), ("sch", "ш"), ("tch", "ч"), ("ey", "ей"), ("ay", "эй"), ("ce", "се"), ("ci", "си"),
       ("cy", "си"), ("ch", "ч"), ("sh", "ш"), ("zh", "ж"), ("kh", "х"),
       ("ts", "ц"), ("yu", "ю"), ("ya", "я"), ("yo", "ё"), ("ee", "и"), ("oo", "у"), ("ph", "ф"),
       ("th", "т"), ("ck", "к"), ("qu", "кв"), ("ou", "у"), ("w", "у"), ("x", "кс"), ("j", "ж"),
       ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"), ("h", "х"),
       ("i", "и"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "к"),
       ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("y", "й"), ("z", "з")]


def translit(text: str) -> str:
    """Простая транслитерация латиницы в кириллицу (для игроков и команд без перевода)."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    out = []
    for word in re.split(r"(\W+)", s):
        w, res, i = word.lower(), "", 0
        while i < len(w):
            if w[i] == "y" and i > 0 and w[i - 1] not in "aeiou":  # y после согласной звучит как «и»
                res += "и"
                i += 1
                continue
            for a, b in _TR:
                if w.startswith(a, i):
                    res += b
                    i += len(a)
                    break
            else:
                res += w[i]
                i += 1
        out.append(res[:1].upper() + res[1:] if word[:1].isupper() else res)
    return "".join(out)


RESERVE = re.compile(r"(\bII\b|\bB\b|U-?\d{2}|\(жен|женск|молод|дубл|резерв)", re.IGNORECASE)


def _reserve_mixup(name: str, label: str) -> bool:
    """Wikidata иногда подсовывает дубль/молодёжку/женскую команду вместо основной."""
    return bool(RESERVE.search(label)) and not RESERVE.search(name.replace("Women", "(жен"))


def _load() -> dict:
    global _cache, _dirty
    if _cache is None:
        _cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        bad = [k for k, v in _cache.items() if _reserve_mixup(k.split(":", 1)[-1], v)]
        for k in bad:  # чистим уже сохранённые ошибки — их переведём заново
            del _cache[k]
        _dirty = _dirty or bool(bad)
    return _cache


def save() -> None:
    if _dirty:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_load(), ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


BUDGET = 40.0  # секунд на поиск новых названий за один запуск — чтобы бот не ждал Wikidata вместо постов
_spent = 0.0


def _api(**params) -> dict | None:
    global _spent
    if _spent >= BUDGET:
        return None
    started = time.time()
    try:
        r = requests.get(API, params={**params, "format": "json"}, headers=HEADERS, timeout=8)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
    except Exception:
        pass
    finally:
        _spent += time.time() - started
    return None


def _wikidata(name: str, national: bool = False) -> str | None:
    queries = [f"{name} national football team"] if national else [name, f"{name} FC"]
    words = ("national football team", "national association football team", "national soccer team") \
        if national else CLUB_WORDS
    for query in queries:
        res = _api(action="wbsearchentities", search=query, language="en", type="item", limit=10)
        if res is None:
            raise ConnectionError("wikidata недоступна")
        ids = [x["id"] for x in res.get("search", [])
               if any(k in ((x.get("description") or "") + " " + (x.get("label") or "")).lower() for k in words)]
        if ids:
            ent = _api(action="wbgetentities", ids="|".join(ids[:3]), props="labels", languages="ru")
            for i in ids[:3]:
                label = ((ent or {}).get("entities", {}).get(i, {}).get("labels", {}).get("ru") or {}).get("value")
                if label and not _reserve_mixup(name, label):
                    label = re.sub(r"\s*\(.*?\)", "", label)  # «Арсенал (Лондон)» → «Арсенал»
                    label = re.sub(r"\s+по футболу$", "", label)  # «Сборная Германии по футболу»
                    return label[:1].upper() + label[1:]
        time.sleep(0.5)
    return None


def team(name: str, national: bool = False) -> str:
    """Русское название команды (national=True — сборная страны)."""
    global _dirty
    if name in FIXED and not national:
        return FIXED[name]
    cache = _load()
    key = f"national:{name}" if national else name
    if key in cache:
        return cache[key]
    try:
        ru = _wikidata(name, national)
    except ConnectionError:
        return translit(name)  # попробуем ещё раз в следующий запуск
    cache[key] = ru or (f"Сборная {translit(name)}" if national else translit(name))
    _dirty = True
    time.sleep(0.3)
    return cache[key]


def player(name: str) -> str:
    return translit(name)


# ── сопоставление названий из разных источников ─────────────────────────────

_STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "cd", "ud", "rc", "sv", "fk", "if", "bk",
         "club", "de", "the", "calcio", "1"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _STOP)


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if a and b and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()
