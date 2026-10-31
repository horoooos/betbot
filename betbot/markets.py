"""Все рынки ставок из одной модели голов.

Из коэффициентов букмекеров восстанавливаем ожидаемые голы каждой команды (λ), строим матрицу
вероятностей всех счетов и из неё считаем любые рынки: исход, двойной шанс, обе забьют, тоталы,
индивидуальные тоталы, форы, точный счёт.
"""
import numpy as np
import pandas as pd
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
    "H-2.5": ("Фора", "Ф1 (−2.5)", lambda i, j: i - j >= 3),
    "A-2.5": ("Фора", "Ф2 (−2.5)", lambda i, j: j - i >= 3),
    "H+2.5": ("Фора", "Ф1 (+2.5)", lambda i, j: i - j >= -2),
    "A+2.5": ("Фора", "Ф2 (+2.5)", lambda i, j: j - i >= -2),
    # больше линий тотала и индивидуальных тоталов
    "O45": ("Тотал", "ТБ 4.5", lambda i, j: i + j > 4.5),
    "U45": ("Тотал", "ТМ 4.5", lambda i, j: i + j < 4.5),
    "H_O25": ("Инд. тотал", "ИТ1 больше 2.5", lambda i, j: i > 2),
    "A_O25": ("Инд. тотал", "ИТ2 больше 2.5", lambda i, j: j > 2),
    # комбинированные
    "H&O15": ("Комбо", "П1 и ТБ 1.5", lambda i, j: i > j and i + j > 1.5),
    "A&O15": ("Комбо", "П2 и ТБ 1.5", lambda i, j: j > i and i + j > 1.5),
    "H&BTTS": ("Комбо", "П1 и обе забьют", lambda i, j: i > j and j > 0),
    "A&BTTS": ("Комбо", "П2 и обе забьют", lambda i, j: j > i and i > 0),
    "1X&U35": ("Комбо", "1X и ТМ 3.5", lambda i, j: i >= j and i + j < 3.5),
    "X2&U35": ("Комбо", "X2 и ТМ 3.5", lambda i, j: i <= j and i + j < 3.5),
    "BTTS&O25": ("Комбо", "Обе забьют и ТБ 2.5", lambda i, j: i > 0 and j > 0 and i + j > 2.5),
}
# Первый тайм: модель та же, но в среднем в первом тайме забивают ~45% голов матча
HT_SHARE = 0.45
HT_MARKETS = {
    "HT_H": ("1-й тайм", "П1 в 1-м тайме", lambda i, j: i > j),
    "HT_D": ("1-й тайм", "Ничья в 1-м тайме", lambda i, j: i == j),
    "HT_A": ("1-й тайм", "П2 в 1-м тайме", lambda i, j: i < j),
    "HT_O05": ("1-й тайм", "ТБ 0.5 в 1-м тайме", lambda i, j: i + j > 0.5),
    "HT_U05": ("1-й тайм", "ТМ 0.5 в 1-м тайме", lambda i, j: i + j < 0.5),
    "HT_O15": ("1-й тайм", "ТБ 1.5 в 1-м тайме", lambda i, j: i + j > 1.5),
    "HT_U15": ("1-й тайм", "ТМ 1.5 в 1-м тайме", lambda i, j: i + j < 1.5),
}


MAIN_POOL = ["H", "A", "1X", "X2", "12", "BTTS_Y", "BTTS_N", "O25", "U25", "O35", "U35",
             "H-1.5", "A-1.5", "H+1.5", "A+1.5", "H_O15", "A_O15", "H&O15", "A&O15"]


def handicap_key(side: str, h: float) -> str | None:
    """Азиатская фора с половинной линией → наш рынок (возврата не бывает).

    Ф1(−0.5) — это П1, Ф1(+0.5) — это 1X, Ф1(±1.5/2.5) — обычные форы. Целые и четвертные линии
    пропускаем: там бывает возврат ставки, а честно учесть его в статистике сложнее.
    """
    if h is None or abs(h * 2) % 2 != 1:
        return None
    if abs(h) == 0.5:
        return {("H", -1): "H", ("H", 1): "1X", ("A", -1): "A", ("A", 1): "X2"}[(side, 1 if h > 0 else -1)]
    k = f"{side}{h:+.1f}"
    return k if k in MARKETS else None


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
    ht = matrix(lh * HT_SHARE, la * HT_SHARE)
    out.update({k: _p(ht, cond) for k, (_, _, cond) in HT_MARKETS.items()})
    flat = sorted(((m[i, j], f"{i}:{j}") for i in range(6) for j in range(6)), reverse=True)
    out["scores"] = [(s, float(p)) for p, s in flat[:3]]
    return out


