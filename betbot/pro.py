"""Инструменты профессионального беттинга.

  • value дня — где лучший коэффициент среди букмекеров выше справедливой цены Pinnacle;
  • прогнозы дня — 3 самых надёжных прогноза, закрепляются в канале;
  • размер ставки — доля банка по осторожному критерию Келли;
  • виртуальный банк — что было бы, если ставить ровно по рекомендациям бота;
  • CLV — куда ушла линия после прогноза: если к началу матча вероятность нашего исхода выросла,
    бот нашёл ценность раньше рынка. Это главный признак качества прогнозов.
"""
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from . import card, names, sports, telegram
from . import markets as mk
from .leagues import ALL, ORDER, title
from .texts import MONTHS

KELLY_FRACTION = 0.25         # четверть Келли — стандарт осторожных игроков
STAKE_MIN, STAKE_MAX = 1.0, 3.0  # % банка
BANK_START = 10_000
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"
# Журнал value-ставок: каждая сохраняется с кэфом на момент публикации и потом рассчитывается по итогу матча.
# Порог 5%: на истории (backtest_value.py) ставки с перевесом от 3% по ранней линии уходили в минус, от 5% — в плюс.
VALUE_LOG = Path(__file__).resolve().parent.parent / "data" / "value_bets.csv"
VALUE_EDGE = (0.05, 0.30)


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


BANK_RESET = "2026-11-12"   # банк обнулён до 10 000: с этого дня бот ставит по новым правилам (все исходы + экспрессы)
EXPRESS_LOG = Path(__file__).resolve().parent.parent / "data" / "express_bets.csv"
LIVE_LOG = Path(__file__).resolve().parent.parent / "data" / "live_bets.csv"   # ⚡ live-ставки бота (пишет inplay.py)


