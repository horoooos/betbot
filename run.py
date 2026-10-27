"""Один запуск бота. На GitHub Actions — каждые 20 минут днём и каждый час ночью.

Что делает:
  • утром (после 08:00 МСК) — статистика за вчера/7/30 дней и расписание матчей на день;
  • примерно за час до каждого матча — картинка + прогноз + полный разбор;
  • после каждого матча — итог, угадал ли бот, статистика за день;
  • раз в сутки — переобучается на свежих результатах.

Запуск:  python run.py   (без TELEGRAM_TOKEN посты сохраняются в data/preview/)
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from betbot import card, names, telegram, texts
from betbot import markets as mk
from betbot.data import MSK, load_fixtures, load_history
from betbot.engine import add_market, fit_full, fit_weights, walk_forward
from betbot.espn import scoreboard, summary
from betbot.leagues import ALL, EXTRA, MAIN

# Лиги, по которым бот делает обзоры (код → см. betbot/leagues.py). Больше лиг = больше постов.
REVIEW_LEAGUES = ["E0", "SP1", "I1", "D1", "F1", "RUS", "UCL", "UEL", "UECL", "N1", "P1", "T1"]
MORNING_HOUR = 8        # во сколько (МСК) выходит расписание
DAY_START_HOUR = 6      # «игровой день» — с 06:00 до 06:00 следующего дня
VALUE_EDGE = (0.05, 0.30)

DATA = Path(__file__).resolve().parent / "data"
STATE, MATCHES, RESULTS = DATA / "state.json", DATA / "matches.json", DATA / "results.csv"
HIST_LEAGUES = [c for c in REVIEW_LEAGUES if c in MAIN or c in EXTRA]
BRAND = os.environ.get("TELEGRAM_CHAT_ID", "") if os.environ.get("TELEGRAM_CHAT_ID", "").startswith("@") else ""


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def matchday(t: pd.Timestamp) -> pd.Timestamp:
    """Матч в 01:30 ночи относится к предыдущему игровому дню."""
    return (t - pd.Timedelta(hours=DAY_START_HOUR)).normalize()


def gap_minutes(now: pd.Timestamp) -> int:
    """Сколько минут до следующего запуска (см. расписание в .github/workflows/daily.yml)."""
    return 20 if 8 <= now.tz_convert("UTC").hour <= 23 else 60


# ── коэффициенты и вероятности ──────────────────────────────────────────────

def find_fixture(ev: dict, fx: pd.DataFrame) -> pd.Series | None:
    """Ищем этот матч в файле football-data (там средние и лучшие коэффициенты 40+ букмекеров)."""
    if fx is None or fx.empty:
        return None
    k = pd.Timestamp(ev["kickoff"])
    cand = fx[(fx["Div"] == ev["div"]) & ((fx["Kickoff"] - k).abs() <= pd.Timedelta(hours=26))]
    best, score = None, 0.0
    for _, r in cand.iterrows():
        s = names.similarity(ev["home"]["name"], r["HomeTeam"]) + names.similarity(ev["away"]["name"], r["AwayTeam"])
        if s > score:
            best, score = r, s
    return best if score >= 1.3 else None


def market(ev: dict, row: pd.Series | None) -> dict | None:
    def ok(*vals):
        return all(v is not None and not pd.isna(v) and v > 1.01 for v in vals)

    if row is not None and ok(row.get("AvgH"), row.get("AvgD"), row.get("AvgA")):
        sharp = ok(row.get("PSH"), row.get("PSD"), row.get("PSA"))
        p1x2 = mk.fair([row["PSH"], row["PSD"], row["PSA"]] if sharp else [row["AvgH"], row["AvgD"], row["AvgA"]])
        real = {"H": row["AvgH"], "D": row["AvgD"], "A": row["AvgA"]}
        line = p_over = None
        if ok(row.get("Avg>2.5"), row.get("Avg<2.5")):
            line, p_over = 2.5, float(mk.fair([row["Avg>2.5"], row["Avg<2.5"]])[0])
            real.update({"O25": row["Avg>2.5"], "U25": row["Avg<2.5"]})
        best = {s: row.get(f"Max{s}") for s in "HDA"}
        return {"p1x2": p1x2, "line": line, "p_over": p_over, "real": real, "max": best,
                "src": "среднее по букмекерам"}
    o = ev.get("odds") or {}
    if ok(o.get("H"), o.get("D"), o.get("A")):
        real = {"H": o["H"], "D": o["D"], "A": o["A"]}
        line = p_over = None
        if o.get("line") and ok(o.get("over"), o.get("under")):
            line, p_over = float(o["line"]), float(mk.fair([o["over"], o["under"]])[0])
            if line == 2.5:
                real.update({"O25": o["over"], "U25": o["under"]})
        return {"p1x2": mk.fair([o["H"], o["D"], o["A"]]), "line": line, "p_over": p_over, "real": real,
                "max": {}, "src": "DraftKings"}
    return None


def lambdas(ev, row, mkt, w, hist_loader) -> tuple[float, float] | None:
    lam_mkt = mk.implied_lambdas(mkt["p1x2"], mkt["line"], mkt["p_over"]) if mkt else None
    lam_model = None
    if row is not None and (w > 0 or lam_mkt is None) and ev["div"] in HIST_LEAGUES:
        hist = hist_loader()
        if (hist["Div"] == ev["div"]).sum() >= 200:
            model = fit_full(hist, ev["div"], pd.Timestamp.now(tz=MSK).tz_localize(None))
            lam_model = model.expected_goals(row["HomeTeam"], row["AwayTeam"])
    if lam_mkt and lam_model:  # смешиваем с весом, который бот выучил сам
        return tuple(float(a ** (1 - w) * b ** w) for a, b in zip(lam_mkt, lam_model))
    return lam_mkt or lam_model


def value_pick(probs: dict, mkt: dict | None) -> dict | None:
    if not mkt or not mkt.get("max"):
        return None
    best = None
    for s in "HDA":
        o = mkt["max"].get(s)
        if o is None or pd.isna(o):
            continue
        edge = probs[s] * o - 1
        if VALUE_EDGE[0] <= edge <= VALUE_EDGE[1] and (best is None or edge > best["edge"]):
            best = {"key": s, "label": mk.label(s), "odds": float(o), "edge": float(edge), "p": probs[s]}
    return best


# ── шаги бота ───────────────────────────────────────────────────────────────

def learn(state: dict, now: pd.Timestamp) -> None:
    try:
        hist = load_history(refresh_current=True, leagues=HIST_LEAGUES)
        start = str((now.tz_localize(None) - pd.Timedelta(days=730)).date())
        state["weights"] = fit_weights(add_market(walk_forward(hist, start=start)))
        print(f"    переобучение: вес модели {state['weights']}")
    except Exception as e:
        print(f"  ! переобучение не удалось: {e}")
        state.setdefault("weights", {"1X2": 0.0, "OU25": 0.0})


def morning(state: dict, events: list[dict], now: pd.Timestamp) -> None:
    res = pd.read_csv(RESULTS) if RESULTS.exists() else pd.DataFrame()
    if len(res):
        telegram.send(texts.stats(res, now.normalize()))
    start = pd.Timestamp(now.normalize()) + pd.Timedelta(hours=DAY_START_HOUR)
    day = [e for e in events if e["state"] == "pre" and start <= pd.Timestamp(e["kickoff"]) < start + pd.Timedelta(days=1)]
    for e in day:
        o = e.get("odds") or {}
        if o.get("H") and o.get("D") and o.get("A"):
            p = mk.fair([o["H"], o["D"], o["A"]])
            if max(p[0], p[2]) >= 0.45:
                e["fav"] = (e["home"]["ru"], p[0]) if p[0] > p[2] else (e["away"]["ru"], p[2])
    if day:
        telegram.send(texts.schedule(day, now))
    print(f"Утренний пост: матчей в расписании {len(day)}")


def review(ev: dict, w: dict, fx_loader, hist_loader) -> dict | None:
    row = find_fixture(ev, fx_loader())
    mkt = market(ev, row)
    lam = lambdas(ev, row, mkt, w.get("1X2", 0.0), hist_loader)
    if lam is None:
        print(f"  нет коэффициентов и истории: {ev['home']['name']} — {ev['away']['name']}")
        return None
    probs = mk.all_markets(*lam)
    scores = probs.pop("scores")
    main, bold = mk.tips(probs, mkt["real"] if mkt else {})
    m = {**ev, "lam": list(lam), "probs": probs, "scores": scores, "main": main, "bold": bold,
         "value": value_pick(probs, mkt), "odds_src": mkt["src"] if mkt else "нет, только модель",
         "model_w": w.get("1X2", 0.0) if mkt else 1.0}
    s = summary(ev["slug"], ev["id"])
    kick = pd.Timestamp(ev["kickoff"])
    tip = f"{main['label']} · {texts.pct(main['p'])}"
    png = card.match_card(texts.league_plain(ev["div"]), texts.when(kick), ev["home"], ev["away"],
                          (probs["H"], probs["D"], probs["A"]), tip, lam, BRAND)
    m["msg_id"] = telegram.send_photo(png, texts.caption(m, s.get("venue") or ev.get("venue")))
    telegram.send(texts.review(m, s), reply_to=m["msg_id"], silent=True)
    m["status"] = "reviewed"
    print(f"  обзор: {ev['home']['ru']} — {ev['away']['ru']} → {main['label']}")
    return m


def settle(m: dict, ev: dict) -> None:
    hs, as_ = int(ev["home"]["score"]), int(ev["away"]["score"])
    s = summary(ev["slug"], ev["id"])
    m["main_hit"] = mk.won(m["main"]["key"], hs, as_)
    m["bold_hit"] = mk.won(m["bold"]["key"], hs, as_) if m.get("bold") else None
    m["value_hit"] = mk.won(m["value"]["key"], hs, as_) if m.get("value") else None
    day = str(matchday(pd.Timestamp(m["kickoff"])).date())
    row = {"date": day, "id": m["id"], "div": m["div"], "home": m["home"]["ru"], "away": m["away"]["ru"],
           "score": f"{hs}:{as_}", "main_label": m["main"]["label"], "main_odds": m["main"]["odds"],
           "main_est": m["main"]["est"], "main_hit": m["main_hit"],
           "bold_label": (m.get("bold") or {}).get("label"), "bold_odds": (m.get("bold") or {}).get("odds"),
           "bold_hit": m["bold_hit"], "value_odds": (m.get("value") or {}).get("odds"), "value_hit": m["value_hit"]}
    res = pd.read_csv(RESULTS) if RESULTS.exists() else pd.DataFrame()
    res = pd.concat([res, pd.DataFrame([row])], ignore_index=True).drop_duplicates("id", keep="last")
    res.to_csv(RESULTS, index=False)
    today = res[res["date"] == day]
    bold = today.dropna(subset=["bold_hit"])
    ds = {"n": len(today), "main": int(today["main_hit"].astype(bool).sum()),
          "nb": len(bold), "bold": int(bold["bold_hit"].astype(bool).sum())}
    telegram.send(texts.result(m, s, hs, as_, ds), reply_to=m["msg_id"])
    m["status"] = "done"
    print(f"  итог: {m['home']['ru']} {hs}:{as_} {m['away']['ru']} → {'✅' if m['main_hit'] else '❌'}")


def main():
    DATA.mkdir(exist_ok=True)
    now = pd.Timestamp.now(tz=MSK)
    state = load_json(STATE, {})
    matches = load_json(MATCHES, {})
    today = str(now.date())

    if state.get("learned") != today:
        print("Переобучаюсь на свежих результатах...")
        learn(state, now)
        state["learned"] = today
    w = state.get("weights", {"1X2": 0.0, "OU25": 0.0})

    utc = now.tz_convert("UTC")
    days = [(utc + pd.Timedelta(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
    events = scoreboard({c: ALL[c][3] for c in REVIEW_LEAGUES}, days)
    events = [e for e in events if "POSTPONED" not in e["status"] and "CANCELED" not in e["status"]]
    for e in events:  # русские названия только для матчей ближайших суток
        if abs(pd.Timestamp(e["kickoff"]) - now) <= pd.Timedelta(hours=30):
            e["home"]["ru"], e["away"]["ru"] = names.team(e["home"]["name"]), names.team(e["away"]["name"])
    events = [e for e in events if "ru" in e["home"]]
    print(f"Матчей в окне: {len(events)}")

    if state.get("schedule_day") != today and now.hour >= MORNING_HOUR:
        morning(state, events, now)
        state["schedule_day"] = today

    cache = {}

    def fx_loader():
        if "fx" not in cache:
            try:
                cache["fx"] = load_fixtures()
            except Exception as e:
                print(f"  ! football-data недоступен: {e}")
                cache["fx"] = None
        return cache["fx"]

    def hist_loader():
        if "hist" not in cache:
            cache["hist"] = load_history(refresh_current=False, leagues=HIST_LEAGUES)
        return cache["hist"]

    # публикуем в последний запуск, который успевает до «за час»: обзор выходит за 60–80 минут
    lead = pd.Timedelta(minutes=60 + gap_minutes(now))
    for ev in sorted(events, key=lambda e: e["kickoff"]):
        kick = pd.Timestamp(ev["kickoff"])
        if ev["state"] == "pre" and ev["id"] not in matches and now < kick <= now + lead:
            try:
                m = review(ev, w, fx_loader, hist_loader)
            except Exception as e:  # один сломанный матч не должен ронять весь запуск
                print(f"  ! обзор не удался {ev['id']}: {e}")
                continue
            matches[ev["id"]] = m or {"status": "skipped", "kickoff": ev["kickoff"]}
            save_json(MATCHES, matches)

    by_id = {e["id"]: e for e in events}
    for mid, m in matches.items():
        ev = by_id.get(mid)
        if m.get("status") == "reviewed" and ev and ev["completed"] and str(ev["home"]["score"]).isdigit():
            try:
                settle(m, ev)
            except Exception as e:
                print(f"  ! итог не удался {mid}: {e}")
            save_json(MATCHES, matches)

    # храним только последние 3 дня, остальное уже в results.csv
    old = now - pd.Timedelta(days=3)
    matches = {k: v for k, v in matches.items() if pd.Timestamp(v["kickoff"]) > old}
    save_json(MATCHES, matches)
    save_json(STATE, state)
    names.save()


if __name__ == "__main__":
    main()
