"""⚡ LIVE-прогноз «в моменте»: по ходу матча бот пересчитывает шансы и даёт одну ставку.

Как считаем: сила команд до матча (ожидаемые голы модели) × оставшееся время → сколько ещё забьют
(распределение Пуассона) + текущий счёт → шансы итогов матча. Берём рынок с шансом 55–75% и показываем
справедливый кэф и минимальный кэф, от которого ставка выгодна (запас 5%). Живых кэфов букмекеров
в бесплатном доступе нет — поэтому честно пишем «ставить, если у букмекера от X».

Один LIVE-прогноз на матч: футбол — с 25-й по 70-ю минуту, хоккей — во втором периоде.
Итог подводим сами по финальному счёту (хоккей — по основному времени) и пишем ответом в ветку матча.
Для сайта пишем docs/live_tips.json — трансляция показывает прогноз прямо во время просмотра.
"""
from __future__ import annotations

import csv
import json
import math
import re
from html import escape
from pathlib import Path

import pandas as pd

from . import card, telegram

ROOT = Path(__file__).resolve().parent.parent
TIPS = ROOT / "docs" / "live_tips.json"
LOG = ROOT / "data" / "live_bets.csv"
EDGE = 1.05            # минимальный кэф = справедливый × 1.05
P_RANGE = (0.55, 0.75)
TARGET_P = 0.62


def _pois(lam: float, n: int = 12) -> list[float]:
    lam = max(lam, 1e-9)
    return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(n)]


def _finals(h: int, a: int, lh: float, la: float) -> dict[tuple[int, int], float]:
    """Распределение итогового счёта: текущий + голы за оставшееся время."""
    ph, pa = _pois(lh), _pois(la)
    return {(h + i, a + j): ph[i] * pa[j] for i in range(len(ph)) for j in range(len(pa))}


def _markets(h: int, a: int, lh: float, la: float, sport: str) -> list[tuple[str, str, float]]:
    """(ключ, подпись, шанс) для рынков по итоговому счёту."""
    f = _finals(h, a, lh, la)
    p = lambda cond: sum(v for (x, y), v in f.items() if cond(x, y))  # noqa: E731
    n = h + a
    reg = " (осн. время)" if sport == "hockey" else ""
    out = [("H", f"П1{reg}", p(lambda x, y: x > y)), ("A", f"П2{reg}", p(lambda x, y: x < y)),
           ("1X", f"1X{reg}", p(lambda x, y: x >= y)), ("X2", f"X2{reg}", p(lambda x, y: x <= y))]
    for k in (0.5, 1.5, 2.5):
        line = n + k
        out.append((f"O{line}", f"ТБ {line:g}", p(lambda x, y, L=line: x + y > L)))
        out.append((f"U{line}", f"ТМ {line:g}", p(lambda x, y, L=line: x + y < L)))
    if sport == "football" and min(h, a) == 0:
        out.append(("BTTS", "Обе забьют — да", p(lambda x, y: x > 0 and y > 0)))
    return out


def hit(key: str, x: int, y: int) -> bool:
    """Зашёл ли рынок при итоговом счёте x:y."""
    if key == "H":
        return x > y
    if key == "A":
        return x < y
    if key == "1X":
        return x >= y
    if key == "X2":
        return x <= y
    if key == "BTTS":
        return x > 0 and y > 0
    if key[0] in "OU":
        line = float(key[1:])
        return x + y > line if key[0] == "O" else x + y < line
    return False


def _minute(e: dict) -> float | None:
    """Сколько прошло: футбол — минуты, хоккей — доля матча (0..1)."""
    if e.get("sport", "football") == "football":
        if "HT" in (e.get("detail") or "") or "Half" in (e.get("detail") or ""):
            return 45.0
        m = re.match(r"(\d+)", str(e.get("clock") or ""))
        return float(m.group(1)) if m else None
    per = len((e.get("home") or {}).get("periods") or [])
    m = re.search(r"(\d+):(\d+)", e.get("detail") or "")
    if not per or not m:
        return None
    left = int(m.group(1)) + int(m.group(2)) / 60
    return min(1.0, ((per - 1) * 20 + (20 - left)) / 60)


def _lams(match: dict) -> tuple[float, float] | None:
    """Ожидаемые голы команд до матча (за всю игру)."""
    if match.get("lam"):
        return float(match["lam"][0]), float(match["lam"][1])
    md = match.get("model") or {}
    if md.get("lh") and md.get("la"):
        return float(md["lh"]), float(md["la"])
    return None


def _score(e: dict) -> tuple[int, int] | None:
    try:
        return int(e["home"].get("score") or 0), int(e["away"].get("score") or 0)
    except (TypeError, ValueError):
        return None


def _regulation(e: dict) -> tuple[int, int] | None:
    """Хоккей: счёт основного времени (первые три периода) — по нему считаются ставки на исход и тотал."""
    hp, ap = (e["home"].get("periods") or [])[:3], (e["away"].get("periods") or [])[:3]
    if len(hp) < 3 or len(ap) < 3:
        return _score(e)
    return int(sum(float(x or 0) for x in hp)), int(sum(float(x or 0) for x in ap))


