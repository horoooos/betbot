"""Инструменты профессионального беттинга.

  • value дня — где лучший коэффициент среди букмекеров выше справедливой цены Pinnacle;
  • прогнозы дня — 3 самых надёжных прогноза, закрепляются в канале;
  • размер ставки — доля банка по осторожному критерию Келли;
  • виртуальный банк — что было бы, если ставить ровно по рекомендациям бота;
  • CLV — куда ушла линия после прогноза: если к началу матча вероятность нашего исхода выросла,
    бот нашёл ценность раньше рынка. Это главный признак качества прогнозов.
"""
from html import escape

import numpy as np
import pandas as pd

from . import card, names, sports, telegram
from . import markets as mk
from .leagues import ALL, ORDER, title

KELLY_FRACTION = 0.25         # четверть Келли — стандарт осторожных игроков
STAKE_MIN, STAKE_MAX = 1.0, 3.0  # % банка
BANK_START = 10_000
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"


def _pct(p: float) -> str:
    return f"{100 * p:.0f}%"


# ── размер ставки и виртуальный банк ────────────────────────────────────────

def stake(tip: dict) -> float:
    """Сколько % банка ставить. Есть перевес по настоящему кэфу — по Келли (1–3%), нет — минимум 1%."""
    if not tip or tip.get("est"):
        return STAKE_MIN
    p, o = tip["p"], tip["odds"]
    edge = p * o - 1
    if edge <= 0 or o <= 1:
        return STAKE_MIN
    kelly = KELLY_FRACTION * edge / (o - 1) * 100
    return round(float(np.clip(kelly, STAKE_MIN, STAKE_MAX)), 1)


def stake_line(tip: dict) -> str:
    s = tip.get("stake", STAKE_MIN)
    why = "есть перевес над линией" if s > STAKE_MIN else "без явного перевеса — минимальная"
    return f"💰 Ставка: <b>{s:g}% банка</b> ({why})"


