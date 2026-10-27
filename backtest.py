"""Проверка на прошлых сезонах: как бы бот отработал, если бы был запущен раньше.

Запуск:  python backtest.py
"""
import numpy as np
import pandas as pd

from betbot.data import load_history
from betbot.engine import add_market, find_value, fit_weights, outcomes, settle, walk_forward

pd.set_option("display.width", 160)


def logloss(df):
    o = outcomes(df)["1X2"]
    pm = df[["m_H", "m_D", "m_A"]].to_numpy()
    pk = df[["k_H", "k_D", "k_A"]].to_numpy()
    idx = np.arange(len(df))
    return -np.log(pm[idx, o]).mean(), -np.log(pk[idx, o]).mean()


def main():
    print("Загружаю данные...")
    hist = load_history(2019, leagues=["E0", "SP1", "I1", "D1", "F1"])
    print("Прогоняю модель неделя за неделей (только прошлое → будущее)...")
    preds = add_market(walk_forward(hist, start="2021-07-01")).dropna(subset=["k_H", "k_O25"])
    preds["SeasonStart"] = preds["Season"].str[:2].astype(int)

    mll, kll = logloss(preds)
    print(f"\nТочность 1X2 (log-loss, меньше = лучше): модель {mll:.4f}, рынок {kll:.4f}")

    rows = []
    all_bets = []
    seasons = sorted(preds["Season"].unique())
    for season in seasons[1:]:
        past = preds[preds["Season"] < season]
        test = preds[preds["Season"] == season]
        w = fit_weights(past)  # вес выучен только на прошлых сезонах
        for edge in (0.03, 0.05, 0.08):
            for col in ("avg", "max"):
                b = settle(find_value(test, w, edge, col))
                if len(b):
                    b["Season"], b["min_edge"], b["odds_type"] = season, edge, col
                    all_bets.append(b)
        rows.append({"season": season, "w_1X2": w["1X2"], "w_OU25": w["OU25"]})

    print("\nСколько бот доверял модели против рынка (0 = только рынок, 1 = только модель):")
    print(pd.DataFrame(rows).to_string(index=False))

    bets = pd.concat(all_bets, ignore_index=True)
    summary = (bets.groupby(["odds_type", "min_edge", "market"])
               .agg(ставок=("profit", "size"), выигрышей=("won", "mean"), прибыль=("profit", "sum"))
               .reset_index())
    summary["ROI_%"] = 100 * summary["прибыль"] / summary["ставок"]
    summary["выигрышей"] = (100 * summary["выигрышей"]).round(1)
    print("\nИтог по стратегиям (ставка = 1 единица):")
    print(summary.round(2).to_string(index=False))

    by_season = (bets[(bets["odds_type"] == "avg") & (bets["min_edge"] == 0.05)]
                 .groupby(["Season", "market"])["profit"].agg(["size", "sum"]))
    by_season["ROI_%"] = 100 * by_season["sum"] / by_season["size"]
    print("\nПо сезонам (средние коэффициенты, перевес ≥ 5%):")
    print(by_season.round(2).to_string())

    bets.to_csv("data/backtest_bets.csv", index=False)
    print("\nВсе ставки сохранены в data/backtest_bets.csv")


if __name__ == "__main__":
    main()
