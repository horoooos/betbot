"""Live-посты: «матч начался» и каждый гол/шайба/карта — с картинкой, ответом к прогнозу на матч.

Чтобы канал не утонул в сотнях постов, live включён только для турниров из LIVE (их легко расширить).
Бот проверяет матчи каждые 5 минут, поэтому пост о голе выходит с задержкой до 5 минут.
"""
import json
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from . import card, names, sports, telegram, texts
from .leagues import title as league_title

LIVE = {
    # футбол: топ-лиги, еврокубки, все национальные кубки и турниры сборных
    "E0", "SP1", "I1", "D1", "F1", "RUS", "N1", "P1", "T1", "E1", "BRA", "ARG",
    "UCL", "UEL", "UECL", "UCLQ", "USC", "LIB", "SUD",
    "FAC", "ELC", "CDR", "DFB", "CIT", "CDF", "TPO", "SCC",
    "UNL", "WCQE", "WCQS", "WC", "EURO", "FRI",
    # другие виды спорта
    "NHL", "NBA", "WNBA", "ATP", "WTA", "CS2", "DOTA",
}
TRACKER = "https://horoooos.github.io/betbot/live.html"  # 3D-трекер матча (docs/live.html на GitHub Pages)
MATCHES_PAGE = "https://horoooos.github.io/betbot/matches.html"
APP_MATCHES = "https://horoooos.github.io/betbot/app.html?startapp=matches"  # то же внутри Telegram — всегда свежая версия  # все матчи дня онлайн
# В хоккее шайб много (ночью NHL — десятки постов), поэтому там только «матч начался» и итог.
WORD = {"football": ("ГОЛ!", "⚽️"), "esports": ("КАРТА!", "🎮")}
START = {"football": "все голы будут здесь", "hockey": "итог матча будет здесь",
         "basketball": "итог матча будет здесь", "tennis": "итог матча будет здесь", "esports": "результат каждой карты будет здесь"}


def _league(e: dict) -> str:
    return texts.league_plain(e["div"]) if e.get("sport", "football") == "football" else sports.league_plain(e["div"])


def _title(e: dict) -> str:
    return league_title(e["div"]) if e.get("sport", "football") == "football" else sports.title(e["div"])


def _score(e: dict) -> tuple[int, int] | None:
    if e.get("sport") == "tennis":  # в теннисе «счёт» — выигранные сеты
        return sum(e["home"].get("set_won") or []), sum(e["away"].get("set_won") or [])
    try:
        return int(e["home"]["score"] or 0), int(e["away"]["score"] or 0)
    except (TypeError, ValueError):
        return None


def _tracker(e: dict, sport: str, h: str, a: str) -> tuple[str, str] | None:
    """Кнопка «Смотреть матч в 3D»: живой трекер на сайте (футбол, хоккей, баскетбол, теннис)."""
    if sport == "football":
        path = f"soccer/{e['slug']}" if e.get("slug") else ""
    else:
        path = sports.LEAGUES.get(e["div"], ("",) * 5)[3]
    if not path or sport == "esports":
        return None
    return ("📺 Смотреть матч онлайн", f"{TRACKER}?" + urlencode({"s": sport, "p": path, "e": e["id"], "h": h, "a": a}))


BB_SPORT = "https://betboom.ru/sport/"   # обычная ссылка на линию BetBoom (реферальная — только на главной сайта)


# Мини-приложение Telegram: кнопки в канале открывают сайт прямо внутри Telegram (t.me/<бот>?startapp=…).
# Включается в data/miniapp.json ({"on": true}) — после настройки «Main Mini App» в BotFather. Бот этот файл не пишет.
MINIAPP_FILE = Path(__file__).resolve().parent.parent / "data" / "miniapp.json"
_bot_name: dict = {}


def miniapp_bot() -> str | None:
    """Имя бота, если мини-приложение включено; иначе None (кнопки ведут на сайт в браузере)."""
    try:
        if not json.loads(MINIAPP_FILE.read_text(encoding="utf-8")).get("on"):
            return None
    except (OSError, ValueError):
        return None
    if "v" not in _bot_name:
        try:
            _bot_name["v"] = telegram._call("getMe", chat_id=None).get("username")
        except Exception as ex:
            print(f"  ! мини-приложение: не узнали имя бота: {ex}")
            _bot_name["v"] = None
    return _bot_name["v"]


def buttons(e: dict, sport: str, h: str, a: str) -> list[tuple[str, str]]:
    """Кнопки под постом о матче: этот матч онлайн + все матчи дня; отдельной строкой — сделать ставку в BetBoom."""
    b = _tracker(e, sport, h, a)
    bot = miniapp_bot()
    if bot:   # внутри Telegram, без браузера
        watch, allm = f"https://t.me/{bot}?startapp=m{e['id']}", f"https://t.me/{bot}?startapp=matches"
    else:
        watch, allm = (b[1] if b else None), MATCHES_PAGE
    row = [("📺 Смотреть онлайн", watch), ("🗂 Все матчи", allm)] if b else [("🗂 Матчи онлайн", allm)]
    from .pages import bb_search
    return row + [("💰 Сделать ставку в BetBoom", bb_search(h, sport))]


