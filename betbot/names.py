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
    # клубы, которые Wikidata путает с городами или находит без русского названия
    "Atlas": "Атлас",
    "Goztepe": "Гёзтепе",
    "Göztepe": "Гёзтепе",
    "Monterrey": "Монтеррей",
    "Estoril": "Эшторил",
    "Rodina Moscow": "Родина",
    "Krasnodar": "Краснодар",
    "PSV Eindhoven": "ПСВ",
    "PSV": "ПСВ",
    "Deportivo Riestra": "Депортиво Риестра",
    "Talleres": "Тальерес",
    "San Lorenzo": "Сан-Лоренсо",
    "Instituto": "Институто",
    "Estudiantes": "Эстудиантес",
    "Estudiantes de La Plata": "Эстудиантес",
    "Coritiba": "Коритиба",
    "Defensa y Justicia": "Дефенса и Хустисия",
    "Belgrano": "Бельграно",
    "Godoy Cruz": "Годой Крус",
    "Lanús": "Ланус",
    "Banfield": "Банфилд",
    "Rosario Central": "Росарио Сентраль",
    "Newell's Old Boys": "Ньюэллс Олд Бойз",
    "Vélez Sarsfield": "Велес Сарсфилд",
    "Velez Sarsfield": "Велес Сарсфилд",
    "Argentinos Juniors": "Архентинос Хуниорс",
    "Independiente": "Индепендьенте",
    "Racing Club": "Расинг",
    "Boca Juniors": "Бока Хуниорс",
    "River Plate": "Ривер Плейт",
    "Huracán": "Уракан",
    "Unión": "Унион",
    "Toluca": "Толука",
    "Cruz Azul": "Крус Асуль",
    "América": "Америка",
    "Club América": "Америка",
    "Santos Laguna": "Сантос Лагуна",
    "León": "Леон",
    "Necaxa": "Некакса",
    "Pachuca": "Пачука",
    "Kasimpasa": "Касымпаша",
    "Kasımpaşa": "Касымпаша",
    "Samsunspor": "Самсунспор",
    "Kayserispor": "Кайсериспор",
    "Gaziantep FK": "Газиантеп",
    "Alanyaspor": "Аланьяспор",
    "Antalyaspor": "Антальяспор",
    "Eyupspor": "Эюпспор",
    "Eyüpspor": "Эюпспор",
    "Rizespor": "Ризеспор",
    "Kocaelispor": "Коджаэлиспор",
    "Genclerbirligi": "Генчлербирлиги",
    "Gençlerbirliği": "Генчлербирлиги",
    "Akron Tolyatti": "Акрон",
    "Rostov": "Ростов",
    "Orenburg": "Оренбург",
    "Pari NN": "Пари НН",
    "Dynamo Makhachkala": "Динамо Махачкала",
    "Baltika": "Балтика",
    "Sochi": "Сочи",
    "AZ Alkmaar": "АЗ",
    "Twente": "Твенте",
    "Utrecht": "Утрехт",
    "Heerenveen": "Херенвен",
    "NEC": "НЕК",
    "Sparta Rotterdam": "Спарта Роттердам",
    "Fortuna Sittard": "Фортуна Ситтард",
    "Heracles Almelo": "Хераклес",
    "Arouca": "Арока",
    "Gil Vicente": "Жил Висенте",
    "Famalicão": "Фамаликан",
    "Santa Clara": "Санта-Клара",
    "Rio Ave": "Риу Аве",
    "Vitória de Guimarães": "Витория Гимарайнш",
    "Moreirense": "Морейренсе",
    "Casa Pia": "Каза Пия",
    "Estrela": "Эштрела",
    "Nacional": "Насьонал",
    "AVS": "АВС",
    "Tondela": "Тондела",
    "Erzurum BB": "Эрзурумспор",
    "Barnet": "Барнет",
    "Barrow": "Барроу",
    "Boreham Wood": "Борэм Вуд",
    "Bromley": "Бромли",
    "Gateshead": "Гейтсхед",
    "Southend United": "Саутенд Юнайтед",
    "Tamworth": "Тамуэрт",
    "Woking": "Уокинг",
    "Worthing": "Уэртинг",
    "Yeovil Town": "Йовил Таун",
    "Hartlepool United": "Хартлпул Юнайтед",
    "Kidderminster Harriers": "Киддерминстер",
    "Forest Green Rovers": "Форест Грин Роверс",
    "Boston United": "Бостон Юнайтед",
    "Wealdstone": "Уилдстон",
    "Real Ávila": "Реал Авила",
    "Rayo Majadahonda": "Райо Махадаонда",
    "CD Extremadura": "Эстремадура",
    "Don Benito": "Дон Бенито",
    "Sant Andreu": "Сант-Андреу",
    "Manresa": "Манреса",
    "Alcalá": "Алькала",
    "Abha": "Абха",
    "Al Khaleej": "Аль-Халидж",
    "Internacional de Bogotá": "Интернасьональ Богота",
    "Estudiantes de Río Cuarto": "Эстудиантес Рио-Куарто",
    "Sarmiento (Junín)": "Сармьенто",
    "Atlético Grau": "Атлетико Грау",
    "Deportivo Garcilaso": "Депортиво Гарсиласо",
    "Juan Pablo II": "Хуан Пабло II",
    "IF Brommapojkarna": "Броммапойкарна",
    "Excelsior Maassluis": "Эксельсиор Масслёйс",
    "Atlético Tordesillas": "Атлетико Тордесильяс",
    "Ciudad De Lucena": "Сьюдад-де-Лусена",
    "Mijas Las Lagunas": "Михас Лас-Лагунас",
    "Sporting de Alcázar": "Спортинг Алькасар",
    "Koninklijke HFC": "ХФК Харлем",
    "Rijnsburgse Boys": "Рейнсбургсе Бойз",
    "Kloetinge": "Клутинге",
    "Penicuik": "Пеникуик",
    "Adelaide 36ers": "Аделаида Сиксерс",
    "Brisbane Bullets": "Брисбен Буллетс",
    "Cairns Taipans": "Кэрнс Тайпанс",
    "Perth Wildcats": "Перт Уайлдкэтс",
    "Sydney Kings": "Сидней Кингз",
    "Tasmania JackJumpers": "Тасмания Джекджамперс",
    "Atalanta": "Аталанта",
    "Fiorentina": "Фиорентина",
    "Torino": "Торино",
    "Como": "Комо",
    "Cremonese": "Кремонезе",
    "Empoli": "Эмполи",
    "Parma": "Парма",
    "Sampdoria": "Сампдория",
    "Cesena": "Чезена",
    "Padova": "Падова",
    "Mantova": "Мантова",
    "Sudtirol": "Зюйдтироль",
    "Virtus Entella": "Виртус Энтелла",
    "Genoa": "Дженоа",
    "Udinese": "Удинезе",
    "Lecce": "Лечче",
    "Cagliari": "Кальяри",
    "Hellas Verona": "Верона",
    "Sassuolo": "Сассуоло",
    "Pisa": "Пиза",
    "Monza": "Монца",
    "Venezia": "Венеция",
    "Palermo": "Палермо",
    "Valencia": "Валенсия",
    "Villarreal": "Вильярреал",
    "Espanyol": "Эспаньол",
    "Rayo Vallecano": "Райо Вальекано",
    "Las Palmas": "Лас-Пальмас",
    "Málaga": "Малага",
    "Real Zaragoza": "Сарагоса",
    "Sevilla": "Севилья",
    "Real Betis": "Бетис",
    "Real Sociedad": "Реал Сосьедад",
    "Athletic Club": "Атлетик",
    "Celta Vigo": "Сельта",
    "Getafe": "Хетафе",
    "Osasuna": "Осасуна",
    "Mallorca": "Мальорка",
    "Girona": "Жирона",
    "Alavés": "Алавес",
    "Elche": "Эльче",
    "Levante": "Леванте",
    "Real Oviedo": "Овьедо",
    "Cultural Leonesa": "Культураль Леонеса",
    "Aston Villa": "Астон Вилла",
    "Brentford": "Брентфорд",
    "Wrexham": "Рексем",
    "Wigan Athletic": "Уиган",
    "Celtic": "Селтик",
    "Aberdeen": "Абердин",
    "Kilmarnock": "Килмарнок",
    "Falkirk": "Фалкерк",
    "Oxford United": "Оксфорд Юнайтед",
    "Bradford City": "Брэдфорд Сити",
    "Doncaster Rovers": "Донкастер",
    "Peterborough United": "Питерборо",
    "Cambridge United": "Кембридж Юнайтед",
    "1. FC Union Berlin": "Унион Берлин",
    "1. FC Nürnberg": "Нюрнберг",
    "Hannover 96": "Ганновер",
    "Holstein Kiel": "Хольштайн Киль",
    "Karlsruher SC": "Карлсруэ",
    "SV Darmstadt 98": "Дармштадт",
    "Nice": "Ницца",
    "Le Havre AC": "Гавр",
    "Go Ahead Eagles": "Гоу Эхед Иглз",
    "Willem II": "Виллем II",
    "Konyaspor": "Коньяспор",
    "Bahia": "Баия",
    "Botafogo": "Ботафого",
    "Flamengo": "Фламенго",
    "Fluminense": "Флуминенсе",
    "Grêmio": "Гремио",
    "Palmeiras": "Палмейрас",
    "Santos": "Сантос",
    "Vasco da Gama": "Васко да Гама",
    "Red Bull Bragantino": "Брагантино",
    "Remo": "Ремо",
    "Platense": "Платенсе",
    "Tigre": "Тигре",
    "Atlético Tucumán": "Атлетико Тукуман",
    "Gimnasia La Plata": "Химнасия Ла-Плата",
    "Universidad Católica": "Универсидад Католика",
    "San Diego FC": "Сан-Диего",
    "Red Bull New York": "Нью-Йорк Ред Буллз",
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
        if w.endswith("ie") and res.endswith("ие") and len(w) > 3:  # Norrie → Норри, Annie → Анни
            res = res[:-2] + "и"
        if w.endswith("ic") and res.endswith("ик") and len(w) > 4:  # Djokovic → Джокович (сербские/хорватские фамилии)
            res = res[:-2] + "ич"
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
        for k, v in list(_cache.items()):
            # старые записи, похожие на транслит («Ввсб»), переспрашиваем у Wikidata: настоящие русские
            # названия («Арсенал») вернутся, а для клубов без них останется оригинал латиницей («VVSB»)
            orig = k.split(":", 1)[-1]
            if v in (translit(orig), f"Сборная {translit(orig)}") and orig not in FIXED:
                del _cache[k]
                bad.append(k)
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
        return name  # Wikidata не ответила — пока латиницей, попробуем ещё раз в следующий запуск
    # русского названия нет — оставляем оригинал латиницей: транслит клубов вроде «VVSB» даёт кашу
    cache[key] = ru or (f"Сборная {name}" if national else name)
    _dirty = True
    time.sleep(0.3)
    return cache[key]


