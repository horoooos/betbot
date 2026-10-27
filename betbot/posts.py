"""Оформление постов для Telegram (HTML-разметка)."""
import difflib
import re
import unicodedata
from html import escape

import pandas as pd

from .engine import SIDE_NAMES
from .leagues import ORDER, title

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
LINE = "➖➖➖➖➖➖➖➖➖➖"
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"


def bar(p: float, width: int = 10) -> str:
    n = round(p * width)
    return "█" * n + "░" * (width - n)


def pct(p: float) -> str:
    return f"{100 * p:.0f}%"


def when(ts: pd.Timestamp) -> str:
    return f"{DAYS[ts.weekday()]} {ts:%d.%m} · {ts:%H:%M}"


def day_title(ts: pd.Timestamp) -> str:
    return f"{ts.day} {MONTHS[ts.month - 1]}"


def confidence(p: float) -> str:
    if p >= 0.65:
        return "🔥 Уверенный фаворит"
    if p >= 0.5:
        return "✅ Фаворит"
    if p >= 0.4:
        return "⚖️ Небольшой перевес"
    return "🎲 Равная игра"


def match_card(r, picks: pd.DataFrame) -> str:
    h, d, a = r.pH, r.pD, r.pA
    fav = max((h, f"П1 · {escape(r.HomeTeam)}"), (d, "Ничья"), (a, f"П2 · {escape(r.AwayTeam)}"))
    lines = [
        f"⏰ <b>{when(r.Kickoff)}</b> МСК",
        f"🏟 <b>{escape(r.HomeTeam)}</b>  —  <b>{escape(r.AwayTeam)}</b>",
        "<code>"
        f"П1 {bar(h)} {pct(h):>4}\n"
        f"Х  {bar(d)} {pct(d):>4}\n"
        f"П2 {bar(a)} {pct(a):>4}"
        "</code>",
        f"⚽️ xG <b>{r.m_xgH:.1f} : {r.m_xgA:.1f}</b> · Счёт: <b>{r.m_score}</b>"
        + (f" · ТБ 2.5: <b>{pct(r.pO)}</b>" if pd.notna(r.pO) else ""),
        f"{confidence(fav[0])}: {fav[1]}",
    ]
    mp = picks[(picks["HomeTeam"] == r.HomeTeam) & (picks["AwayTeam"] == r.AwayTeam)] if len(picks) else picks
    for p in mp.itertuples():
        lines.append(f"💎 <b>VALUE: {SIDE_NAMES[p.side]} @ {p.odds:.2f}</b> "
                     f"(вероятность {pct(p.prob)}, перевес +{100 * p.edge:.1f}%)")
    return "\n".join(lines)


def league_post(code: str, rows: pd.DataFrame, picks: pd.DataFrame, weights: dict) -> str:
    rows = rows.sort_values("Kickoff")
    first, last = rows["Kickoff"].iloc[0], rows["Kickoff"].iloc[-1]
    span = day_title(first) if first.date() == last.date() else f"{day_title(first)} — {day_title(last)}"
    parts = [f"<b>{title(code).upper()}</b>\n📅 Прогнозы на {span}\n{LINE}"]
    parts += [match_card(r, picks) for r in rows.itertuples()]
    parts.append(f"{LINE}\n🤖 <i>Модель переобучается каждый день. Сейчас доверие: "
                 f"модель {pct(weights['1X2'])} / рынок {pct(1 - weights['1X2'])}</i>\n{FOOTER}")
    return "\n\n".join(parts)


# ── live-табло ────────────────────────────────────────────────────────────────

_STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "cd", "ud", "rc", "sv", "fk", "if", "bk",
         "club", "de", "the", "city", "united", "town", "calcio", "1"}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _STOP)


