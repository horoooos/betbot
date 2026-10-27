"""Все рынки ставок из одной модели голов.

Из коэффициентов букмекеров восстанавливаем ожидаемые голы каждой команды (λ), строим матрицу
вероятностей всех счетов и из неё считаем любые рынки: исход, двойной шанс, обе забьют, тоталы,
индивидуальные тоталы, форы, точный счёт.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

MAXG = 10
RHO = -0.08
MARGIN = 0.93  # если реального коэффициента нет — считаем «справедливый» минус типичная маржа

# key: (группа, название, условие выигрыша по счёту i:j)
MARKETS = {
    "H": ("Исход", "П1", lambda i, j: i > j),
    "D": ("Исход", "Ничья", lambda i, j: i == j),
    "A": ("Исход", "П2", lambda i, j: i < j),
    "1X": ("Двойной шанс", "1X", lambda i, j: i >= j),
    "12": ("Двойной шанс", "12 (без ничьей)", lambda i, j: i != j),
    "X2": ("Двойной шанс", "X2", lambda i, j: i <= j),
    "BTTS_Y": ("Обе забьют", "Обе забьют — да", lambda i, j: i > 0 and j > 0),
    "BTTS_N": ("Обе забьют", "Обе забьют — нет", lambda i, j: i == 0 or j == 0),
    "O15": ("Тотал", "ТБ 1.5", lambda i, j: i + j > 1.5),
    "U15": ("Тотал", "ТМ 1.5", lambda i, j: i + j < 1.5),
    "O25": ("Тотал", "ТБ 2.5", lambda i, j: i + j > 2.5),
    "U25": ("Тотал", "ТМ 2.5", lambda i, j: i + j < 2.5),
    "O35": ("Тотал", "ТБ 3.5", lambda i, j: i + j > 3.5),
    "U35": ("Тотал", "ТМ 3.5", lambda i, j: i + j < 3.5),
    "H_O05": ("Инд. тотал", "ИТ1 больше 0.5", lambda i, j: i > 0),
    "H_O15": ("Инд. тотал", "ИТ1 больше 1.5", lambda i, j: i > 1),
    "A_O05": ("Инд. тотал", "ИТ2 больше 0.5", lambda i, j: j > 0),
    "A_O15": ("Инд. тотал", "ИТ2 больше 1.5", lambda i, j: j > 1),
    "H-1.5": ("Фора", "Ф1 (−1.5)", lambda i, j: i - j >= 2),
    "A+1.5": ("Фора", "Ф2 (+1.5)", lambda i, j: j - i >= -1),
    "A-1.5": ("Фора", "Ф2 (−1.5)", lambda i, j: j - i >= 2),
    "H+1.5": ("Фора", "Ф1 (+1.5)", lambda i, j: i - j >= -1),
}


MAIN_POOL = ["H", "A", "1X", "X2", "12", "BTTS_Y", "BTTS_N", "O25", "U25", "O35",
             "H-1.5", "A-1.5", "H_O15", "A_O15"]


def matrix(lh: float, la: float, rho: float = RHO) -> np.ndarray:
    x = np.arange(MAXG + 1)
    m = np.outer(poisson.pmf(x, lh), poisson.pmf(x, la))
    m[0, 0] *= 1 - lh * la * rho
    m[0, 1] *= 1 + lh * rho
    m[1, 0] *= 1 + la * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()


def _p(m: np.ndarray, cond) -> float:
    return float(sum(m[i, j] for i in range(MAXG + 1) for j in range(MAXG + 1) if cond(i, j)))


def fair(odds: list[float]) -> np.ndarray:
    inv = 1 / np.asarray(odds, float)
    return inv / inv.sum()


def implied_lambdas(p1x2: np.ndarray, line: float | None = None, p_over: float | None = None) -> tuple[float, float]:
    """Ожидаемые голы команд, при которых модель повторяет вероятности рынка."""
    def loss(v):
        lh, la = np.exp(v)
        m = matrix(lh, la)
        err = (np.tril(m, -1).sum() - p1x2[0]) ** 2 + (np.trace(m) - p1x2[1]) ** 2 + (np.triu(m, 1).sum() - p1x2[2]) ** 2
        if line is not None and p_over is not None:
            err += (_p(m, lambda i, j: i + j > line) - p_over) ** 2
        return err
    res = minimize(loss, np.log([1.4, 1.1]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-9})
    lh, la = np.exp(res.x)
    return float(lh), float(la)


def all_markets(lh: float, la: float) -> dict:
    m = matrix(lh, la)
    out = {k: _p(m, cond) for k, (_, _, cond) in MARKETS.items()}
    flat = sorted(((m[i, j], f"{i}:{j}") for i in range(6) for j in range(6)), reverse=True)
    out["scores"] = [(s, float(p)) for p, s in flat[:3]]
    return out


def won(key: str, hs: int, as_: int) -> bool:
    if key.startswith("CS_"):
        return key == f"CS_{hs}:{as_}"
    return bool(MARKETS[key][2](hs, as_))


def label(key: str) -> str:
    if key.startswith("CS_"):
        return f"Точный счёт {key[3:]}"
    return MARKETS[key][1]


def tips(probs: dict, real_odds: dict) -> tuple[dict, dict]:
    """Основной прогноз (самый надёжный с нормальным кэфом) и смелый (кэф 2.0–3.6)."""
    def odds_for(k):
        o = real_odds.get(k)
        return (round(o, 2), False) if o else (round(MARGIN / probs[k], 2), True)

    cands = [k for k in MARKETS if probs[k] > 0]
    # самый вероятный из «настоящих» рынков, но не пустой (вероятность до 75% ≈ кэф от 1.3)
    pool = [k for k in MAIN_POOL if probs[k] <= 0.75] or MAIN_POOL
    main_k = max(pool, key=probs.get)
    bold_pool = [k for k in cands if 2.0 <= odds_for(k)[0] <= 3.6 and k != main_k]
    bold_k = max(bold_pool, key=lambda k: probs[k]) if bold_pool else None

    def pack(k):
        if k is None:
            return {}
        o, est = odds_for(k)
        return {"key": k, "label": label(k), "p": round(probs[k], 4), "odds": o, "est": est}
    return pack(main_k), pack(bold_k)