def player(name: str) -> str:
    return translit(name)


def tennis_player(name: str) -> str:
    """Русское имя теннисиста из Wikidata («Мария Тимофеева», «Сунь Синьжань»), иначе транслит."""
    global _dirty
    cache = _load()
    key = f"tennis:{name}"
    if key in cache and len(cache[key].split()) >= min(2, len(name.split())):
        return cache[key]  # запись из одного слова («Новак») — старая ошибка, переспрашиваем
    res = _api(action="wbsearchentities", search=name, language="en", type="item", limit=7)
    if res is None:
        return translit(name)  # Wikidata не ответила или лимит времени исчерпан — попробуем в следующий раз
    ids = [x["id"] for x in res.get("search", []) if "tennis" in (x.get("description") or "").lower()]
    label = None
    if ids:
        ent = _api(action="wbgetentities", ids=ids[0], props="labels", languages="ru")
        label = ((ent or {}).get("entities", {}).get(ids[0], {}).get("labels", {}).get("ru") or {}).get("value")
    ru = _person(re.sub(r"\s*\(.*?\)", "", label)) if label else ""
    cache[key] = ru if len(ru.split()) >= min(2, len(name.split())) else translit(name)
    _dirty = True
    return cache[key]


def _person(label: str) -> str:
    """«Тимофеева, Мария Глебовна» → «Мария Тимофеева»; «Даниил Сергеевич Медведев» → «Даниил Медведев»."""
    if "," in label:
        last, first = (x.strip() for x in label.split(",", 1))
        label = f"{first.split()[0]} {last}" if first else last
    words = label.split()
    if len(words) >= 3:  # отчество — только среднее слово из трёх («Даниил Сергеевич Медведев»), а не фамилия «Джокович»
        words = [w for i, w in enumerate(words) if not (0 < i < len(words) - 1 and re.search(r"(вич|вна|ична|инична)$", w))]
    return " ".join(words)


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