def bank_curve(res: pd.DataFrame) -> list[float]:
    """Виртуальный банк по рекомендациям бота: старт 10 000, ставка — рекомендованный % от текущего банка."""
    bank, curve = float(BANK_START), [float(BANK_START)]
    if res is None or res.empty:
        return curve
    hit = res["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    stakes = res["main_stake"].fillna(STAKE_MIN) if "main_stake" in res else pd.Series(STAKE_MIN, index=res.index)
    for h, o, s in zip(hit, res["main_odds"].astype(float), stakes.astype(float)):
        amount = bank * s / 100
        bank += amount * (o - 1) if h else -amount
        curve.append(round(bank, 2))
    return curve


# ── CLV: движение линии после прогноза ──────────────────────────────────────

def snapshot(ev: dict, keys: list[str]) -> dict:
    """Вероятности рынков по текущей линии ESPN/DraftKings — для сравнения «при публикации» и «к началу»."""
    keys = [k for k in keys if k]
    o = ev.get("odds") or {}
    try:
        if ev.get("sport", "football") == "football":
            if not (o.get("H") and o.get("D") and o.get("A")):
                return {}
            line = p_over = None
            if o.get("line") and o.get("over") and o.get("under"):
                line, p_over = float(o["line"]), float(mk.fair([o["over"], o["under"]])[0])
            probs = mk.all_markets(*mk.implied_lambdas(mk.fair([o["H"], o["D"], o["A"]]), line, p_over))
        elif ev.get("sport") in ("hockey", "basketball"):
            a = sports.analyse(ev, {})
            probs = a["probs"] if a else {}
        else:
            return {}  # теннис/киберспорт: линия обновляется дважды в день — для CLV не годится
    except Exception:
        return {}
    return {k: round(float(probs[k]), 4) for k in keys if k in probs}


def clv(m: dict, key: str | None) -> float | None:
    o, c = (m.get("open") or {}).get(key), (m.get("close") or {}).get(key)
    return round(c / o - 1, 4) if o and c else None


def clv_line(m: dict) -> str:
    """Строка для итога матча: куда ушла линия после прогноза."""
    key = m["main"]["key"]
    c = clv(m, key)
    if c is None:
        return ""
    o, z = m["open"][key], m["close"][key]
    verdict = "линия пошла за ботом 👍" if c > 0.005 else "линия ушла против прогноза" if c < -0.005 else "линия не изменилась"
    return f"\n📉 CLV: вероятность «{escape(m['main']['label'])}» {_pct(o)} → {_pct(z)} к началу ({100 * c:+.1f}%) — {verdict}"


def clv_summary(res: pd.DataFrame, days: int = 30) -> str:
    if res is None or res.empty or "main_clv" not in res:
        return ""
    d = pd.to_datetime(res["date"])
    x = res[d > d.max() - pd.Timedelta(days=days)]["main_clv"].dropna().astype(float)
    if len(x) < 5:
        return ""
    return (f"📉 <b>CLV за {days} дней:</b> {100 * x.mean():+.1f}% · линия пошла за ботом в "
            f"<b>{_pct((x > 0).mean())}</b> прогнозов ({len(x)})")


# ── value дня ──────────────────────────────────────────────────────────────

def _ru_pair(row: pd.Series, events: list[dict]) -> tuple[str, str]:
    """Русские названия: ищем этот матч в расписании ESPN (там уже переведены)."""
    best, score = None, 0.0
    for e in events:
        if e["div"] != row["Div"] or "ru" not in e["home"]:
            continue
        if abs(pd.Timestamp(e["kickoff"]) - row["Kickoff"]) > pd.Timedelta(hours=26):
            continue
        s = names.similarity(e["home"]["name"], row["HomeTeam"]) + names.similarity(e["away"]["name"], row["AwayTeam"])
        if s > score:
            best, score = e, s
    if best is not None and score >= 1.3:
        return best["home"]["ru"], best["away"]["ru"]
    return row["HomeTeam"], row["AwayTeam"]


def value_candidates(fx: pd.DataFrame, events: list[dict], now: pd.Timestamp, edge=(0.03, 0.25)) -> list[dict]:
    """Матчи ближайших 24 часов, где лучший коэффициент выше справедливой цены (Pinnacle/среднее без маржи)."""
    if fx is None or fx.empty:
        return []
    leagues = {e["div"] for e in events}  # только турниры, которые бот и так ведёт (без мусорных лиг)
    soon = fx[(fx["Kickoff"] > now) & (fx["Kickoff"] <= now + pd.Timedelta(hours=24)) & fx["Div"].isin(leagues)]
    out = []
    for _, r in soon.iterrows():
        sides = []
        if all(pd.notna(r.get(c)) and r.get(c, 0) > 1 for c in ("MaxH", "MaxD", "MaxA")):
            fair_src = ("PSH", "PSD", "PSA") if all(pd.notna(r.get(c)) and r.get(c, 0) > 1 for c in ("PSH", "PSD", "PSA")) \
                else ("AvgH", "AvgD", "AvgA")
            if all(pd.notna(r.get(c)) and r.get(c, 0) > 1 for c in fair_src):
                p = mk.fair([r[c] for c in fair_src])
                sides += [("П1", p[0], r["MaxH"]), ("Ничья", p[1], r["MaxD"]), ("П2", p[2], r["MaxA"])]
        if all(pd.notna(r.get(c)) and r.get(c, 0) > 1 for c in ("Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5")):
            p = mk.fair([r["Avg>2.5"], r["Avg<2.5"]])
            sides += [("ТБ 2.5", p[0], r["Max>2.5"]), ("ТМ 2.5", p[1], r["Max<2.5"])]
        for label, p, o in sides:
            e = p * float(o) - 1
            if edge[0] <= e <= edge[1] and 1.3 <= float(o) <= 6:
                h, a = _ru_pair(r, events)
                out.append({"div": r["Div"], "kickoff": r["Kickoff"], "home": h, "away": a, "label": label,
                            "p": float(p), "odds": float(o), "edge": float(e)})
    return sorted(out, key=lambda x: -x["edge"])


def post_value(fx, events, now, brand) -> bool:
    picks = value_candidates(fx, events, now)[:6]
    if not picks:
        return False
    lines = ["💎 <b>VALUE ДНЯ</b>", "Здесь лучший коэффициент среди букмекеров <b>выше справедливой цены</b> — "
             "именно такие ставки на длинной дистанции дают плюс.\n"]
    for x in picks:
        tip = {"p": x["p"], "odds": x["odds"], "est": False}
        lines.append(f"🕒 {x['kickoff']:%H:%M} <b>{escape(x['home'])} — {escape(x['away'])}</b> · {title(x['div'])}\n"
                     f"   ✅ <b>{x['label']}</b> @ {x['odds']:.2f} · справедливо ≈{1 / x['p']:.2f} · "
                     f"перевес <b>+{100 * x['edge']:.1f}%</b> · ставка {stake(tip):g}% банка")
    lines += ["\n<i>Лучший кэф быстро уходит — проверяйте линию у своего букмекера перед ставкой.</i>", FOOTER]
    rows = [(f"{x['kickoff']:%H:%M}", x["home"], x["away"], f"{x['label']} @ {x['odds']:.2f}") for x in picks]
    png = card.schedule_card("ставки дороже справедливой цены", rows, 0, brand, heading="Value дня")
    _post(png, "\n".join(lines))
    return True


# ── прогнозы дня ───────────────────────────────────────────────────────────

def _quick_tip(e: dict) -> dict | None:
    """Прогноз «на утро» по текущей линии: как в обзоре, но без публикации."""
    o = e.get("odds") or {}
    if e.get("sport", "football") == "football":
        if not (o.get("H") and o.get("D") and o.get("A")):
            return None
        line = p_over = None
        real = {"H": o["H"], "D": o["D"], "A": o["A"]}
        if o.get("line") and o.get("over") and o.get("under"):
            line, p_over = float(o["line"]), float(mk.fair([o["over"], o["under"]])[0])
            if line == 2.5:
                real.update({"O25": o["over"], "U25": o["under"]})
        probs = mk.all_markets(*mk.implied_lambdas(mk.fair([o["H"], o["D"], o["A"]]), line, p_over))
        probs.pop("scores", None)
        main, _ = mk.tips(probs, real, {})
        return main
    a = sports.analyse(e, {})
    return sports.pick(a, {})[0] if a else None


def post_top(state: dict, football: list[dict], other: list[dict], now: pd.Timestamp, brand: str) -> None:
    start = now.normalize() + pd.Timedelta(hours=6)
    day = [e for e in football + [x for x in other if x["sport"] in ("hockey", "basketball")]
           if e["state"] == "pre" and start <= pd.Timestamp(e["kickoff"]) < start + pd.Timedelta(days=1) and "ru" in e["home"]]
    cands = []
    for e in day:
        try:
            t = _quick_tip(e)
        except Exception:
            t = None
        if t and not t.get("est") and t["odds"] >= 1.45:
            rank = ORDER.get(e["div"], 40) if e["div"] in ALL else 10  # топ-лиги чуть приоритетнее
            cands.append((t["p"] - rank / 1000, e, t))
    cands.sort(key=lambda x: -x[0])
    top, seen = [], set()
    for _, e, t in cands:
        if e["id"] not in seen:
            top.append((e, t))
            seen.add(e["id"])
        if len(top) == 3:
            break
    if not top:
        return
    lines = ["⭐ <b>ПРОГНОЗЫ ДНЯ</b>", "Три самых надёжных прогноза на сегодня по линии букмекеров:\n"]
    for i, (e, t) in enumerate(sorted(top, key=lambda x: x[0]["kickoff"]), 1):
        t["stake"] = stake(t)
        emoji = sports.EMOJI.get(e.get("sport", "football"), "⚽️")
        league = title(e["div"]) if e["div"] in ALL else sports.title(e["div"])
        lines.append(f"{i}. {emoji} {pd.Timestamp(e['kickoff']):%H:%M} <b>{escape(e['home']['ru'])} — "
                     f"{escape(e['away']['ru'])}</b> · {league}\n   🎯 <b>{escape(t['label'])}</b> — {_pct(t['p'])} · "
                     f"кэф {t['odds']:.2f} · ставка {t['stake']:g}% банка")
    lines += ["\nПолный разбор каждого матча выйдет примерно за час до начала 👇", FOOTER]
    rows = [(f"{pd.Timestamp(e['kickoff']):%H:%M}", e["home"]["ru"], e["away"]["ru"], t["label"]) for e, t in top]
    png = card.schedule_card(f"{now.day:02d}.{now.month:02d} · самое надёжное", rows, 0, brand, heading="Прогнозы дня")
    mid = _post(png, "\n".join(lines))
    telegram.pin(mid)
    state["top_picks"] = {"day": str(now.date()), "keys": [f"{e['div']}|{e['id']}" for e, _ in top]}
    print(f"Прогнозы дня: {len(top)}")


def is_top(state: dict, div: str, eid: str) -> bool:
    return f"{div}|{eid}" in (state.get("top_picks") or {}).get("keys", [])


def _post(png: bytes, text: str) -> int:
    if len(text) <= telegram.CAPTION_LIMIT:
        return telegram.send_photo(png, text)
    head, _, rest = text.partition("\n")
    mid = telegram.send_photo(png, head)
    telegram.send(rest, reply_to=mid, silent=True)
    return mid
