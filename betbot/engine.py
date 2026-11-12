"""Прогон модели «как в реальности»: на каждую неделю модель видит только прошлое."""
import numpy as np
import pandas as pd

from .model import PoissonModel, blend, learn_blend_weight, market_probs

WINDOW_DAYS = 3 * 365
MARKETS = {
    "1X2": {"sides": ["H", "D", "A"], "avg": ["AvgH", "AvgD", "AvgA"], "max": ["MaxH", "MaxD", "MaxA"],
            "sharp": ["PSH", "PSD", "PSA"]},
    "OU25": {"sides": ["O25", "U25"], "avg": ["Avg>2.5", "Avg<2.5"], "max": ["Max>2.5", "Max<2.5"],
             "sharp": None},
}
SIDE_NAMES = {"H": "П1", "D": "Ничья", "A": "П2", "O25": "ТБ 2.5", "U25": "ТМ 2.5"}


def predict_rows(model: PoissonModel, rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    preds = [model.probs(r.HomeTeam, r.AwayTeam) for r in rows.itertuples()]
    for key in ["H", "D", "A", "O25", "U25", "xgH", "xgA", "score"]:
        out["m_" + key] = [p[key] for p in preds]
    return out


def blended(row, market: str, weights: dict[str, float]) -> list[float]:
    """Итоговые вероятности исходов для одной строки: модель + рынок с выученным весом."""
    sides = MARKETS[market]["sides"]
    pm = np.array([getattr(row, "m_" + s) for s in sides])
    pk = np.array([getattr(row, "k_" + s, np.nan) for s in sides])
    if np.isnan(pk).any():
        return list(pm)
    return list(blend(pm, pk, weights[market]))


def walk_forward(history: pd.DataFrame, start: str, **model_kw) -> pd.DataFrame:
    """Честные прогнозы для всех матчей начиная с даты start."""
    parts = []
    for league, df in history.groupby("Div"):
        df = df.sort_values("Date")
        test = df[df["Date"] >= start]
        for week_start, rows in test.groupby(test["Date"].dt.to_period("W").dt.start_time):
            train = df[(df["Date"] < week_start) & (df["Date"] >= week_start - pd.Timedelta(days=WINDOW_DAYS))]
            if len(train) < 200:
                continue
            model = PoissonModel(**model_kw).fit(train, week_start)
            parts.append(predict_rows(model, rows))
    return pd.concat(parts, ignore_index=True).sort_values("Date").reset_index(drop=True)


def add_market(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет вероятности рынка (без маржи) для каждого исхода."""
    df = df.copy()
    odd_cols = [c for spec in MARKETS.values() for k in ("avg", "max", "sharp") for c in (spec[k] or [])]
    for c in odd_cols:
        if c in df:  # битые коэффициенты (0, 1.0, пусто) не должны ломать обучение
            df[c] = df[c].where(df[c] > 1.01)
    for mk, spec in MARKETS.items():
        cols = spec["avg"]
        if spec["sharp"] and all(c in df for c in spec["sharp"]):
            sharp = df[spec["sharp"]].notna().all(axis=1)
            src = np.where(sharp.to_numpy()[:, None], df[spec["sharp"]].to_numpy(float), df[cols].to_numpy(float))
        else:
            src = df[cols].to_numpy(float)
        inv = 1 / src
        p = inv / inv.sum(axis=1, keepdims=True)
        for i, s in enumerate(spec["sides"]):
            df["k_" + s] = p[:, i]
    return df


def outcomes(df: pd.DataFrame) -> dict[str, np.ndarray]:
    gd = df["FTHG"] - df["FTAG"]
    res = np.where(gd > 0, 0, np.where(gd == 0, 1, 2))
    ou = np.where(df["FTHG"] + df["FTAG"] > 2.5, 0, 1)
    return {"1X2": res, "OU25": ou}


def fit_weights(df: pd.DataFrame) -> dict[str, float]:
    """Учимся на прошлом: сколько доверять модели против рынка."""
    df = df.dropna(subset=[f"k_{s}" for spec in MARKETS.values() for s in spec["sides"]])
    out = outcomes(df)
    w = {}
    for mk, spec in MARKETS.items():
        pm = df[["m_" + s for s in spec["sides"]]].to_numpy()
        pk = df[["k_" + s for s in spec["sides"]]].to_numpy()
        w[mk] = learn_blend_weight(pm, pk, out[mk])
    return w


def find_value(df: pd.DataFrame, weights: dict[str, float], min_edge: float, odds_col: str = "avg",
               max_odds: float = 6.0) -> pd.DataFrame:
    """Ставки, где наша вероятность × коэффициент > 1 + min_edge."""
    bets = []
    for mk, spec in MARKETS.items():
        sub = df.dropna(subset=["k_" + s for s in spec["sides"]] + spec[odds_col])
        pm = sub[["m_" + s for s in spec["sides"]]].to_numpy()
        pk = sub[["k_" + s for s in spec["sides"]]].to_numpy()
        p = np.power(pm, weights[mk]) * np.power(pk, 1 - weights[mk])
        p /= p.sum(axis=1, keepdims=True)
        odds = sub[spec[odds_col]].to_numpy(float)
        ev = p * odds - 1
        for i, s in enumerate(spec["sides"]):
            mask = (ev[:, i] > min_edge) & (odds[:, i] <= max_odds)
            if mask.any():
                b = sub.loc[mask, ["Div", "Date", "HomeTeam", "AwayTeam"]].copy()
                b["market"], b["side"] = mk, s
                b["prob"], b["odds"], b["edge"] = p[mask, i], odds[mask, i], ev[mask, i]
                for c in ("FTHG", "FTAG"):
                    if c in sub:
                        b[c] = sub.loc[mask, c]
                bets.append(b)
    if not bets:
        return pd.DataFrame()
    return pd.concat(bets, ignore_index=True).sort_values(["Date", "edge"], ascending=[True, False])


def settle(bets: pd.DataFrame) -> pd.DataFrame:
    """Считает выигрыш/проигрыш ставки в 1 единицу."""
    if bets.empty or "FTHG" not in bets:
        return pd.DataFrame()
    b = bets.dropna(subset=["FTHG", "FTAG"]).copy()
    hg, ag = b["FTHG"], b["FTAG"]
    won = np.select(
        [b["side"] == "H", b["side"] == "D", b["side"] == "A", b["side"] == "O25", b["side"] == "U25"],
        [hg > ag, hg == ag, hg < ag, hg + ag > 2.5, hg + ag < 2.5],
    )
    b["won"] = won.astype(bool)
    b["profit"] = np.where(b["won"], b["odds"] - 1, -1.0)
    return b


def fit_full(history: pd.DataFrame, league: str, as_of: pd.Timestamp, **model_kw) -> PoissonModel:
    df = history[(history["Div"] == league) & (history["Date"] >= as_of - pd.Timedelta(days=WINDOW_DAYS))]
    return PoissonModel(**model_kw).fit(df, as_of)

def fit_weights_lambda(df: pd.DataFrame, rho: float = -0.08, max_rows: int = 8000) -> dict[str, float]:
    """Вес модели, выученный в той же шкале, в которой применяется — по лямбдам.

    Раньше вес подбирался на смеси вероятностей, а применялся к λ в run.lambdas — это разные операции.
    Здесь обучение и применение идут в λ: для каждого w берём λ = модель^w · рынок^(1−w), строим
    матрицу счёта (Пуассон + поправка Диксона-Коулза) и считаем log-loss 1X2 и ТБ/ТМ 2.5.
    Считаем векторизованно и не больше max_rows матчей — иначе переобучение занимает минуты.
    """
    from scipy.stats import poisson

    from .markets import implied_lambdas
    sub = df.dropna(subset=["k_H", "k_D", "k_A", "m_xgH", "m_xgA", "FTHG", "FTAG"])
    if len(sub) < 200:
        return {"1X2": 0.0, "OU25": 0.0}
    if len(sub) > max_rows:
        sub = sub.sample(max_rows, random_state=1)
    lams = np.array([implied_lambdas([r.k_H, r.k_D, r.k_A]) for r in sub.itertuples()], float)
    kl, ka = lams[:, 0], lams[:, 1]
    ml = sub["m_xgH"].to_numpy(float)
    ma = sub["m_xgA"].to_numpy(float)
    hg, ag = sub["FTHG"].to_numpy(int), sub["FTAG"].to_numpy(int)
    res_out = np.where(hg > ag, 0, np.where(hg == ag, 1, 2))
    ou_out = np.where(hg + ag > 2.5, 0, 1)
    x = np.arange(11)
    tot = x[:, None] + x[None, :]
    mask_h, mask_d, mask_a = np.tril(np.ones((11, 11)), -1).astype(bool), np.eye(11, dtype=bool), np.triu(np.ones((11, 11)), 1).astype(bool)
    best = {"1X2": (np.inf, 0.0), "OU25": (np.inf, 0.0)}
    for w in np.linspace(0, 1, 21):
        lh = np.power(ml, w) * np.power(kl, 1 - w)
        la = np.power(ma, w) * np.power(ka, 1 - w)
        m = poisson.pmf(x[None, :], lh[:, None])[:, :, None] * poisson.pmf(x[None, :], la[:, None])[:, None, :]
        m[:, 0, 0] *= 1 - lh * la * rho
        m[:, 0, 1] *= 1 + lh * rho
        m[:, 1, 0] *= 1 + la * rho
        m[:, 1, 1] *= 1 - rho
        m /= m.sum(axis=(1, 2), keepdims=True)
        p1x2 = np.stack([(m * mask_h).sum(axis=(1, 2)), (m * mask_d).sum(axis=(1, 2)),
                         (m * mask_a).sum(axis=(1, 2))], axis=1)
        p_ou = np.stack([m[:, tot > 2.5].sum(axis=1), m[:, tot < 2.5].sum(axis=1)], axis=1)
        ll1 = -np.log(p1x2[np.arange(len(sub)), res_out] + 1e-12).mean()
        ll2 = -np.log(p_ou[np.arange(len(sub)), ou_out] + 1e-12).mean()
        if ll1 < best["1X2"][0]:
            best["1X2"] = (ll1, float(w))
        if ll2 < best["OU25"][0]:
            best["OU25"] = (ll2, float(w))
    return {"1X2": best["1X2"][1], "OU25": best["OU25"][1]}