def won(key: str, hs: int, as_: int) -> bool:
    if key.startswith("CS_"):
        return key == f"CS_{hs}:{as_}"
    return bool(MARKETS[key][2](hs, as_))


SPORT_LABELS = {"TN_2S": "Будет 2 сета", "TN_3S": "Будет 3 сета", "TN_W1": "Победа первого", "TN_W2": "Победа второго",
                "HK_ML_H": "П1 (хоккей)", "HK_ML_A": "П2 (хоккей)", "BB_ML_H": "П1 (баскетбол)", "BB_ML_A": "П2 (баскетбол)",
                "ES_W1": "Победа первого (кибер)", "ES_W2": "Победа второго (кибер)", "ES_FULL": "Все карты", "ES_DRY": "Всухую"}


def label(key: str) -> str:
    if key.startswith("CS_"):
        return f"Точный счёт {key[3:]}"
    m = MARKETS.get(key) or HT_MARKETS.get(key)
    if m:
        return m[1]
    if key in SPORT_LABELS:
        return SPORT_LABELS[key]
    if key[:4] in ("TN_S", "ES_S") and ":" in key:
        return f"Счёт по {'сетам' if key[0] == 'T' else 'картам'} {key[4:]}"
    if key[:4] in ("HK_O", "HK_U", "BB_O", "BB_U"):
        return f"Т{'Б' if key[3] == 'O' else 'М'} {key[4:]}"
    if key.startswith("HK_IT"):
        return f"ИТ{key[5]} больше {key[7:]}"
    return key


