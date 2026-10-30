"""Live-посты: «матч начался» и каждый гол/шайба/карта — с картинкой, ответом к прогнозу на матч.

Чтобы канал не утонул в сотнях постов, live включён только для турниров из LIVE (их легко расширить).
Бот проверяет матчи каждые 5 минут, поэтому пост о голе выходит с задержкой до 5 минут.
"""
from html import escape

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
    "NHL", "NBA", "CS2", "DOTA",
}
# В хоккее шайб много (ночью NHL — десятки постов), поэтому там только «матч начался» и итог.
WORD = {"football": ("ГОЛ!", "⚽️"), "esports": ("КАРТА!", "🎮")}
START = {"football": "все голы будут здесь", "hockey": "итог матча будет здесь",
         "basketball": "итог матча будет здесь", "esports": "результат каждой карты будет здесь"}


def _league(e: dict) -> str:
    return texts.league_plain(e["div"]) if e.get("sport", "football") == "football" else sports.league_plain(e["div"])


def _title(e: dict) -> str:
    return league_title(e["div"]) if e.get("sport", "football") == "football" else sports.title(e["div"])


def _score(e: dict) -> tuple[int, int] | None:
    try:
        return int(e["home"]["score"] or 0), int(e["away"]["score"] or 0)
    except (TypeError, ValueError):
        return None


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
            mid = telegram.send_photo(png, f"🔴 <b>МАТЧ НАЧАЛСЯ</b>\n{sports.EMOJI.get(sport, '⚽️')} <b>{escape(h)} — "
                                           f"{escape(a)}</b>\n🏆 {_title(e)}{tip_line}", reply_to=rv.get("msg"))
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
            new = (e.get("goals") or [])[st.get("goals", 0):]
            for g in new or [{}]:
                team = h if g.get("team") == str(e["home"]["id"]) else a if g.get("team") else ""
                who = names.player(g["player"]) if g.get("player") else ""
                tag = " (пен.)" if g.get("pen") else " (автогол)" if g.get("own") else ""
                sub = " ".join(x for x in (g.get("min", ""), who + tag, f"— {team}" if team else "") if x).strip()
                png = card.live_card(_league(e), e["home"], e["away"], sc[0], sc[1], word, sub, brand, sport,
                                     color=(39, 174, 96))
                telegram.send_photo(png, f"{emoji} <b>{word} {escape(h)} {sc[0]}:{sc[1]} {escape(a)}</b>"
                                         + (f"\n{escape(sub)}" if sub else ""), reply_to=st["msg"])
            st["goals"] = len(e.get("goals") or [])
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
