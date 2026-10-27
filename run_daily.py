"""Ежедневный запуск бота: дообучение → прогнозы → отправка в Telegram → учёт результатов.

Запуск:  python run_daily.py
"""
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

from betbot import telegram
from betbot.data import LEAGUES, load_fixtures, load_history
from betbot.engine import (SIDE_NAMES, add_market, find_value, fit_full, fit_weights,
                           predict_rows, settle, walk_forward)

MIN_EDGE = 0.05      # минимальный перевес, чтобы считать ставку value
LEARN_SEASONS = 2    # на скольких последних сезонах переобучаем вес модели
PICKS = Path(__file__).resolve().parent / "data" / "picks.csv"
KEY = ["Date", "HomeTeam", "AwayTeam", "market", "side"]


def learn(hist: pd.DataFrame) -> dict[str, float]:
    start = pd.Timestamp(date.today()) - pd.Timedelta(days=365 * LEARN_SEASONS)
    preds = add_market(walk_forward(hist, start=str(start.date())))
    return fit_weights(preds)


def forecast(hist: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    parts = []
    for league, rows in fixtures.groupby("Div"):
        model = fit_full(hist, league, today)
        parts.append(predict_rows(model, rows))
    return add_market(pd.concat(parts, ignore_index=True))


def update_picks(new: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    old = pd.read_csv(PICKS, parse_dates=["Date"]) if PICKS.exists() else pd.DataFrame()
    allp = pd.concat([old, new], ignore_index=True)
    if allp.empty:
        return allp
    allp = allp.drop_duplicates(subset=KEY, keep="first")  # фиксируем первый (ранний) прогноз
    res = hist[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]
    allp = allp.drop(columns=["FTHG", "FTAG", "won", "profit"], errors="ignore").merge(
        res, on=["Date", "HomeTeam", "AwayTeam"], how="left")
    settled = settle(allp)
    if not settled.empty:
        allp = allp.merge(settled[KEY + ["won", "profit"]], on=KEY, how="left")
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    allp.sort_values("Date").to_csv(PICKS, index=False)
    return allp


def fmt_pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def build_message(fc: pd.DataFrame, picks: pd.DataFrame, all_picks: pd.DataFrame, w: dict) -> str:
    lines = [f"<b>⚽ Прогнозы на {date.today():%d.%m.%Y}</b>",
             f"Доверие к модели (переобучено сегодня): 1X2 — {fmt_pct(w['1X2'])}, "
             f"тоталы — {fmt_pct(w['OU25'])}. Остальное — оценка рынка."]

    upcoming = fc[fc["Date"] >= pd.Timestamp(date.today())]
    for league, g in upcoming.groupby("Div"):
        block = [f"<b>{LEAGUES[league]}</b>"]
        for r in g.sort_values("Date").itertuples():
            ph = r.m_H ** w["1X2"] * r.k_H ** (1 - w["1X2"])
            pd_ = r.m_D ** w["1X2"] * r.k_D ** (1 - w["1X2"])
            pa = r.m_A ** w["1X2"] * r.k_A ** (1 - w["1X2"])
            s = ph + pd_ + pa
            block.append(
                f"{r.Date:%d.%m} {escape(r.HomeTeam)} — {escape(r.AwayTeam)}: "
                f"П1 {fmt_pct(ph / s)} · Х {fmt_pct(pd_ / s)} · П2 {fmt_pct(pa / s)} "
                f"(xG {r.m_xgH:.1f}:{r.m_xgA:.1f})")
        lines.append("\n".join(block))

    if picks.empty:
        lines.append("💡 <b>Value-ставок сегодня нет</b> — нигде нет перевеса ≥ "
                     f"{fmt_pct(MIN_EDGE)}. Это нормально: лучше пропустить, чем играть в минус.")
    else:
        block = [f"💡 <b>Value-кандидаты</b> (перевес ≥ {fmt_pct(MIN_EDGE)}, по лучшему коэффициенту):"]
        for r in picks.itertuples():
            block.append(f"• {escape(r.HomeTeam)} — {escape(r.AwayTeam)}: <b>{SIDE_NAMES[r.side]}</b> "
                         f"@ {r.odds:.2f} (вероятность {fmt_pct(r.prob)}, перевес +{100 * r.edge:.1f}%)")
        lines.append("\n".join(block))

    done = all_picks.dropna(subset=["profit"]) if "profit" in all_picks else pd.DataFrame()
    if len(done):
        roi = 100 * done["profit"].sum() / len(done)
        lines.append(f"📊 <b>Честная статистика бота</b>: {len(done)} ставок, "
                     f"угадано {fmt_pct(done['won'].mean())}, "
                     f"прибыль {done['profit'].sum():+.2f} ед., ROI {roi:+.1f}%")
    lines.append("<i>Это не финансовый совет. Ставьте только то, что не жалко потерять.</i>")
    return "\n\n".join(lines)


def main():
    print("1/4 Загружаю результаты...")
    hist = load_history(2019)
    print("2/4 Переобучаюсь на последних сезонах...")
    w = learn(hist)
    print(f"    вес модели: {w}")
    print("3/4 Считаю прогнозы на ближайшие матчи...")
    fixtures = load_fixtures()
    if fixtures.empty:
        fc, picks = pd.DataFrame(columns=["Date", "Div"]), pd.DataFrame()
    else:
        fc = forecast(hist, fixtures)
        picks = find_value(fc, w, MIN_EDGE, "max")
    all_picks = update_picks(picks, hist)
    print("4/4 Отправляю в Telegram...")
    telegram.send(build_message(fc, picks, all_picks, w))


if __name__ == "__main__":
    main()
