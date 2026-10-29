"""Хоккей, баскетбол и теннис: данные ESPN, вероятности всех рынков, тексты постов и расчёт итогов.

  • хоккей — модель голов (Пуассон), подогнанная под коэффициенты: победа с ОТ, исход основного
    времени, тоталы, форы;
  • баскетбол — нормальное распределение разницы и тотала очков вокруг линий букмекера;
  • теннис — коэффициентов на ESPN нет, поэтому свой рейтинг Эло по истории матчей ATP/WTA за год;
    из него — победа, счёт по сетам, «будет ли третий сет».
"""
import json
from concurrent.futures import ThreadPoolExecutor
from html import escape
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

from . import esports
from . import markets as mk
from . import names
from .espn import MSK, _get, decimal
from .reviews import ROUNDS

SB = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={day}"
TENNIS_CACHE = Path(__file__).resolve().parent.parent / "data" / "raw" / "tennis"

# code: (флаг, страна, турнир, путь ESPN, вид спорта)
LEAGUES = {
    "NHL": ("🇺🇸", "США", "NHL", "hockey/nhl", "hockey"),
    "NBA": ("🇺🇸", "США", "NBA", "basketball/nba", "basketball"),
    "WNBA": ("🇺🇸", "США", "WNBA", "basketball/wnba", "basketball"),
    "ATP": ("🎾", "Теннис", "ATP", "tennis/atp", "tennis"),
    "WTA": ("🎾", "Теннис", "WTA", "tennis/wta", "tennis"),
    "CS2": ("🎮", "Киберспорт", "CS2", "", "esports"),      # данные — PandaScore, см. esports.py
    "DOTA": ("🎮", "Киберспорт", "Dota 2", "", "esports"),
}
EMOJI = {"hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "football": "⚽️", "esports": "🎮"}
SPORT_RU = {"hockey": "Хоккей", "basketball": "Баскетбол", "tennis": "Теннис", "football": "Футбол",
            "esports": "Киберспорт"}
SLAMS = ("Australian Open", "Roland Garros", "French Open", "Wimbledon", "US Open")
SIGMA = {"NBA": (12.0, 17.0), "WNBA": (11.0, 15.0)}  # разброс разницы и тотала очков


def title(code: str) -> str:
    flag, country, league, _, _ = LEAGUES[code]
    return f"{flag} {country} · {league}"


def league_plain(code: str) -> str:
    _, country, league, _, _ = LEAGUES[code]
    return f"{country} · {league}"


# ── загрузка ────────────────────────────────────────────────────────────────

def _close(block: dict, side: str, field: str = "odds"):
    return ((block.get(side) or {}).get("close") or {}).get(field)


def _team_odds(comp: dict) -> dict:
    for o in comp.get("odds") or []:
        if not isinstance(o, dict):
            continue
        ml, ps, tot = o.get("moneyline") or {}, o.get("pointSpread") or {}, o.get("total") or {}
        out = {
            "H": decimal((o.get("homeTeamOdds") or {}).get("moneyLine") or _close(ml, "home")),
            "A": decimal((o.get("awayTeamOdds") or {}).get("moneyLine") or _close(ml, "away")),
            "line": o.get("overUnder"),
            "over": decimal(_close(tot, "over")),
            "under": decimal(_close(tot, "under")),
            "spread": None, "sp_h": decimal(_close(ps, "home")), "sp_a": decimal(_close(ps, "away")),
        }
        try:
            out["spread"] = float(_close(ps, "home", "line"))
        except (TypeError, ValueError):
            if o.get("spread") is not None:
                out["spread"] = float(o["spread"])
        if out["H"] and out["A"]:
            return out
    return {}


def _team(t: dict) -> dict:
    team = t["team"]
    recs = t.get("records") or []
    return {"id": team.get("id"), "name": team.get("displayName"), "logo": team.get("logo"),
            "color": team.get("color") or "3b4a7a", "score": t.get("score"),
            "record": recs[0].get("summary") if recs else "",
            "periods": [x.get("value") for x in t.get("linescores") or []]}


def _team_events(code: str, day: str) -> list[dict]:
    path = LEAGUES[code][3]
    data = _get(SB.format(path=path, day=day)) or {}
    out = []
    for e in data.get("events", []):
        comp = e["competitions"][0]
        teams = {t["homeAway"]: t for t in comp.get("competitors", [])}
        if "home" not in teams or "away" not in teams:
            continue
        st = e["status"]["type"]
        out.append({"id": e["id"], "div": code, "sport": LEAGUES[code][4],
                    "kickoff": pd.Timestamp(e["date"]).tz_convert(MSK).isoformat(),
                    "state": st.get("state"), "completed": bool(st.get("completed")), "status": st.get("name", ""),
                    "home": _team(teams["home"]), "away": _team(teams["away"]), "odds": _team_odds(comp)})
    return out


def _tennis_matches(code: str, data: dict, only_singles: bool = True) -> list[dict]:
    out = []
    for e in data.get("events", []):
        tour_name = e.get("name", "")
        for g in e.get("groupings", []):
            gname = (g.get("grouping") or {}).get("displayName", "")
            if only_singles and ("Singles" not in gname or "Qualif" in gname):
                continue
            for c in g.get("competitions", []):
                comps = c.get("competitors", [])
                if len(comps) != 2 or not all(x.get("athlete") for x in comps):
                    continue
                rnd = (c.get("round") or {}).get("displayName", "")
                if only_singles and "Qualif" in rnd:  # квалификацию не берём — только основная сетка
                    continue
                st = c["status"]["type"]
                p = sorted(comps, key=lambda x: x.get("order", 0))
                players = [{"id": str(x.get("id")), "name": x["athlete"].get("displayName", ""),
                            "logo": [f"https://a.espncdn.com/i/headshots/tennis/players/full/{x.get('id')}.png",
                                     (x["athlete"].get("flag") or {}).get("href")],
                            "country": (x["athlete"].get("flag") or {}).get("alt", ""), "color": "2d6a4f",
                            "winner": bool(x.get("winner")),
                            "sets": [s.get("value") for s in x.get("linescores") or []],
                            "set_won": [bool(s.get("winner")) for s in x.get("linescores") or []]} for x in p]
                out.append({"id": str(c["id"]), "div": code, "sport": "tennis", "tournament": tour_name, "round": rnd,
                            "bo5": code == "ATP" and any(s in tour_name for s in SLAMS),
                            "kickoff": pd.Timestamp(c.get("date") or e["date"]).tz_convert(MSK).isoformat(),
                            "state": st.get("state"), "completed": bool(st.get("completed")),
                            "status": st.get("name", ""), "detail": st.get("detail", ""),
                            "home": players[0], "away": players[1]})
    return out


def fetch(now: pd.Timestamp) -> list[dict]:
    """Все матчи хоккея, баскетбола и тенниса за вчера/сегодня/завтра."""
    utc = now.tz_convert("UTC")
    days = [(utc + pd.Timedelta(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
    jobs = [(c, d) for c in LEAGUES for d in days if LEAGUES[c][4] != "esports"]

    def one(job):
        code, day = job
        if LEAGUES[code][4] == "tennis":
            return _tennis_matches(code, _get(SB.format(path=LEAGUES[code][3], day=day)) or {})
        return _team_events(code, day)

    with ThreadPoolExecutor(12) as ex:
        events = [e for part in ex.map(one, jobs) for e in part]
    try:
        events += esports.fetch()
    except Exception as ex:
        print(f"  ! киберспорт недоступен: {ex}")
    events = list({(e["div"], e["id"]): e for e in events}.values())
    return [e for e in events if "POSTPONED" not in e["status"] and "CANCEL" not in e["status"]]


# ── теннис: рейтинг Эло по истории ESPN ─────────────────────────────────────

def tennis_history(refresh: bool) -> list[dict]:
    """Завершённые одиночные матчи ATP/WTA за ~год (кэш по неделям, свежие недели обновляются)."""
    TENNIS_CACHE.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now(tz=MSK).normalize().tz_localize(None)
    jobs = []
    for code in ("ATP", "WTA"):
        for w in range(0, 53):
            day = (today - pd.Timedelta(weeks=w)).strftime("%Y%m%d")
            jobs.append((code, day, w <= 1))

    def one(job):
        code, day, fresh = job
        path = TENNIS_CACHE / f"{code}_{day}.json"
        if path.exists() and not (fresh and refresh):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data = _get(SB.format(path=LEAGUES[code][3], day=day))
        if data is None:
            return []
        ms = [m for m in _tennis_matches(code, data) if m["completed"]]
        path.write_text(json.dumps(ms, ensure_ascii=False), encoding="utf-8")
        return ms

    with ThreadPoolExecutor(8) as ex:
        matches = [m for part in ex.map(one, jobs) for m in part]
    return sorted({m["id"]: m for m in matches}.values(), key=lambda m: m["kickoff"])


def elo(history: list[dict]) -> dict[str, tuple[float, int]]:
    """Рейтинг Эло (с K, убывающим по опыту игрока, как у FiveThirtyEight). id → (рейтинг, матчей)."""
    r: dict[str, float] = {}
    n: dict[str, int] = {}
    for m in history:
        a, b = m["home"], m["away"]
        if a["winner"] == b["winner"]:
            continue
        w, l = (a, b) if a["winner"] else (b, a)
        rw, rl = r.get(w["id"], 1500.0), r.get(l["id"], 1500.0)
        exp = 1 / (1 + 10 ** ((rl - rw) / 400))
        kw = 250 / (n.get(w["id"], 0) + 5) ** 0.4
        kl = 250 / (n.get(l["id"], 0) + 5) ** 0.4
        r[w["id"]], r[l["id"]] = rw + kw * (1 - exp), rl - kl * (1 - exp)
        n[w["id"]], n[l["id"]] = n.get(w["id"], 0) + 1, n.get(l["id"], 0) + 1
    return {k: (r[k], n[k]) for k in r}


# ── вероятности и рынки ─────────────────────────────────────────────────────

def _hockey_lambdas(p_home: float, line: float | None, p_over: float | None) -> tuple[float, float]:
    def loss(v):
        lh, la = np.exp(v)
        m = mk.matrix(lh, la, rho=0.0)
        ml = np.tril(m, -1).sum() + 0.52 * np.trace(m)  # ничья в основное время → ОТ/буллиты почти 50/50
        err = (ml - p_home) ** 2
        if line is not None and p_over is not None:
            err += (mk._p(m, lambda i, j: i + j > line) - p_over) ** 2
        else:
            err += 0.001 * (lh + la - 6.0) ** 2
        return err
    res = minimize(loss, np.log([3.1, 2.8]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10})
    return tuple(float(x) for x in np.exp(res.x))


def _p2(o: dict, a: str, b: str) -> float | None:
    if o.get(a) and o.get(b):
        return float(mk.fair([o[a], o[b]])[0])
    return None


def series(p: float, bo: int) -> dict[str, float]:
    """Вероятности счёта серии (сеты в теннисе, карты в киберспорте) при вероятности выиграть серию p."""
    if bo <= 1:
        return {"1:0": p, "0:1": 1 - p}
    if bo == 2:  # в серии из двух карт победителя может не быть, поэтому p — это шанс выиграть карту
        return {"2:0": p * p, "1:1": 2 * p * (1 - p), "0:2": (1 - p) ** 2}
    need = bo // 2 + 1

    def win(s):
        return sum(comb(need - 1 + k, k) * s ** need * (1 - s) ** k for k in range(need))
    lo, hi = 0.01, 0.99
    for _ in range(60):  # вероятность выиграть один сет/карту, дающая такую вероятность серии
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if win(mid) < p else (lo, mid)
    s = (lo + hi) / 2
    out = {}
    for k in range(need):
        out[f"{need}:{k}"] = comb(need - 1 + k, k) * s ** need * (1 - s) ** k
        out[f"{k}:{need}"] = comb(need - 1 + k, k) * (1 - s) ** need * s ** k
    return out


def _elo_or_market(e: dict, ratings: dict | None, o: dict):
    """Вероятность победы первого: по линии букмекера (если есть), иначе по рейтингу Эло бота.

    Возвращает (p, рейтинг1, рейтинг2, источник) или (None, …), если нет ни линии, ни истории.
    """
    ra, rb = (ratings or {}).get(e["home"]["id"]), (ratings or {}).get(e["away"]["id"])
    elo_ok = ra and rb and ra[1] >= 5 and rb[1] >= 5
    if o.get("H") and o.get("A"):
        return float(mk.fair([o["H"], o["A"]])[0]), ra if elo_ok else None, rb if elo_ok else None, o.get("src", "букмекера")
    if elo_ok:
        return 1 / (1 + 10 ** ((rb[0] - ra[0]) / 400)), ra, rb, "Эло"
    return None, None, None, None


def analyse(e: dict, ratings: dict | None = None) -> dict | None:
    """Вероятности всех рынков матча. Возвращает {probs, labels, real, center, model} или None."""
    o = e.get("odds") or {}
    sport = e["sport"]
    labels, probs, real = {}, {}, {}
    h, a = e["home"]["ru"], e["away"]["ru"]
    if sport == "hockey":
        p_home = _p2(o, "H", "A")
        if p_home is None:
            return None
        line = float(o["line"]) if o.get("line") else None
        lh, la = _hockey_lambdas(p_home, line, _p2(o, "over", "under"))
        m = mk.matrix(lh, la, rho=0.0)
        P = lambda cond: mk._p(m, cond)  # noqa: E731
        d = float(np.trace(m))
        probs.update({"HK_ML_H": float(np.tril(m, -1).sum()) + 0.52 * d, "HK_ML_A": float(np.triu(m, 1).sum()) + 0.48 * d,
                      "HK_H": float(np.tril(m, -1).sum()), "HK_D": d, "HK_A": float(np.triu(m, 1).sum())})
        labels.update({"HK_ML_H": "П1 (с ОТ и буллитами)", "HK_ML_A": "П2 (с ОТ и буллитами)",
                       "HK_H": "П1 в основное время", "HK_D": "Ничья в основное время", "HK_A": "П2 в основное время"})
        real.update({"HK_ML_H": o["H"], "HK_ML_A": o["A"]})
        base = line or 5.5
        for L in (base - 1, base, base + 1):
            probs[f"HK_O{L}"], probs[f"HK_U{L}"] = P(lambda i, j, L=L: i + j > L), P(lambda i, j, L=L: i + j < L)
            labels[f"HK_O{L}"], labels[f"HK_U{L}"] = f"ТБ {L}", f"ТМ {L}"
        if line and o.get("over") and o.get("under"):
            real.update({f"HK_O{line}": o["over"], f"HK_U{line}": o["under"]})
        for k, lab, cond in (("HK_H-1.5", "Ф1 (−1.5)", lambda i, j: i - j >= 2), ("HK_A+1.5", "Ф2 (+1.5)", lambda i, j: j - i >= -1),
                             ("HK_A-1.5", "Ф2 (−1.5)", lambda i, j: j - i >= 2), ("HK_H+1.5", "Ф1 (+1.5)", lambda i, j: i - j >= -1)):
            probs[k], labels[k] = P(cond), lab
        center = f"Ожидаемые голы {lh:.1f} : {la:.1f}"
        return {"probs": probs, "labels": labels, "real": real, "center": center, "bar": (probs["HK_ML_H"], 0, probs["HK_ML_A"]),
                "model": {"lh": lh, "la": la}}

    if sport == "basketball":
        sm, st = SIGMA.get(e["div"], (12.0, 17.0))
        if o.get("spread") is not None:
            mu = -float(o["spread"])
        elif _p2(o, "H", "A") is not None:
            mu = sm * norm.ppf(_p2(o, "H", "A"))
        else:
            return None
        p_home = float(norm.cdf(mu / sm))
        probs.update({"BB_ML_H": p_home, "BB_ML_A": 1 - p_home})
        labels.update({"BB_ML_H": "П1 (с ОТ)", "BB_ML_A": "П2 (с ОТ)"})
        if o.get("H") and o.get("A"):
            real.update({"BB_ML_H": o["H"], "BB_ML_A": o["A"]})
        if o.get("spread") is not None:
            sp = float(o["spread"])
            probs["BB_SPR_H"] = float(norm.cdf((mu + sp) / sm))
            probs["BB_SPR_A"] = 1 - probs["BB_SPR_H"]
            labels["BB_SPR_H"], labels["BB_SPR_A"] = f"Ф1 ({sp:+.1f})", f"Ф2 ({-sp:+.1f})"
            if o.get("sp_h") and o.get("sp_a"):
                real.update({"BB_SPR_H": o["sp_h"], "BB_SPR_A": o["sp_a"]})
        T = float(o["line"]) if o.get("line") else None
        if T:
            for L in (T - 7, T, T + 7):
                probs[f"BB_O{L}"] = float(1 - norm.cdf((L - T) / st))
                probs[f"BB_U{L}"] = 1 - probs[f"BB_O{L}"]
                labels[f"BB_O{L}"], labels[f"BB_U{L}"] = f"ТБ {L:g}", f"ТМ {L:g}"
            if o.get("over") and o.get("under"):
                real.update({f"BB_O{T}": o["over"], f"BB_U{T}": o["under"]})
        center = (f"Ожидаемый счёт {(T + mu) / 2:.0f} : {(T - mu) / 2:.0f}" if T else f"Разница ≈ {mu:+.1f}")
        return {"probs": probs, "labels": labels, "real": real, "center": center, "bar": (p_home, 0, 1 - p_home),
                "model": {"mu": mu, "T": T}}

    if sport == "tennis":
        p, ra, rb, src = _elo_or_market(e, ratings, o)
        if p is None:
            return None
        sets = series(p, 5 if e.get("bo5") else 3)
        probs.update({"TN_W1": p, "TN_W2": 1 - p})
        if o.get("H") and o.get("A"):
            real.update({"TN_W1": o["H"], "TN_W2": o["A"]})
        labels.update({"TN_W1": f"Победа: {h}", "TN_W2": f"Победа: {a}"})
        if not e.get("bo5"):
            probs["TN_3S"], labels["TN_3S"] = sets["2:1"] + sets["1:2"], "Будет 3 сета"
            probs["TN_2S"], labels["TN_2S"] = sets["2:0"] + sets["0:2"], "Будет 2 сета"
        else:
            probs["TN_4P"], labels["TN_4P"] = 1 - sets["3:0"] - sets["0:3"], "Будет 4+ сета"
        for sc, pr in sets.items():
            probs[f"TN_S{sc}"], labels[f"TN_S{sc}"] = pr, f"Счёт по сетам {sc}"
        elo = f"Эло {ra[0]:.0f} : {rb[0]:.0f}" if ra and rb else ""
        center = (f"Линия {src}" + (f" · {elo}" if elo else "")) if src != "Эло" else f"Рейтинг {elo}"
        return {"probs": probs, "labels": labels, "real": real, "center": center, "bar": (p, 0, 1 - p),
                "model": {"elo": [ra[0], rb[0]] if ra and rb else None, "src": src}}

    if sport == "esports":
        bo = int(e.get("bo") or 1)
        # в серии из двух карт возможна ничья — там линия «на победу» не подходит, считаем по рейтингу
        p, ra, rb, src = _elo_or_market(e, ratings, o if bo != 2 else {})
        if p is None:
            return None
        sc = series(p, bo)
        if bo == 2:  # серия из двух карт может закончиться 1:1
            probs.update({"ES_W1": sc["2:0"], "ES_X": sc["1:1"], "ES_W2": sc["0:2"]})
            labels.update({"ES_W1": f"Победа {h} 2:0", "ES_X": "Ничья 1:1", "ES_W2": f"Победа {a} 2:0"})
            bar = (sc["2:0"], sc["1:1"], sc["0:2"])
        else:
            probs.update({"ES_W1": p, "ES_W2": 1 - p})
            labels.update({"ES_W1": f"Победа: {h}", "ES_W2": f"Победа: {a}"})
            if o.get("H") and o.get("A"):
                real.update({"ES_W1": o["H"], "ES_W2": o["A"]})
            bar = (p, 0, 1 - p)
        if bo >= 3:
            need = bo // 2 + 1
            dry = sc[f"{need}:0"] + sc[f"0:{need}"]
            probs["ES_FULL"], labels["ES_FULL"] = 1 - dry, f"Больше {need} карт"
            probs["ES_DRY"], labels["ES_DRY"] = dry, f"Всухую ({need}:0 или 0:{need})"
            for k, v in sc.items():
                probs[f"ES_S{k}"], labels[f"ES_S{k}"] = v, f"Счёт по картам {k}"
        elo = f"Эло {ra[0]:.0f} : {rb[0]:.0f}" if ra and rb else ""
        center = f"BO{bo} · " + ((f"линия {src}" + (f" · {elo}" if elo else "")) if src != "Эло" else elo)
        return {"probs": probs, "labels": labels, "real": real, "center": center,
                "bar": bar, "model": {"elo": [ra[0], rb[0]] if ra and rb else None, "src": src}}
    return None


def pick(a: dict, calib: dict) -> tuple[dict, dict]:
    """Основной (самый вероятный, до 75%) и смелый (кэф 2.0–3.6) прогнозы с учётом статистики бота."""
    probs, labels, real = a["probs"], a["labels"], a["real"]

    def odds_for(k):
        return (round(real[k], 2), False) if real.get(k) else (round(mk.MARGIN / probs[k], 2), True)

    def score(k):
        return probs[k] * calib.get(k, (1.0, 0))[0]

    keys = [k for k in probs if 0 < probs[k] < 1 and not k.startswith(("TN_S", "ES_S"))]
    pool = [k for k in keys if probs[k] <= 0.75] or keys
    main_k = max(pool, key=score)
    bold = [k for k in probs if k != main_k and 2.0 <= odds_for(k)[0] <= 3.6]
    bold_k = max(bold, key=score) if bold else None

    def pack(k):
        if not k:
            return {}
        o, est = odds_for(k)
        return {"key": k, "label": labels[k], "p": round(probs[k], 4), "odds": o, "est": est}
    return pack(main_k), pack(bold_k)


def final(e: dict) -> dict | None:
    """Итоговый счёт: для тенниса — по сетам, для хоккея ещё и основное время."""
    status = str(e.get("status", "")).upper()
    if any(w in status for w in ("WALKOVER", "RETIRED", "FORFEIT", "ABANDON", "DEFAULT")):
        return {"void": True, "reason": {"WALKOVER": "соперник снялся до матча", "RETIRED": "отказ по ходу матча",
                                         "FORFEIT": "техническое поражение"}.get(
            next((w for w in ("WALKOVER", "RETIRED", "FORFEIT") if w in status), ""), "матч не доигран")}
    try:
        if e["sport"] == "esports":  # счёт по картам
            hs, as_ = int(e["home"]["score"] or 0), int(e["away"]["score"] or 0)
            return {"hs": hs, "as": as_, "home_won": hs > as_, "away_won": as_ > hs, "sets": f"{hs}:{as_}"}
        if e["sport"] == "tennis":
            s1, s2 = sum(e["home"]["set_won"]), sum(e["away"]["set_won"])
            if s1 + s2 == 0:  # ни одного сета — матча фактически не было
                return {"void": True, "reason": "матч не состоялся"}
            return {"hs": s1, "as": s2, "home_won": e["home"]["winner"], "sets": f"{s1}:{s2}",
                    "games": " ".join(f"{int(x)}-{int(y)}" for x, y in zip(e["home"]["sets"], e["away"]["sets"]) if x is not None)}
        hs, as_ = int(e["home"]["score"]), int(e["away"]["score"])
        out = {"hs": hs, "as": as_, "home_won": hs > as_,
               "periods": [(int(x or 0), int(y or 0)) for x, y in zip(e["home"]["periods"], e["away"]["periods"])],
               "spread_h": (e.get("odds") or {}).get("spread")}
        if e["sport"] == "hockey":
            hp, ap = e["home"]["periods"][:3], e["away"]["periods"][:3]
            out["reg"] = (int(sum(x or 0 for x in hp)), int(sum(x or 0 for x in ap)))
        return out
    except (TypeError, ValueError, KeyError):
        return None


def won(key: str, f: dict) -> bool:
    hs, as_ = f["hs"], f["as"]
    if key in ("HK_ML_H", "BB_ML_H", "TN_W1"):
        return f["home_won"]
    if key in ("HK_ML_A", "BB_ML_A", "TN_W2"):
        return not f["home_won"]
    if key in ("HK_H", "HK_D", "HK_A"):
        rh, ra = f["reg"]
        return {"HK_H": rh > ra, "HK_D": rh == ra, "HK_A": rh < ra}[key]
    if key.startswith(("HK_O", "BB_O")):
        return hs + as_ > float(key[4:])
    if key.startswith(("HK_U", "BB_U")):
        return hs + as_ < float(key[4:])
    if key.startswith("HK_") and key[3] in "HA":
        side, line = key[3], float(key[4:])
        diff = (hs - as_) if side == "H" else (as_ - hs)
        return diff + line > 0
    if key == "BB_SPR_H":
        return f.get("spread_h") is not None and hs - as_ + f["spread_h"] > 0
    if key == "BB_SPR_A":
        return f.get("spread_h") is not None and hs - as_ + f["spread_h"] < 0
    if key.startswith("ES_"):
        if key == "ES_W1":
            return f["home_won"]
        if key == "ES_W2":
            return f["away_won"]
        if key == "ES_X":
            return hs == as_
        if key == "ES_FULL":
            return min(hs, as_) > 0
        if key == "ES_DRY":
            return min(hs, as_) == 0
        return f["sets"] == key[4:]
    if key == "TN_3S":
        return hs + as_ == 3
    if key == "TN_2S":
        return hs + as_ == 2
    if key == "TN_4P":
        return hs + as_ >= 4
    if key.startswith("TN_S"):
        return f["sets"] == key[4:]
    return False


# ── тексты ──────────────────────────────────────────────────────────────────

def _pct(p: float) -> str:
    return f"{100 * p:.0f}%"


def _tip(t: dict) -> str:
    return f"{escape(t['label'])} — {_pct(t['p'])} · кэф {'≈' if t.get('est') else ''}{t['odds']:.2f}"


def caption(m: dict, when: str) -> str:
    """Пост перед игрой (хоккей/баскетбол) — помещается в подпись к картинке."""
    h, a = escape(m["home"]["ru"]), escape(m["away"]["ru"])
    lines = (["⭐ <b>ПРОГНОЗ ДНЯ</b>"] if m.get("top") else []) + [
        f"{EMOJI[m['sport']]} <b>{h} — {a}</b>", f"🏆 {title(m['div'])}", f"⏰ {when}"]
    if m.get("tournament"):
        rnd = ROUNDS.get(m.get("round", ""), m.get("round", ""))
        lines.append(f"🎟 {escape(m['tournament'])}" + (f" · {escape(rnd)}" if rnd else ""))
    if m["home"].get("record") or m["away"].get("record"):
        lines.append(f"📋 Баланс: {h} {m['home'].get('record') or '—'} · {a} {m['away'].get('record') or '—'}")
    s_ = m["main"].get("stake", 1.0)
    lines += ["", f"🎯 <b>Основной прогноз:</b> {_tip(m['main'])}",
              f"💰 Ставка: <b>{s_:g}% банка</b>" + (" · есть перевес над линией" if s_ > 1.0 else "")]
    if m.get("bold"):
        lines.append(f"🔥 <b>Смелый прогноз:</b> {_tip(m['bold'])}")
    lines += ["", "👇 <i>Полный разбор — в ответе к посту</i>"]
    return "\n".join(lines)


def result_caption(m: dict, f: dict, day: dict) -> str:
    h, a = escape(m["home"]["ru"]), escape(m["away"]["ru"])
    lines = [f"🏁 <b>ФИНАЛ: {h} {f['hs']}:{f['as']} {a}</b>"]
    if m["sport"] == "hockey" and f.get("reg") and sum(f["reg"]) != f["hs"] + f["as"]:
        lines.append(f"Основное время {f['reg'][0]}:{f['reg'][1]}, дальше — овертайм/буллиты")
    per = " · ".join(f"{x}:{y}" for x, y in f.get("periods") or [])
    if f.get("games"):
        lines.append(f"📊 По геймам: {f['games']}")
    if per:
        lines.append(f"📊 По {'периодам' if m['sport'] == 'hockey' else 'четвертям'}: {per}")
    lines.append("")
    lines.append(f"🎯 Основной: {escape(m['main']['label'])} — {'✅ <b>ЗАШЁЛ</b>' if m['main_hit'] else '❌ мимо'}")
    if m.get("bold"):
        lines.append(f"🔥 Смелый: {escape(m['bold']['label'])} — {'✅ <b>ЗАШЁЛ</b>' if m['bold_hit'] else '❌ мимо'}")
    if day.get("n"):
        lines.append(f"\n📅 Сегодня ({SPORT_RU[m['sport']].lower()}): {day['main']}/{day['n']} ({_pct(day['main'] / day['n'])})")
    return "\n".join(lines)


def schedule_block(events: list[dict], start: pd.Timestamp) -> str:
    """Строки для утреннего расписания: хоккей и баскетбол поштучно, теннис — по турнирам."""
    end = start + pd.Timedelta(days=1)
    day = [e for e in events if e["state"] == "pre" and start <= pd.Timestamp(e["kickoff"]) < end]
    blocks = []
    for code in LEAGUES:
        g = sorted((e for e in day if e["div"] == code), key=lambda e: e["kickoff"])
        if not g:
            continue
        if LEAGUES[code][4] == "tennis":
            tours = sorted({e["tournament"] for e in g})
            blocks.append(f"<b>🎾 Теннис · {code}</b>: {len(g)} матч(ей) — {escape(', '.join(tours))}")
        elif LEAGUES[code][4] == "esports":
            lines = [f"<b>🎮 {title(code)}</b>"]
            for e in g[:12]:
                lines.append(f"🕒 {pd.Timestamp(e['kickoff']):%H:%M}  {escape(e['home']['ru'])} — "
                             f"{escape(e['away']['ru'])} · BO{e.get('bo', 1)}")
            if len(g) > 12:
                lines.append(f"…и ещё {len(g) - 12}")
            blocks.append("\n".join(lines))
        else:
            lines = [f"<b>{EMOJI[LEAGUES[code][4]]} {title(code)}</b>"]
            for e in g:
                lines.append(f"🕒 {pd.Timestamp(e['kickoff']):%H:%M}  {escape(e['home'].get('ru', e['home']['name']))} — "
                             f"{escape(e['away'].get('ru', e['away']['name']))}")
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def ru_names(events: list[dict], now: pd.Timestamp) -> None:
    for e in sorted(events, key=lambda e: abs(pd.Timestamp(e["kickoff"]) - now)):
        if abs(pd.Timestamp(e["kickoff"]) - now) > pd.Timedelta(hours=30):
            continue
        for side in ("home", "away"):
            t = e[side]
            if e["sport"] == "esports":
                t["ru"] = t["name"]  # киберкоманды принято писать как есть: NAVI, Team Spirit…
            elif e["sport"] == "tennis":
                t["ru"] = names.player(t["name"])
            else:
                t["ru"] = names.team(t["name"])
