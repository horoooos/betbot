"""Модель голов (Пуассон + поправка Диксона-Коулза) и смешивание с рынком.

Каждая команда получает силу атаки и обороны. Свежие матчи весят больше старых
(экспоненциальное затухание), поэтому модель сама подстраивается под форму команд.
"""
import numpy as np
import pandas as pd
from scipy.stats import poisson

MAX_GOALS = 10


class PoissonModel:
    def __init__(self, half_life_days: float = 240, prior_games: float = 4.0, rho: float = -0.08):
        self.xi = np.log(2) / half_life_days
        self.prior = prior_games
        self.rho = rho

    def fit(self, matches: pd.DataFrame, as_of: pd.Timestamp) -> "PoissonModel":
        teams = pd.Index(sorted(set(matches["HomeTeam"]) | set(matches["AwayTeam"])))
        h = teams.get_indexer(matches["HomeTeam"])
        a = teams.get_indexer(matches["AwayTeam"])
        hg = matches["FTHG"].to_numpy(float)
        ag = matches["FTAG"].to_numpy(float)
        days = (as_of - matches["Date"]).dt.days.to_numpy(float)
        w = np.exp(-self.xi * np.clip(days, 0, None))

        n = len(teams)
        att = np.ones(n)
        dfn = np.ones(n)
        home = (w * hg).sum() / (w * ag).sum()
        g = (w * (hg + ag)).sum() / (2 * w.sum())  # средние голы одной команды
        k = self.prior * g  # псевдонаблюдения тянут новые команды к среднему

        for _ in range(40):
            # атака: забитые / ожидаемые при силе 1
            num = np.bincount(h, w * hg, n) + np.bincount(a, w * ag, n)
            den = np.bincount(h, w * dfn[a] * home * g, n) + np.bincount(a, w * dfn[h] * g, n)
            att = (num + k) / (den + k)
            # оборона: пропущенные / ожидаемые
            num = np.bincount(h, w * ag, n) + np.bincount(a, w * hg, n)
            den = np.bincount(h, w * att[a] * g, n) + np.bincount(a, w * att[h] * home * g, n)
            dfn = (num + k) / (den + k)
            dfn /= np.exp(np.log(dfn).mean())
            home = (w * hg).sum() / (w * att[h] * dfn[a] * g).sum()

        self.teams, self.att, self.dfn, self.home, self.g = teams, att, dfn, home, g
        return self

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        def idx(t):
            i = self.teams.get_indexer([t])[0]
            return i
        i, j = idx(home_team), idx(away_team)
        # незнакомая команда (только что вышла в лигу) — слабее среднего
        ai, di = (self.att[i], self.dfn[i]) if i >= 0 else (0.85, 1.15)
        aj, dj = (self.att[j], self.dfn[j]) if j >= 0 else (0.85, 1.15)
        return ai * dj * self.home * self.g, aj * di * self.g

    def probs(self, home_team: str, away_team: str) -> dict:
        lh, la = self.expected_goals(home_team, away_team)
        x = np.arange(MAX_GOALS + 1)
        m = np.outer(poisson.pmf(x, lh), poisson.pmf(x, la))
        # Диксон-Коулз: поправка на ничьи 0:0 и 1:1
        r = self.rho
        m[0, 0] *= 1 - lh * la * r
        m[0, 1] *= 1 + lh * r
        m[1, 0] *= 1 + la * r
        m[1, 1] *= 1 - r
        m /= m.sum()
        total = x[:, None] + x[None, :]
        return {
            "H": np.tril(m, -1).sum(), "D": np.trace(m), "A": np.triu(m, 1).sum(),
            "O25": m[total > 2.5].sum(), "U25": m[total < 2.5].sum(),
            "xgH": lh, "xgA": la,
        }


def market_probs(odds: list[float]) -> np.ndarray:
    """Вероятности из коэффициентов без маржи букмекера."""
    inv = 1 / np.asarray(odds, float)
    return inv / inv.sum()


def blend(p_model: np.ndarray, p_market: np.ndarray, w: float) -> np.ndarray:
    """Логарифмическое смешивание: w=1 — верим только модели, w=0 — только рынку."""
    p = np.power(p_model, w) * np.power(p_market, 1 - w)
    return p / p.sum()


def learn_blend_weight(pm: np.ndarray, pk: np.ndarray, outcome: np.ndarray) -> float:
    """Подбираем вес модели, при котором прогнозы на прошлых матчах были точнее всего.

    pm, pk — массивы (N, K) вероятностей модели и рынка, outcome — индексы исходов.
    """
    best_w, best_ll = 0.0, np.inf
    for w in np.linspace(0, 1, 21):
        p = np.power(pm, w) * np.power(pk, 1 - w)
        p /= p.sum(axis=1, keepdims=True)
        ll = -np.log(p[np.arange(len(p)), outcome] + 1e-12).mean()
        if ll < best_ll:
            best_w, best_ll = w, ll
    return float(best_w)