def pick(e: dict, match: dict) -> dict | None:
    """LIVE-прогноз для матча прямо сейчас (или None, если момент/данные не подходят)."""
    sport = e.get("sport", "football")
    if sport not in ("football", "hockey") or e.get("state") != "in":
        return None
    t, lams, sc = _minute(e), _lams(match), _score(e)
    if t is None or lams is None or sc is None:
        return None
    if sport == "football":
        if not 25 <= t <= 70:
            return None
        left, minute = max(0.0, (90 - t) / 90), f"{int(t)}'"
    else:
        if not 1 / 3 <= t <= 2 / 3:
            return None
        left, minute = 1 - t, "2-й период"
    lh, la = lams[0] * left, lams[1] * left
    cands = [(k, lb, p) for k, lb, p in _markets(sc[0], sc[1], lh, la, sport) if P_RANGE[0] <= p <= P_RANGE[1]]
    if not cands:
        return None
    k, lb, p = min(cands, key=lambda c: abs(c[2] - TARGET_P))
    return {"key": k, "label": lb, "p": round(p, 3), "fair": round(1 / p, 2), "min_odds": round(EDGE / p, 2),
            "minute": minute, "score": f"{sc[0]}:{sc[1]}", "sport": sport}


def _tally() -> tuple[int, int]:
    if not LOG.exists():
        return 0, 0
    rows = list(csv.DictReader(LOG.open(encoding="utf-8")))
    return sum(r["hit"] == "True" for r in rows), len(rows)


def _site(store: dict, events: list[dict]) -> None:
    """docs/live_tips.json: LIVE-прогнозы идущих и недавних матчей — для страницы трансляции."""
    out = {}
    for e in events:
        st = store.get(f"{e['div']}|{e['id']}") or {}
        if st.get("lt"):
            out[str(e["id"])] = {k: st["lt"].get(k) for k in ("label", "p", "fair", "min_odds", "minute", "score", "result")}
    try:
        old = TIPS.read_text(encoding="utf-8") if TIPS.exists() else ""
        new = json.dumps(out, ensure_ascii=False, sort_keys=True)
        if new != old:
            TIPS.write_text(new, encoding="utf-8", newline="\n")
    except OSError:
        pass


def run(store: dict, events: list[dict], matches: dict, brand: str) -> None:
    """store — data/live.json (ветка матча в Telegram: st['msg']); matches — прогнозы бота по ключу «div|id»."""
    from . import live
    for e in events:
        key = f"{e['div']}|{e['id']}"
        st, m = store.get(key), matches.get(key)
        if not st or not m or not st.get("msg"):
            continue
        h, a = e["home"].get("ru", ""), e["away"].get("ru", "")
        lt = st.get("lt")
        if lt is None and not st.get("lt_none"):
            tip = pick(e, m)
            if not tip:
                continue
            try:
                png = card.live_card(live._league(e), e["home"], e["away"], *_score(e), "LIVE-ПРОГНОЗ",
                                     f"{tip['label']} · шанс {100 * tip['p']:.0f}% · кэф от {tip['min_odds']:.2f}", brand,
                                     tip["sport"], color=(124, 58, 237))
                text = (f"⚡ <b>LIVE-ПРОГНОЗ · {tip['minute']}</b>\n{escape(h)} <b>{tip['score']}</b> {escape(a)}\n\n"
                        f"🎯 <b>{escape(tip['label'])}</b> — шанс {100 * tip['p']:.0f}%\n"
                        f"💰 Справедливый кэф ≈{tip['fair']:.2f} · ставить, если у букмекера <b>от {tip['min_odds']:.2f}</b>\n"
                        f"🧠 Расчёт в моменте: сила команд до матча, текущий счёт и оставшееся время")
                telegram.send_photo(png, text, reply_to=st["msg"])
                st["lt"] = tip
                print(f"  live-прогноз: {h} — {a}: {tip['label']} ({100 * tip['p']:.0f}%)")
            except Exception as ex:
                print(f"  ! live-прогноз не отправлен: {ex}")
        elif lt and not lt.get("result") and e.get("state") == "post":
            fin = _regulation(e) if lt.get("sport") == "hockey" else _score(e)
            if not fin:
                continue
            ok = hit(lt["key"], *fin)
            lt["result"] = "hit" if ok else "miss"
            new_file = not LOG.exists()
            with LOG.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["date", "match", "label", "p", "fair", "min_odds", "minute", "final", "hit"])
                w.writerow([pd.Timestamp.now(tz="Europe/Moscow").strftime("%Y-%m-%d"), f"{h} — {a}", lt["label"],
                            lt["p"], lt["fair"], lt["min_odds"], lt["minute"], f"{fin[0]}:{fin[1]}", ok])
            wins, total = _tally()
            try:
                telegram.send(f"{'✅' if ok else '❌'} <b>LIVE-прогноз {'зашёл' if ok else 'не зашёл'}</b>: "
                              f"{escape(lt['label'])} · итог {fin[0]}:{fin[1]}\n📊 LIVE-прогнозы бота: {wins} из {total}",
                              reply_to=st["msg"], silent=True)
            except Exception as ex:
                print(f"  ! итог live-прогноза не отправлен: {ex}")
    _site(store, events)