def calibration(res, prior: float = 20.0) -> dict[str, tuple[float, int]]:
    """Учимся на своих прогнозах: во сколько раз каждый тип ставки заходит чаще/реже, чем обещал бот.

    res — таблица results.csv. Возвращает key → (поправка, сколько прогнозов). Пока прогнозов мало,
    поправка близка к 1 (`prior` воображаемых прогнозов «ровно как обещано»), с опытом — точнее.
    """
    out = {}
    if res is None or len(res) == 0 or "main_key" not in res:
        return out
    rows = []
    for kind in ("main", "bold"):
        if f"{kind}_key" in res:
            part = res[["date", f"{kind}_key", f"{kind}_p", f"{kind}_hit"]].dropna()
            part.columns = ["date", "key", "p", "hit"]
            rows.append(part)
    df = pd.concat(rows, ignore_index=True)
    df["hit"] = df["hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    recent = pd.to_datetime(df["date"]) > pd.to_datetime(df["date"]).max() - pd.Timedelta(days=WEAK_DAYS)
    for key, g in df.groupby("key"):
        pbar = g["p"].astype(float).mean()
        ratio = (g["hit"].sum() + prior * pbar) / (g["p"].astype(float).sum() + prior * pbar)
        out[key] = (float(min(max(ratio, 0.8), 1.2)), len(g))
        last = g[recent[g.index]]
        if len(last) >= WEAK_MIN_N and last["hit"].mean() < last["p"].astype(float).mean() - WEAK_GAP:
            out[key] = (0.0, len(g))  # рынок стабильно заходит реже обещанного — бот его временно не ставит
    return out


WEAK_MIN_N, WEAK_GAP, WEAK_DAYS = 20, 0.10, 30


def weak(calib: dict) -> list[str]:
    """Типы ставок, отключённые из-за плохой статистики."""
    return [k for k, (r, _) in (calib or {}).items() if r == 0.0]


FAV_P = 0.60
AGAINST = {"H": {"A", "D", "X2", "A+1.5", "A+2.5", "A-1.5", "A-2.5", "A&O15", "A&BTTS", "X2&U35"},
           "A": {"H", "D", "1X", "H+1.5", "H+2.5", "H-1.5", "H-2.5", "H&O15", "H&BTTS", "1X&U35"}}
MIN_ODDS = 1.5     # ниже этого кэфа профессионалы не играют: одна осечка съедает несколько выигрышей
MAIN_MIN_P = 0.45  # основной прогноз — всё-таки «скорее зайдёт», чем нет
BOLD_MIN_P = 0.40  # смелый — не лотерея: хотя бы 40%


def compatible(k1: str, k2: str) -> bool:
    """Могут ли обе ставки зайти в одном матче (есть хотя бы один счёт, при котором заходят обе)."""
    return any(won(k1, i, j) and won(k2, i, j) for i in range(8) for j in range(8))


def choose(keys: list[str], probs: dict, real: dict, score, main_pool: list[str] | None = None, fits=None):
    """Как выбирает профессиональный каппер.

    Основной: среди рынков с НАСТОЯЩИМ кэфом от 1.5 и вероятностью от 45% — самый выгодный
    (вероятность × кэф, т.е. ожидаемый возврат). Если настоящих кэфов нет — самый вероятный
    с честным кэфом от 1.5. Смелый: кэф 2.0–3.6, тоже по выгоде, предпочтительно с настоящим кэфом.
    """
    def odds(k):
        return real.get(k) or MARGIN / probs[k]

    def ev(k):
        return score(k) * odds(k)

    pool = main_pool or keys
    real_main = [k for k in keys if real.get(k) and real[k] >= MIN_ODDS and probs[k] >= MAIN_MIN_P]
    if real_main:
        main_k = max(real_main, key=lambda k: (round(ev(k), 3), score(k)))
    else:
        est = [k for k in pool if k in probs and MAIN_MIN_P <= probs[k] and odds(k) >= MIN_ODDS]
        main_k = max(est or [k for k in pool if k in probs], key=score)
    # смелый не должен спорить с основным: П1 основным и П2 смелым — это ставка против самого себя
    # смелый — только с настоящим кэфом букмекера и шансом от 40%: на «расчётных» кэфах он заходил в 31% случаев
    bold = [k for k in keys if k != main_k and real.get(k) and 2.0 <= real[k] <= 3.6 and probs[k] >= BOLD_MIN_P
            and (fits is None or fits(main_k, k))]
    bold_k = max(bold, key=ev) if bold else None
    return main_k, bold_k


def stake_text(t: dict) -> str:
    """«💰 Ставка: 1% банка · ставить при кэфе от 1.72» — минимальный кэф = точка безубыточности (1 / вероятность)."""
    s = t.get("stake", 1.0)
    line = f"💰 Ставка: <b>{s:g}% банка</b>"
    if s > 1.0:
        line += " · есть перевес над линией"
    if t.get("p"):
        fair_odds = 1 / t["p"]
        if not t.get("est") and t.get("odds") and t["odds"] < fair_odds:
            # средний кэф ниже справедливого (это маржа букмекера) — честно говорим, где ставка становится выгодной
            line += f" · выгодно с кэфа <b>{fair_odds:.2f}</b> — ищи у букмекеров повыше"
        else:
            line += f" · ставить при кэфе <b>от {fair_odds:.2f}</b>"
    return line


def tips(probs: dict, real_odds: dict, calib: dict | None = None) -> tuple[dict, dict]:
    """Основной прогноз (самый надёжный с нормальным кэфом) и смелый (кэф 2.0–3.6).

    calib — поправки из собственной статистики бота: типы ставок, которые у него заходят чаще
    обещанного, выбираются охотнее, а «подводящие» — реже.
    """
    calib = calib or {}

    def odds_for(k):
        o = real_odds.get(k)
        return (round(o, 2), False) if o else (round(MARGIN / probs[k], 2), True)

    def score(k):
        return probs[k] * calib.get(k, (1.0, 0))[0]

    keys = [k for k in MARKETS if probs[k] > 0 and score(k) > 0]  # score 0 — рынок отключён (см. calibration)
    # при явном фаворите (60%+) не ставим против него: «Ф1 (+1.5)» за аутсайдера выглядит странно и путает читателей
    fav = "H" if probs["H"] >= probs["A"] else "A"
    if probs[fav] >= FAV_P:
        keys = [k for k in keys if k not in AGAINST[fav]]
    main_k, bold_k = choose(keys, probs, real_odds, score, [k for k in MAIN_POOL if k in keys] or keys, compatible)

    def pack(k):
        if k is None:
            return {}
        o, est = odds_for(k)
        return {"key": k, "label": label(k), "p": round(probs[k], 4), "odds": o, "est": est}
    return pack(main_k), pack(bold_k)