def bank_daily(res: pd.DataFrame, today: pd.Timestamp | None = None) -> list[dict]:
    """Банк по дням с BANK_RESET: [{date, bank, n (ставок), w (зашло)}]; первая точка — старт 10 000."""
    if res is not None and len(res):
        res = res[pd.to_datetime(res["date"]) >= pd.Timestamp(BANK_RESET)]
    start = pd.Timestamp(BANK_RESET)
    out = [{"date": (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "bank": float(BANK_START), "n": 0, "w": 0, "start": True}]
    bank = float(BANK_START)
    for day, o, h, s in all_bets(res, start=BANK_RESET, dated=True):
        if out[-1]["date"] != day:
            out.append({"date": day, "bank": bank, "n": 0, "w": 0})
        amount = bank * s / 100
        bank += amount * (o - 1) if h else -amount
        out[-1].update(bank=round(bank, 2), n=out[-1]["n"] + 1, w=out[-1]["w"] + int(h))
    return out


def bank_curve(res: pd.DataFrame) -> list[float]:
    """Виртуальный банк по ВСЕМ исходам бота с BANK_RESET: старт 10 000, ставка — рекомендованный % от текущего банка.

    Учитываются все основные прогнозы (и с настоящим кэфом, и с расчётным «≈»), все смелые ставки (1% банка)
    и все экспрессы — «Экспресс дня» и «Экспресс на яйцах» (1% банка).
    """
    if res is not None and len(res):
        res = res[pd.to_datetime(res["date"]) >= pd.Timestamp(BANK_RESET)]
    bank, curve = float(BANK_START), [float(BANK_START)]
    for o, h, s in all_bets(res, start=BANK_RESET):
        amount = bank * s / 100
        bank += amount * (o - 1) if h else -amount
        curve.append(round(bank, 2))
    return curve


def _truthy(col: pd.Series) -> pd.Series:
    return col.astype(str).str.lower().isin(["true", "1", "1.0"])


def expresses(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Рассчитанные экспрессы из журнала (дата, вид, событий, кэф, зашёл) за период."""
    try:
        ex = pd.read_csv(EXPRESS_LOG)
    except (OSError, ValueError):
        return pd.DataFrame(columns=["date", "name", "legs", "odds", "hit"])
    d = pd.to_datetime(ex["date"])
    if start:
        ex = ex[d >= pd.Timestamp(start)]
    if end:
        ex = ex[pd.to_datetime(ex["date"]) <= pd.Timestamp(end)]
    return ex


def live_bets(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Рассчитанные live-ставки из журнала inplay.py: дата, матч, рынок, кэф «от», зашла ли."""
    try:
        df = pd.read_csv(LIVE_LOG)
    except (OSError, ValueError):
        return pd.DataFrame(columns=["date", "match", "label", "odds", "hit"])
    if df.empty:
        return df
    if start:
        df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(start)]
    if end:
        df = df[pd.to_datetime(df["date"]) <= pd.Timestamp(end)]
    return df


def all_bets(res: pd.DataFrame, start: str | None = None, end: str | None = None, dated: bool = False) -> list:
    """Все рассчитанные ставки бота по датам: (кэф, зашла ли, % банка) — основные, смелые, экспрессы и live.

    Экспрессы берём за даты таблицы res (или с start, если задан). Live-ставки — из журнала inplay.py,
    кэф у них — минимальный, при котором ставка была выгодна (так их и рекомендовал бот)."""
    rows: list[tuple[str, float, bool, float]] = []
    if res is not None and not res.empty:
        stakes = res["main_stake"].fillna(STAKE_MIN) if "main_stake" in res else pd.Series(STAKE_MIN, index=res.index)
        main_hit = _truthy(res["main_hit"])
        bold_hit = _truthy(res["bold_hit"]) if "bold_hit" in res else pd.Series(False, index=res.index)
        for i in res.index:
            day = str(res.at[i, "date"])[:10]
            o = pd.to_numeric(res.at[i, "main_odds"], errors="coerce")
            if pd.notna(o) and o > 1 and pd.notna(res.at[i, "main_hit"]):
                rows.append((day, float(o), bool(main_hit[i]), float(stakes[i])))
            if "bold_odds" in res and pd.notna(res.at[i, "bold_hit"] if "bold_hit" in res else None):
                bo = pd.to_numeric(res.at[i, "bold_odds"], errors="coerce")
                if pd.notna(bo) and bo > 1:
                    rows.append((day, float(bo), bool(bold_hit[i]), STAKE_MIN))
        start = start or str(res["date"].min())[:10]
        end = end or str(res["date"].max())[:10]
    if start or end:
        ex = expresses(start, end)
        rows += [(str(r["date"])[:10], float(r["odds"]), str(r["hit"]).lower() in ("true", "1"), STAKE_MIN)
                 for _, r in ex.iterrows() if float(r["odds"]) > 1]
        lb = live_bets(start, end)
        rows += [(str(r["date"])[:10], float(r["min_odds"]), str(r["hit"]).lower() in ("true", "1"), STAKE_MIN)
                 for _, r in lb.iterrows()
                 if pd.notna(r.get("min_odds")) and float(r["min_odds"]) > 1 and str(r.get("hit")) not in ("", "nan")]
    rows.sort(key=lambda r: r[0])   # по дням; внутри дня — в порядке записи
    return rows if dated else [(o, h, s) for _, o, h, s in rows]


def bet_counts(res: pd.DataFrame) -> dict:
    """Сколько реально было ставок за всё время: основные, смелые, экспрессы и сколько из них зашло."""
    out = {"main": 0, "main_w": 0, "bold": 0, "bold_w": 0, "express": 0, "express_w": 0}
    if res is not None and len(res):
        m = res[pd.to_numeric(res["main_odds"], errors="coerce") > 1]
        m = m[m["main_hit"].notna()]
        out["main"], out["main_w"] = len(m), int(_truthy(m["main_hit"]).sum())
        if "bold_odds" in res and "bold_hit" in res:
            b = res[(pd.to_numeric(res["bold_odds"], errors="coerce") > 1) & res["bold_hit"].notna()]
            out["bold"], out["bold_w"] = len(b), int(_truthy(b["bold_hit"]).sum())
    ex = expresses()
    out["express"], out["express_w"] = len(ex), int(ex["hit"].astype(str).str.lower().isin(["true", "1"]).sum()) if len(ex) else 0
    out["total"] = out["main"] + out["bold"] + out["express"]
    out["won"] = out["main_w"] + out["bold_w"] + out["express_w"]
    return out


def roi_all(res: pd.DataFrame) -> float | None:
    """ROI по всем исходам (основные + смелые + экспрессы, любые кэфы), ставка 1 ед."""
    bets = all_bets(res)
    if not bets:
        return None
    return float(100 * sum((o - 1) if h else -1 for o, h, _ in bets) / len(bets))


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

def _ru_pair(row: pd.Series, events: list[dict]) -> tuple[str, str, list, list]:
    """Русские названия, логотипы и цвета: ищем этот матч в расписании ESPN (там всё уже есть)."""
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
        return (best["home"]["ru"], best["away"]["ru"], [best["home"].get("logo"), best["away"].get("logo")],
                [best["home"].get("color"), best["away"].get("color")])
    return row["HomeTeam"], row["AwayTeam"], [None, None], ["3b4a7a", "8a2b2b"]


def value_candidates(fx: pd.DataFrame, events: list[dict], now: pd.Timestamp, edge=VALUE_EDGE) -> list[dict]:
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
                sides += [("П1", p[0], r["MaxH"], "H"), ("Ничья", p[1], r["MaxD"], "D"), ("П2", p[2], r["MaxA"], "A")]
        if all(pd.notna(r.get(c)) and r.get(c, 0) > 1 for c in ("Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5")):
            p = mk.fair([r["Avg>2.5"], r["Avg<2.5"]])
            sides += [("ТБ 2.5", p[0], r["Max>2.5"], "O25"), ("ТМ 2.5", p[1], r["Max<2.5"], "U25")]
        for label, p, o, key in sides:
            e = p * float(o) - 1
            if edge[0] <= e <= edge[1] and 1.5 <= float(o) <= 4:
                h, a, logos, colors = _ru_pair(r, events)
                out.append({"div": r["Div"], "kickoff": r["Kickoff"], "home": h, "away": a, "label": label,
                            "logos": logos, "colors": colors, "league": title(r["Div"]),
                            "p": float(p), "odds": float(o), "edge": float(e), "key": key,
                            "ht": r["HomeTeam"], "at": r["AwayTeam"]})
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
    png = card.value_card(picks, f"{now.day} {MONTHS[now.month - 1]}", brand)
    mid = _post(png, "\n".join(lines))
    rows = pd.DataFrame([{"posted": str(now.date()), "msg": mid, "div": x["div"], "kickoff": x["kickoff"].isoformat(),
                          "ht": x["ht"], "at": x["at"], "home": x["home"], "away": x["away"], "key": x["key"],
                          "label": x["label"], "odds": round(x["odds"], 3), "p": round(x["p"], 4),
                          "edge": round(x["edge"], 4), "score": None, "hit": None} for x in picks])
    old = pd.read_csv(VALUE_LOG, dtype=object) if VALUE_LOG.exists() else None
    pd.concat([old, rows], ignore_index=True).to_csv(VALUE_LOG, index=False)
    return True


def settle_value(now: pd.Timestamp, load_history) -> None:
    """Рассчитывает value-ставки по итогам матчей (из той же базы football-data) и пишет итог дня."""
    if not VALUE_LOG.exists():
        return
    log = pd.read_csv(VALUE_LOG, dtype={"score": object, "hit": object, "announced": object})
    todo = log["hit"].isna() & (pd.to_datetime(log["kickoff"], utc=True) < now.tz_convert("UTC") - pd.Timedelta(hours=3))
    if not todo.any():
        return
    hist = load_history(refresh_current=True, leagues=sorted(log.loc[todo, "div"].unique()))
    hist = hist[hist["Date"] >= pd.Timestamp(now.date()) - pd.Timedelta(days=10)]
    for i in log.index[todo]:
        r = log.loc[i]
        m = hist[(hist["Div"] == r["div"]) & (hist["HomeTeam"] == r["ht"]) & (hist["AwayTeam"] == r["at"])]
        if m.empty:
            if now.tz_convert("UTC") - pd.Timestamp(r["kickoff"]).tz_convert("UTC") > pd.Timedelta(days=4):
                log.loc[i, "hit"] = "void"  # матч перенесён или не попал в базу — ставка не в счёт
            continue
        hs, as_ = int(m.iloc[-1]["FTHG"]), int(m.iloc[-1]["FTAG"])
        log.loc[i, "score"] = f"{hs}:{as_}"
        log.loc[i, "hit"] = str(bool(mk.won(r["key"], hs, as_)))
    log.to_csv(VALUE_LOG, index=False)
    # итог value дня — ответом к посту, когда рассчитаны все ставки этого поста
    for msg, g in log.groupby("msg"):
        if g["hit"].isna().any() or g.get("announced", pd.Series(dtype=object)).notna().any():
            continue
        played = g[g["hit"].isin(["True", "False"])]
        if played.empty:
            continue
        win = played["hit"] == "True"
        profit = float((win * (played["odds"] - 1) - (~win)).sum())
        lines = [f"💎 <b>ИТОГ VALUE ДНЯ: {int(win.sum())} из {len(played)}</b> · "
                 f"{'+' if profit >= 0 else ''}{profit:.2f} ед. при ставке 1 ед. на каждую"]
        for (_, r), w in zip(played.iterrows(), win):
            lines.append(f"{'✅' if w else '❌'} {escape(str(r['home']))} {r['score']} {escape(str(r['away']))} — "
                         f"{escape(str(r['label']))} @ {r['odds']:.2f}")
        total = value_summary()
        if total:
            lines.append("\n" + total)
        try:
            telegram.send("\n".join(lines), reply_to=int(msg))
        except Exception as ex:
            print(f"  ! итог value дня не отправлен: {ex}")
        log.loc[g.index, "announced"] = str(now.date())
    log.to_csv(VALUE_LOG, index=False)


def value_numbers() -> tuple[int, int, float] | None:
    """(ставок, зашло, ROI %) по всем рассчитанным value-ставкам."""
    if not VALUE_LOG.exists():
        return None
    log = pd.read_csv(VALUE_LOG, dtype={"score": object, "hit": object, "announced": object})
    done = log[log["hit"].isin(["True", "False", True, False])]
    if done.empty:
        return None
    win = done["hit"].astype(str) == "True"
    roi = float((win * (done["odds"].astype(float) - 1) - (~win)).mean() * 100)
    return len(done), int(win.sum()), roi


def value_summary() -> str:
    v = value_numbers()
    if not v:
        return ""
    n, w, roi = v
    return (f"💎 <b>Value-ставки за всё время:</b> {w} из {n} · ROI <b>{roi:+.1f}%</b> "
            f"<i>(настоящие кэфы, ставка 1 ед.)</i>")


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
    picks = [{"home": e["home"], "away": e["away"], "time": f"{pd.Timestamp(e['kickoff']):%H:%M}",
              "league": card.safe(title(e["div"]) if e["div"] in ALL else sports.title(e["div"])),
              "label": t["label"], "odds": t["odds"], "p": t["p"]}
             for e, t in sorted(top, key=lambda x: x[0]["kickoff"])]
    png = card.top_card(picks, f"{now.day} {MONTHS[now.month - 1]}", brand)
    mid = _post(png, "\n".join(lines))
    telegram.pin(mid)
    state["top_picks"] = {"day": str(now.date()), "keys": [f"{e['div']}|{e['id']}" for e, _ in top]}
    print(f"Прогнозы дня: {len(top)}")


# ── серии заходов ───────────────────────────────────────────────────────────

STREAK_MARKS = (5, 7, 10)  # дальше — каждые 5: 15, 20, 25… (серии по 3 случаются слишком часто)
STREAK_PER_DAY = 2


def _is_mark(n: int) -> bool:
    return n in STREAK_MARKS or (n > 10 and n % 5 == 0)


def post_streak(state: dict, res: pd.DataFrame, brand: str, force: bool = False) -> None:
    """«🔥 5 заходов подряд!» — когда серия основных прогнозов доходит до 3, 5, 7, 10, 15…"""
    if res is None or res.empty:
        return
    hit = res["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"]).tolist()
    n = 0
    for h in reversed(hit):
        if not h:
            break
        n += 1
    posted = state.get("streak_posted", 0)
    if n < posted:  # серия прервалась — начинаем заново
        state["streak_posted"] = 0
        posted = 0
    if not force and (n <= posted or not _is_mark(n)):
        return
    if n < 3:  # даже по запросу не хвастаемся одним-двумя заходами
        return
    day = str(pd.Timestamp.now(tz="Europe/Moscow").date())
    cnt = state.setdefault("streak_day", {})
    for k in [k for k in cnt if k != day]:   # держим только сегодняшний счётчик, а не обнуляем его
        cnt.pop(k, None)
    if not force and cnt.get(day, 0) >= STREAK_PER_DAY:
        return
    cnt[day] = cnt.get(day, 0) + 1
    tail = res.tail(n)
    odds = tail["main_odds"].astype(float)
    total = float(np.prod(odds))
    word = "ЗАХОД" if n % 10 == 1 and n % 100 != 11 else "ЗАХОДА" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "ЗАХОДОВ"
    lines = [f"🔥 <b>{n} {word} ПОДРЯД!</b>", "Основной прогноз бота заходит раз за разом:\n"]
    for _, r in tail.iloc[::-1].head(10).iterrows():
        emoji = sports.EMOJI.get(str(r.get("sport", "football")), "⚽️")
        lines.append(f"✅ {emoji} {escape(str(r['home']))} {escape(str(r['score']))} {escape(str(r['away']))} — "
                     f"{escape(str(r['main_label']))} @ {float(r['main_odds']):.2f}")
    if n > 10:
        lines.append(f"…и ещё {n - 10}")
    lines += [f"\n💰 Если бы всё это было одним экспрессом — кэф <b>{total:,.2f}</b>".replace(",", " "),
              "<i>Серии заканчиваются — играйте по банку, а не на эмоциях.</i>", FOOTER]
    rows = [{"score": str(r["score"]), "home": str(r["home"]), "away": str(r["away"]), "label": str(r["main_label"]),
             "odds": float(r["main_odds"]), "sport": str(r.get("sport", "football"))}
            for _, r in tail.iloc[::-1].iterrows()]
    sports_in = tail["sport"].fillna("football").unique() if "sport" in tail else ["football"]
    icon = sports_in[0] if len(sports_in) == 1 else "football"  # иконка вида спорта, из которого серия
    png = card.streak_card(rows, n, total, brand, sport=icon)
    _post(png, "\n".join(lines))
    state["streak_posted"] = n   # только после успешной публикации — иначе при сбое серия не повторится
    print(f"Серия: {n} заходов подряд")


def is_top(state: dict, div: str, eid: str) -> bool:
    return f"{div}|{eid}" in (state.get("top_picks") or {}).get("keys", [])


def _post(png: bytes, text: str) -> int:
    if len(text) <= telegram.CAPTION_LIMIT:
        return telegram.send_photo(png, text)
    head, _, rest = text.partition("\n")
    mid = telegram.send_photo(png, head)
    telegram.send(rest, reply_to=mid, silent=True)
    return mid
