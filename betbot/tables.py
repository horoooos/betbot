"""Турнирные таблицы и рейтинги — каждый день в 12:00 МСК, по очереди для всех категорий.

  футбол — таблицы лиг (ESPN); хоккей и баскетбол — таблицы конференций NHL/NBA (ESPN);
  теннис и киберспорт — топ-10 по рейтингу Эло бота (ESPN/PandaScore, история за год).
"""
from html import escape

import pandas as pd

from . import card, esports, names, sports, telegram
from .espn import _get
from .leagues import ALL, title

STANDINGS = "https://site.api.espn.com/apis/v2/sports/{path}/standings"
ROTATION = ["E0", "NHL", "SP1", "NBA", "I1", "ATP", "D1", "CS2", "F1", "WTA", "RUS", "DOTA", "N1", "P1", "T1"]
HOUR = 12


def _stat(stats: list, *keys):
    for k in keys:
        for s in stats:
            if s.get("abbreviation") == k or s.get("name") == k:
                return s.get("displayValue")
    return ""


def _football(code: str) -> tuple[bytes, str] | None:
    data = _get(STANDINGS.format(path=f"soccer/{ALL[code][3]}")) or {}
    groups = data.get("children") or [data]
    entries = (groups[0].get("standings") or {}).get("entries", [])
    if not entries:
        return None
    rows = []
    for e in entries:
        st = e.get("stats", [])
        rows.append((_stat(st, "R", "rank"), names.team(e["team"]["displayName"]), _stat(st, "GP"),
                     _stat(st, "GD"), _stat(st, "P", "points")))
    rows.sort(key=lambda r: int(r[0] or 99))
    text = [f"📊 <b>ТУРНИРНАЯ ТАБЛИЦА · {escape(title(code)).upper()}</b>\n"]
    for r in rows:
        text.append(f"{r[0]:>2}. {escape(r[1])} — <b>{r[4]}</b> очк. ({r[2]} игр, разница {r[3]})")
    png = card.table_card("Турнирная таблица", title(code).split(" ", 1)[-1], ("#", "Команда", "И", "Р", "О"), rows)
    return png, "\n".join(text)


def _us(code: str) -> tuple[bytes, str] | None:
    data = _get(STANDINGS.format(path=sports.LEAGUES[code][3])) or {}
    confs = data.get("children") or []
    if not confs:
        return None
    hockey = code == "NHL"
    text = [f"📊 <b>ТАБЛИЦА {code}</b>"]
    best = []
    for conf in confs:
        entries = (conf.get("standings") or {}).get("entries", [])
        rows = []
        for e in entries:
            st = e.get("stats", [])
            team = names.team(e["team"]["displayName"])
            w, l = _stat(st, "W", "wins"), _stat(st, "L", "losses")
            pts = _stat(st, "PTS", "points") if hockey else _stat(st, "PCT", "winPercent")
            rows.append([team, f"{w}-{l}", pts])
        rows.sort(key=lambda r: float(str(r[2]).replace("-", "0") or 0), reverse=True)
        name = "Восток" if "East" in conf.get("name", "") else "Запад" if "West" in conf.get("name", "") else conf.get("name", "")
        text.append(f"\n<b>{name}</b>")
        for i, r in enumerate(rows[:10], 1):
            text.append(f"{i:>2}. {escape(r[0])} — {r[1]}" + (f", <b>{r[2]}</b> очк." if hockey else f" ({r[2]})"))
        best += rows
    best.sort(key=lambda r: float(str(r[2]).replace("-", "0") or 0), reverse=True)
    table = [(i, r[0], r[1], r[2]) for i, r in enumerate(best[:10], 1)]
    png = card.table_card(f"Таблица {code}", "лучшие команды лиги", ("#", "Команда", "В-П", "О" if hockey else "%"), table,
                          sport="hockey" if hockey else "basketball")
    return png, "\n".join(text)


def _elo(code: str) -> tuple[bytes, str] | None:
    sport = sports.LEAGUES[code][4]
    hist = sports.tennis_history(refresh=False) if sport == "tennis" else esports.history(refresh=False)
    hist = [m for m in hist if m["div"] == code]
    if not hist:
        return None
    rating = sports.elo(hist)
    nm = {p["id"]: p["name"] for m in hist for p in (m["home"], m["away"])}
    recent = pd.Timestamp.now(tz="Europe/Moscow") - pd.Timedelta(days=60)
    active = {p["id"] for m in hist if pd.Timestamp(m["kickoff"]) > recent for p in (m["home"], m["away"])}
    top = sorted(((k, v) for k, v in rating.items() if v[1] >= 10 and k in active), key=lambda x: -x[1][0])[:10]
    show = (lambda n: names.player(n)) if sport == "tennis" else (lambda n: n)
    rows = [(i, show(nm[k]), v[1], f"{v[0]:.0f}") for i, (k, v) in enumerate(top, 1)]
    what = "игроков" if sport == "tennis" else "команд"
    text = [f"🏆 <b>РЕЙТИНГ {what.upper()} · {code} (по версии бота)</b>",
            "<i>Рейтинг Эло по всем матчам за год: чем выше — тем сильнее. По нему бот и считает прогнозы.</i>\n"]
    text += [f"{r[0]:>2}. {escape(r[1])} — <b>{r[3]}</b> ({r[2]} матчей)" for r in rows]
    png = card.table_card(f"Рейтинг {code}", f"топ-10 {what} по версии бота", ("#", "Имя" if sport == "tennis" else "Команда",
                          "Матчи", "Эло"), rows, sport=sport)
    return png, "\n".join(text)


def run(state: dict, now: pd.Timestamp, brand: str) -> None:
    if now.hour != HOUR or state.get("table_day") == str(now.date()):
        return
    state["table_day"] = str(now.date())
    start = int(now.strftime("%j"))
    for shift in range(len(ROTATION)):  # если таблицы сегодня нет (межсезонье, нет ключа) — берём следующую
        code = ROTATION[(start + shift) % len(ROTATION)]
        try:
            if code in ALL:
                res = _football(code)
            elif sports.LEAGUES[code][4] in ("hockey", "basketball"):
                res = _us(code)
            else:
                res = _elo(code)
        except Exception as e:
            print(f"  ! таблица {code}: {e}")
            res = None
        if res:
            png, text = res
            if len(text) <= telegram.CAPTION_LIMIT:
                telegram.send_photo(png, text)
            else:
                head, _, rest = text.partition("\n")
                mid = telegram.send_photo(png, head)
                telegram.send(rest, reply_to=mid, silent=True)
            print(f"Таблица дня: {code}")
            return
