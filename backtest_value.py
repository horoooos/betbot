"""Проверка стратегий на истории топ-лиг (football-data.co.uk, 5 сезонов).

Запуск: python backtest_value.py  → таблица в консоли и data/backtest_value_log.txt

Что сравниваем (ставка всегда 1 единица, считаем ROI = прибыль / сумма ставок):
  1. «Бот сейчас» — на каждый матч основной прогноз как в боте: среди П1/Х/П2/ТБ2.5/ТМ2.5 с кэфом от 1.5
     и вероятностью от 45% — максимум «вероятность × средний кэф»; ставим по среднему кэфу.
  2. «Лучший кэф» — ставим только когда у обычного букмекера (Bet365, BetWin, William Hill, 1xBet) кэф
     выше справедливого кэфа Pinnacle (без маржи) на заданный процент.
Обе стратегии проверяем по линии за 1–3 дня до матча и по линии закрытия (бот публикует за час — ближе к ней).
CLV — насколько взятый кэф лучше справедливого кэфа Pinnacle на закрытии: главный признак настоящего перевеса.
"""
import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

LEAGUES = ["E0", "E1", "SP1", "I1", "D1", "F1", "N1", "P1", "T1", "B1", "SC0"]
SEASONS = ["2122", "2223", "2324", "2425", "2526"]
CACHE = Path(__file__).resolve().parent / "data" / "raw" / "backtest"
LOG = Path(__file__).resolve().parent / "data" / "backtest_value_log.txt"
SOFT = ["B365", "BW", "WH", "1XB"]  # обычные букмекеры; Pinnacle — эталон, его не берём
OUT = {"H": "H", "D": "D", "A": "A"}


def load() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    frames = []
    for s in SEASONS:
        for lg in LEAGUES:
            f = CACHE / f"{lg}_{s}.csv"
            if not f.exists() or s == SEASONS[-1]:
                r = requests.get(f"https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv", timeout=60)
                if r.status_code != 200:
                    continue
                f.write_bytes(r.content)
            try:
                d = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip")
            except Exception:
                continue
            frames.append(d.assign(season=s))
    df = pd.concat(frames, ignore_index=True)
    text = {"Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTR", "HTR", "Referee", "season"}
    for col in df.columns.difference(list(text)):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["FTHG", "FTAG"])


def fair(*cols) -> np.ndarray:
    inv = np.column_stack([1 / c for c in cols])
    return inv / inv.sum(axis=1, keepdims=True)


def build(df: pd.DataFrame, close: bool) -> dict:
    """По каждому исходу: справедливая вероятность Pinnacle, средний кэф, лучший обычный кэф, итог."""
    c = "C" if close else ""
    hg, ag = df["FTHG"].astype(int), df["FTAG"].astype(int)
    res = {"H": hg > ag, "D": hg == ag, "A": hg < ag, "O25": hg + ag > 2, "U25": hg + ag < 3}
    p1x2 = fair(df[f"PS{c}H"], df[f"PS{c}D"], df[f"PS{c}A"])
    pou = fair(df[f"P{c}>2.5"], df[f"P{c}<2.5"])
    pou_avg = fair(df[f"Avg{c}>2.5"], df[f"Avg{c}<2.5"])
    out = {}
    for i, k in enumerate("HDA"):
        soft = df[[f"{b}{c}{k}" for b in SOFT if f"{b}{c}{k}" in df]].max(axis=1)
        out[k] = {"p": p1x2[:, i], "p_bot": p1x2[:, i], "avg": df[f"Avg{c}{k}"], "best": soft, "win": res[k]}
    for i, (k, side) in enumerate((("O25", ">"), ("U25", "<"))):
        soft = df[[f"B365{c}{side}2.5"]].max(axis=1)
        out[k] = {"p": pou[:, i], "p_bot": pou_avg[:, i], "avg": df[f"Avg{c}{side}2.5"], "best": soft, "win": res[k]}
    # справедливая вероятность на закрытии — для CLV
    pc = fair(df["PSCH"], df["PSCD"], df["PSCA"])
    pcou = fair(df["PC>2.5"], df["PC<2.5"])
    for i, k in enumerate("HDA"):
        out[k]["p_close"] = pc[:, i]
    out["O25"]["p_close"], out["U25"]["p_close"] = pcou[:, 0], pcou[:, 1]
    return out