def _match_forecast(ev, forecasts: pd.DataFrame):
    if forecasts.empty:
        return None
    cand = forecasts[(forecasts["Div"] == ev.Div) & (forecasts["Kickoff"].dt.date == ev.Kickoff.date())]
    best, best_score = None, 0.0
    key = _norm(ev.home) + " | " + _norm(ev.away)
    for f in cand.itertuples():
        s = difflib.SequenceMatcher(None, key, _norm(f.HomeTeam) + " | " + _norm(f.AwayTeam)).ratio()
        if s > best_score:
            best, best_score = f, s
    return best if best_score >= 0.55 else None


def _hit(f, hs: int, as_: int) -> str:
    """Совпал ли исход матча с самым вероятным по прогнозу."""
    fav = max((f.pH, "H"), (f.pD, "D"), (f.pA, "A"))[1]
    real = "H" if hs > as_ else "D" if hs == as_ else "A"
    return " ✅" if fav == real else " ❌"


def live_board(sb: pd.DataFrame, forecasts: pd.DataFrame, now: pd.Timestamp) -> str:
    n_live = int((sb["state"] == "in").sum())
    head = (f"📺 <b>LIVE-ТАБЛО · {day_title(now).upper()}</b>\n"
            f"🔴 Сейчас идёт: <b>{n_live}</b> · обновлено в {now:%H:%M} МСК\n{LINE}")
    blocks = [head]
    sb = sb.assign(o=sb["Div"].map(ORDER)).sort_values(["o", "Kickoff"])
    for code, g in sb.groupby("Div", sort=False):
        lines = [f"<b>{title(code)}</b>"]
        for ev in g.itertuples():
            f = _match_forecast(ev, forecasts)
            home, away = escape(ev.home), escape(ev.away)
            if ev.state == "pre":
                tip = f" · <i>П1 {pct(f.pH)} Х {pct(f.pD)} П2 {pct(f.pA)}</i>" if f is not None else ""
                lines.append(f"🕒 {ev.Kickoff:%H:%M}  {home} — {away}{tip}")
                continue
            score = f"<b>{ev.hs} : {ev.aws}</b>"
            if ev.state == "in":
                lines.append(f"🔴 <code>{ev.clock:>6}</code> {home} {score} {away}")
            else:
                done = f is not None and str(ev.hs).isdigit() and str(ev.aws).isdigit()
                mark = _hit(f, int(ev.hs), int(ev.aws)) if done else ""
                lines.append(f"🏁 <code>{'FT':>6}</code> {home} {score} {away}{mark}")
        blocks.append("\n".join(lines))
    blocks.append("<i>✅/❌ — угадал ли бот исход. Табло обновляется само.</i>")
    text = "\n\n".join(blocks)
    while len(text) > 4000 and len(blocks) > 3:  # в одно сообщение влезает не всё — убираем хвост
        blocks.pop(-2)
        text = "\n\n".join(blocks + ["<i>…и другие матчи</i>"])
    return text


# ── итоги ставок ─────────────────────────────────────────────────────────────

def results_post(new: pd.DataFrame, all_done: pd.DataFrame) -> str:
    lines = [f"📊 <b>ИТОГИ VALUE-СТАВОК</b>\n{LINE}"]
    for r in new.sort_values("Date").itertuples():
        icon = "✅" if r.won else "❌"
        lines.append(f"{icon} {escape(r.HomeTeam)} {int(r.FTHG)}:{int(r.FTAG)} {escape(r.AwayTeam)}\n"
                     f"     {SIDE_NAMES[r.side]} @ {r.odds:.2f} → <b>{r.profit:+.2f}</b>")
    n, profit = len(all_done), all_done["profit"].sum()
    roi = 100 * profit / n
    lines.append(f"{LINE}\n📈 <b>Вся статистика бота</b>\n"
                 f"Ставок: <b>{n}</b> · Угадано: <b>{pct(all_done['won'].mean())}</b>\n"
                 f"Прибыль: <b>{profit:+.2f}</b> ед. · ROI: <b>{roi:+.1f}%</b>\n"
                 f"<i>1 ед. = ставка одной суммы на каждый прогноз</i>")
    return "\n\n".join(lines)
