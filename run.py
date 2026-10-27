"""Один запуск бота. На GitHub Actions запускается каждые 30 минут.

Что делает:
  • раз в день — скачивает результаты, переобучается и публикует итоги value-ставок;
  • каждый запуск — выпускает прогнозы на матчи, до которых осталось < 36 часов (каждый матч один раз);
  • каждый запуск — обновляет закреплённое live-табло со счётом всех матчей дня.

Запуск:  python run.py   (без TELEGRAM_TOKEN посты печатаются в консоль)
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from betbot import posts, telegram
from betbot.data import MSK, load_fixtures, load_history
from betbot.engine import (add_market, blended, find_value, fit_full, fit_weights, predict_rows,
                           settle, walk_forward)
from betbot.leagues import ORDER
from betbot.live import scoreboard

DATA = Path(__file__).resolve().parent / "data"
STATE, FORECASTS, PICKS = DATA / "state.json", DATA / "forecasts.csv", DATA / "picks.csv"
MIN_EDGE = 0.05                      # минимальный перевес для value-ставки
MAX_EDGE = 0.30
HORIZON = pd.Timedelta(hours=36)     # за сколько до матча публикуем прогноз
LEARN = pd.Timedelta(days=2 * 365)   # на каком периоде переобучаем вес модели
MATCH = ["Div", "Date", "HomeTeam", "AwayTeam"]
PICK_KEY = MATCH + ["market", "side"]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"])
    if "Kickoff" in df:
        df["Kickoff"] = pd.to_datetime(df["Kickoff"], utc=True).dt.tz_convert(MSK)
    return df


def keys(df: pd.DataFrame) -> pd.Series:
    return df["Div"] + "|" + df["Date"].dt.strftime("%Y-%m-%d") + "|" + df["HomeTeam"] + "|" + df["AwayTeam"]


def learn(hist: pd.DataFrame, now: pd.Timestamp) -> dict:
    preds = add_market(walk_forward(hist, start=str((now - LEARN).date())))
    return fit_weights(preds)


def forecast(hist: pd.DataFrame, fx: pd.DataFrame, now: pd.Timestamp, w: dict) -> pd.DataFrame:
    counts = hist["Div"].value_counts()
    parts = []
    for code, rows in fx.groupby("Div"):
        if counts.get(code, 0) < 200:  # слишком мало истории для модели
            continue
        parts.append(predict_rows(fit_full(hist, code, now), rows))
    if not parts:
        return pd.DataFrame()
    fc = add_market(pd.concat(parts, ignore_index=True))
    p1x2 = np.array([blended(r, "1X2", w) for r in fc.itertuples()])
    fc["pH"], fc["pD"], fc["pA"] = p1x2[:, 0], p1x2[:, 1], p1x2[:, 2]
    fc["pO"] = [blended(r, "OU25", w)[0] for r in fc.itertuples()]
    return fc


def post_forecasts(hist, now, w) -> None:
    fx = load_fixtures()
    fx = fx[(fx["Kickoff"] > now) & (fx["Kickoff"] <= now + HORIZON)]
    old = read_csv(FORECASTS)
    if len(old):
        fx = fx[~keys(fx).isin(set(keys(old)))]
    if fx.empty:
        print("Новых матчей для прогноза нет")
        return
    fc = forecast(hist, fx, now.tz_localize(None), w)
    if fc.empty:
        return
    picks = find_value(fc, w, MIN_EDGE, "max")
    if len(picks):
        # тоталы на истории в минусе, пока модель не доказала, что лучше рынка; перевес > 30% — почти
        # всегда ошибка в коэффициентах
        picks = picks[((picks["market"] == "1X2") | (w["OU25"] > 0)) & (picks["edge"] <= MAX_EDGE)]
    for code in sorted(fc["Div"].unique(), key=lambda c: ORDER.get(c, 999)):
        lp = picks[picks["Div"] == code] if len(picks) else picks
        telegram.send(posts.league_post(code, fc[fc["Div"] == code], lp, w))

    cols = MATCH + ["Kickoff", "pH", "pD", "pA", "pO", "m_xgH", "m_xgA", "m_score"]
    save = fc[cols].rename(columns={"m_xgH": "xgH", "m_xgA": "xgA", "m_score": "score"})
    pd.concat([old, save], ignore_index=True).to_csv(FORECASTS, index=False)
    if len(picks):
        allp = pd.concat([read_csv(PICKS), picks.assign(reported=False)], ignore_index=True)
        allp.drop_duplicates(PICK_KEY).to_csv(PICKS, index=False)
    print(f"Опубликовано прогнозов: {len(fc)}, value-ставок: {len(picks)}")


def post_results(hist) -> None:
    allp = read_csv(PICKS)
    if allp.empty:
        return
    res = hist[MATCH + ["FTHG", "FTAG"]]
    allp = allp.drop(columns=["FTHG", "FTAG", "won", "profit"], errors="ignore").merge(res, on=MATCH, how="left")
    done = settle(allp)
    if done.empty:
        allp.to_csv(PICKS, index=False)
        return
    allp = allp.merge(done[PICK_KEY + ["won", "profit"]], on=PICK_KEY, how="left")
    fresh = allp[allp["profit"].notna() & ~allp["reported"].astype(bool)]
    if len(fresh):
        telegram.send(posts.results_post(fresh, allp[allp["profit"].notna()]))
        allp.loc[fresh.index, "reported"] = True
    allp.to_csv(PICKS, index=False)


def update_live(state: dict, now: pd.Timestamp) -> None:
    sb = scoreboard(now)
    if sb.empty:
        print("Сегодня матчей нет — табло не нужно")
        return
    text = posts.live_board(sb, read_csv(FORECASTS), now)
    digest = hashlib.md5(text.split("обновлено")[0].encode() + text.split("\n", 3)[-1].encode()).hexdigest()
    today = str(now.date())
    lv = state.get("live", {})
    if lv.get("date") == today and lv.get("id"):
        if lv.get("hash") == digest:
            return  # ничего не поменялось
        if telegram.edit(lv["id"], text):
            lv["hash"] = digest
            state["live"] = lv
            return
    ids = telegram.send(text, silent=True)  # новый день (или табло удалили) — новое сообщение
    telegram.pin(ids[0])
    state["live"] = {"date": today, "id": ids[0], "hash": digest}


def main():
    DATA.mkdir(exist_ok=True)
    now = pd.Timestamp.now(tz=MSK)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    daily = state.get("learned") != str(now.date())

    print("1/4 Загружаю результаты" + (" и обновляю базу..." if daily else " из кэша..."))
    hist = load_history(refresh_current=daily)
    if daily or "weights" not in state:
        print("2/4 Переобучаюсь на последних двух годах...")
        state["weights"] = learn(hist, now.tz_localize(None))
        state["learned"] = str(now.date())
        print(f"    вес модели: {state['weights']}")
        post_results(hist)
    print("3/4 Прогнозы на ближайшие матчи...")
    post_forecasts(hist, now, state["weights"])
    print("4/4 Live-табло...")
    update_live(state, now)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