def stats(odds: pd.Series, win: pd.Series, p_close: pd.Series) -> dict:
    odds, win, p_close = odds.astype(float), win.astype(bool), p_close.astype(float)
    ret = np.where(win, odds - 1, -1.0)
    n = len(ret)
    if n == 0:
        return {"ставок": 0}
    roi = ret.mean()
    se = ret.std(ddof=1) / np.sqrt(n) if n > 1 else 0
    return {"ставок": n, "зашло": f"{100 * win.mean():.1f}%", "ср. кэф": round(odds.mean(), 2),
            "ROI": f"{100 * roi:+.1f}%", "±95%": f"{196 * se:.1f}", "CLV": f"{100 * (odds * p_close - 1).mean():+.1f}%"}


def bot_strategy(m: dict, n: int) -> dict:
    keys = list(m)
    p = np.column_stack([m[k]["p_bot"] for k in keys])
    o = np.column_stack([m[k]["avg"].astype(float) for k in keys])
    ok = (o >= 1.5) & (p >= 0.45) & np.isfinite(o) & np.isfinite(p)
    ev = np.where(ok, p * o, -np.inf)
    pick = ev.argmax(axis=1)
    has = np.isfinite(ev.max(axis=1))
    rows = np.arange(n)[has]
    odds = pd.Series(o[rows, pick[has]])
    win = pd.Series(np.column_stack([m[k]["win"] for k in keys])[rows, pick[has]])
    pc = pd.Series(np.column_stack([m[k]["p_close"] for k in keys])[rows, pick[has]])
    return stats(odds, win, pc)


def value_strategy(m: dict, edge: float, lo: float = 1.5, hi: float = 4.0) -> dict:
    parts = []
    for k, v in m.items():
        best = v["best"].astype(float)
        e = v["p"] * best - 1
        sel = (e >= edge) & (best >= lo) & (best <= hi)
        parts.append(pd.DataFrame({"odds": best[sel], "win": v["win"][sel], "pc": v["p_close"][sel]}))
    d = pd.concat(parts)
    return stats(d["odds"], d["win"], d["pc"])


def main():
    df = load()
    need = ["PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA", "P>2.5", "P<2.5", "PC>2.5", "PC<2.5",
            "AvgH", "AvgD", "AvgA", "AvgCH", "AvgCD", "AvgCA", "Avg>2.5", "Avg<2.5", "AvgC>2.5", "AvgC<2.5"]
    df = df.dropna(subset=need).reset_index(drop=True)
    lines = [f"Матчей: {len(df)} · лиг: {df['Div'].nunique()} · сезоны {SEASONS[0]}–{SEASONS[-1]}\n"]
    for close in (False, True):
        m = build(df, close)
        rows = {"Бот сейчас (средний кэф)": bot_strategy(m, len(df))}
        for edge in (0.0, 0.02, 0.03, 0.05, 0.08):
            rows[f"Лучший кэф, перевес ≥{100 * edge:.0f}%"] = value_strategy(m, edge)
        rows["Лучший кэф ≥3%, любые кэфы"] = value_strategy(m, 0.03, 1.01, 50)
        title = "ЛИНИЯ ЗАКРЫТИЯ (как бот: за час до матча)" if close else "ЛИНИЯ ЗА 1–3 ДНЯ ДО МАТЧА"
        lines.append(f"=== {title} ===")
        lines.append(pd.DataFrame(rows).T.to_string())
        lines.append("")
    # по сезонам — устойчив ли результат лучшей стратегии
    m = build(df, False)
    lines.append("=== Лучший кэф ≥3% (линия до матча) по сезонам ===")
    per = {}
    for s in SEASONS:
        mask = (df["season"] == s).to_numpy()
        ms = {k: {kk: (vv[mask] if hasattr(vv, "__len__") else vv) for kk, vv in v.items()} for k, v in m.items()}
        ms = {k: {kk: (vv.reset_index(drop=True) if isinstance(vv, pd.Series) else vv) for kk, vv in v.items()} for k, v in ms.items()}
        per[s] = value_strategy(ms, 0.03)
    lines.append(pd.DataFrame(per).T.to_string())
    text = "\n".join(lines)
    print(text)
    LOG.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