def run(store: dict, events: list[dict], reviews: dict, brand: str) -> None:
    """store — состояние live (data/live.json); reviews — ключ матча → {"msg": id поста с прогнозом, "tip": прогноз}.

    Live ведём только по матчам, на которые бот давал прогноз: всё идёт ответами в ветку этого прогноза.
    """
    for e in events:
        key = f"{e['div']}|{e['id']}"
        if e["div"] not in LIVE or "ru" not in e["home"] or (key not in reviews and key not in store):
            continue
        sport = e.get("sport", "football")
        sc = _score(e)
        st = store.get(key)
        h, a = e["home"]["ru"], e["away"]["ru"]
        if st is None:
            if e["state"] != "in" or sc is None:
                continue
            # бот мог «проснуться» уже по ходу матча — тогда старые голы не дублируем, а показываем текущий счёт
            if sum(sc) == 0:
                sub = f"Следим за игрой — {START.get(sport, 'все события будут здесь')}"
            else:
                sub = f"{'Серия идёт, по картам' if sport == 'esports' else 'Матч идёт, на табло'} {sc[0]}:{sc[1]}"
            png = card.live_card(_league(e), e["home"], e["away"], sc[0], sc[1], "МАТЧ НАЧАЛСЯ", sub, brand, sport,
                                 color=(214, 48, 49))
            rv = reviews.get(key) or {}
            tip = rv.get("tip") or {}
            tip_line = ""
            if tip:
                tip_line = (f"\n\n🎯 <b>Наш прогноз:</b> {escape(tip['label'])} · кэф {'≈' if tip.get('est') else ''}"
                            f"{tip['odds']:.2f} · ставка {tip.get('stake', 1):g}% банка\n👀 Следим вместе — итог будет здесь")
            button = buttons(e, sport, h, a)
            mid = telegram.send_photo(png, f"🔴 <b>МАТЧ НАЧАЛСЯ</b>\n{sports.EMOJI.get(sport, '⚽️')} <b>{escape(h)} — "
                                           f"{escape(a)}</b>\n🏆 {_title(e)}{tip_line}", reply_to=rv.get("msg"), button=button)
            store[key] = {"msg": mid, "hs": sc[0], "as": sc[1], "goals": len(e.get("goals") or []),
                          "kickoff": e["kickoff"]}
            print(f"  live: начался {h} — {a}")
            continue
        if sc is None or sport not in WORD:
            if sc is not None:
                st["hs"], st["as"] = sc  # счёт помним, но без отдельных постов
            continue
        prev = (st["hs"], st["as"])
        if sc == prev:
            continue
        if sum(sc) < sum(prev):  # гол отменили (VAR) — тихо обновляем счёт
            st["hs"], st["as"] = sc
            continue
        word, emoji = WORD[sport]
        if sport == "football":
            # постов ровно столько, на сколько вырос счёт: подробности голов ESPN иногда присылает с опозданием,
            # и старый гол не должен выйти второй раз; счёт в каждом посте — на момент этого гола
            details = e.get("goals") or []
            k = sum(sc) - sum(prev)
            new = details[st.get("goals", 0):][-k:]
            new = [{}] * (k - len(new)) + new
            run_sc = list(prev)
            for g in new:
                side = 0 if g.get("team") == str(e["home"]["id"]) else 1 if g.get("team") else None
                if side is None or run_sc[side] >= sc[side]:  # нет данных или не сходится — по тому, кто ещё «должен» гол
                    side = 0 if run_sc[0] < sc[0] else 1
                run_sc[side] += 1
                team = h if side == 0 else a
                who = names.player(g["player"]) if g.get("player") else ""
                tag = " (пен.)" if g.get("pen") else " (автогол)" if g.get("own") else ""
                sub = " ".join(x for x in (g.get("min", ""), who + tag, f"— {team}") if x).strip()
                png = card.live_card(_league(e), e["home"], e["away"], run_sc[0], run_sc[1], word, sub, brand, sport,
                                     color=(39, 174, 96))
                telegram.send_photo(png, f"{emoji} <b>{word} {escape(h)} {run_sc[0]}:{run_sc[1]} {escape(a)}</b>"
                                         + (f"\n{escape(sub)}" if sub else ""), reply_to=st["msg"])
            st["goals"] = max(st.get("goals", 0), len(details))
        else:
            scorer = h if sc[0] > prev[0] else a
            sub = f"{'Карту взяла' if sport == 'esports' else 'Забила'} команда {scorer}"
            png = card.live_card(_league(e), e["home"], e["away"], sc[0], sc[1], word, sub, brand, sport,
                                 color=(39, 174, 96))
            telegram.send_photo(png, f"{emoji} <b>{word} {escape(h)} {sc[0]}:{sc[1]} {escape(a)}</b>\n{escape(sub)}",
                                reply_to=st["msg"])
        st["hs"], st["as"] = sc
        print(f"  live: {word} {h} {sc[0]}:{sc[1]} {a}")


def cleanup(store: dict, now: pd.Timestamp) -> dict:
    old = now - pd.Timedelta(days=1)
    return {k: v for k, v in store.items() if pd.Timestamp(v["kickoff"]) > old}
