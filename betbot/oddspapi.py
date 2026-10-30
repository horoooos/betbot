"""Настоящие коэффициенты (Pinnacle) на теннис, CS2 и Dota 2 через бесплатный тариф OddsPapi.

Бесплатно — 250 запросов в месяц, поэтому бот экономит:
  • номера видов спорта и рынков узнаёт один раз и запоминает;
  • список турниров обновляет раз в 3 дня, линию — дважды в день (одним запросом на вид спорта);
  • ведёт счётчик запросов и останавливается на BUDGET в месяц — тогда прогнозы снова по рейтингу Эло.
Без ключа ODDSPAPI_KEY модуль ничего не делает.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from . import names

API = "https://api.oddspapi.io/v4"
CACHE = Path(__file__).resolve().parent.parent / "data" / "raw" / "oddspapi"
BUDGET = 230           # из 250 бесплатных — с запасом
REFRESH_HOURS = 11     # линия — примерно дважды в день
# теннис — чаще: матчи следующего круга появляются в линии только после предыдущего; киберспорт — раз в сутки
# (в месяц: теннис ~4×31 + турниры 31 + киберспорт 2×31 ≈ 217 запросов из 230)
REFRESH = {"tennis": 6, "CS2": 23, "DOTA": 23}
TOURNAMENTS_DAYS_BY = {"tennis": 1}
RETRY_HOURS = 3        # после неудачного запроса — повтор не раньше чем через 3 часа
TOURNAMENTS_DAYS = 3
BOOKMAKERS = "pinnacle"  # бесплатный тариф принимает ровно одного букмекера; Pinnacle — самая точная линия
VERSION = 3              # меняется, когда исправляется сам запрос: старые паузы и списки турниров сбрасываются
MAX_TOURNAMENTS = 5      # бесплатный тариф ограничивает число турниров в одном запросе
SPORTS = {"tennis": ("tennis",), "CS2": ("counter", "cs2", "cs-go", "csgo"), "DOTA": ("dota",)}
MSK = "Europe/Moscow"


def enabled() -> bool:
    return bool(os.environ.get("ODDSPAPI_KEY"))


def _get(state: dict, path: str, **params):
    """Запрос с учётом месячного лимита. None — если лимит исчерпан или ошибка."""
    month = pd.Timestamp.now(tz=MSK).strftime("%Y-%m")
    used = state.setdefault("oddspapi", {}).setdefault("used", {})
    if used.get(month, 0) >= BUDGET:
        return None
    used[month] = used.get(month, 0) + 1
    try:
        r = requests.get(f"{API}{path}", params={**params, "apiKey": os.environ["ODDSPAPI_KEY"]}, timeout=30)
        time.sleep(1.1)  # у каждого метода пауза между запросами ~1 с
        if r.status_code == 200:
            return r.json()
        print(f"  ! OddsPapi {path}: {r.status_code} {r.text[:400]}")
    except Exception as e:
        print(f"  ! OddsPapi {path}: {e}")
    return None


def _meta(state: dict) -> dict:
    """Номера видов спорта и рынка «победитель матча» — узнаём один раз."""
    meta = state.setdefault("oddspapi", {}).setdefault("meta", {})
    if "sports" not in meta:
        sports = _get(state, "/sports") or []
        found = {}
        for key, words in SPORTS.items():
            for s in sports:
                text = f"{s.get('slug', '')} {s.get('sportName', '')}".lower()
                if any(w in text for w in words):
                    found[key] = s["sportId"]
                    break
        if found:
            meta["sports"] = found
    if "winner" not in meta and meta.get("sports"):
        markets = _get(state, "/markets") or []
        winner = {}
        for key, sid in meta["sports"].items():
            two_way = [m for m in markets if m.get("sportId") == sid and m.get("marketLength") == 2
                       and not m.get("playerProp") and not m.get("handicap")
                       and any(w in f"{m.get('marketType', '')} {m.get('marketName', '')}".lower()
                               for w in ("winner", "moneyline", "12", "match"))]
            if two_way:
                m = min(two_way, key=lambda x: x["marketId"])
                outs = sorted(m.get("outcomes", []), key=lambda o: o["outcomeId"])
                winner[key] = {"market": str(m["marketId"]), "p1": str(outs[0]["outcomeId"]), "p2": str(outs[1]["outcomeId"])}
        if winner:
            meta["winner"] = winner
    if "extra" not in meta and meta.get("sports"):
        meta["extra"] = _extra_markets(_get(state, "/markets") or [], meta["sports"])
    return meta


def _extra_markets(markets: list, sports: dict) -> dict:
    """Форы ±1.5 и тотал 2.5 по сетам (теннис) или картам (киберспорт) — из того же ответа с линией.

    Возвращает вид спорта → {marketId: [вид, линия, исход1, исход2]}. Форы и тоталы по геймам/раундам
    не берём: в названии рынка должно быть «set» или «map».
    """
    out = {}
    for key, sid in sports.items():
        unit = ("set",) if key == "tennis" else ("map",)
        found = {}
        for m in markets:
            name = f"{m.get('marketType', '')} {m.get('marketName', '')}".lower()
            if m.get("sportId") != sid or m.get("marketLength") != 2 or m.get("playerProp"):
                continue
            if not any(u in name for u in unit) or any(w in name for w in ("game", "round", "kill", "1st", "2nd", "first")):
                continue
            h = m.get("handicap")
            outs = sorted(m.get("outcomes", []), key=lambda o: o["outcomeId"])
            if h is None or len(outs) != 2:
                continue
            kind = "tot" if ("total" in name or "over" in name) else "hcp" if ("handicap" in name or "spread" in name) else None
            if (kind == "tot" and float(h) == 2.5) or (kind == "hcp" and abs(float(h)) == 1.5):
                found[str(m["marketId"])] = [kind, float(h), str(outs[0]["outcomeId"]), str(outs[1]["outcomeId"])]
        out[key] = found
    print(f"  OddsPapi: доп. рынки {({k: len(v) for k, v in out.items()})}")
    return out


def _tournaments(state: dict, key: str, sport_id: int) -> list[int]:
    t = state["oddspapi"].setdefault("tournaments", {})
    saved = t.get(key)
    days = TOURNAMENTS_DAYS_BY.get(key, TOURNAMENTS_DAYS)
    if saved and pd.Timestamp.now(tz=MSK) - pd.Timestamp(saved["at"]) < pd.Timedelta(days=days):
        return saved["ids"]
    items = _get(state, "/tournaments", sportId=sport_id) or []

    def upcoming(x):  # число будущих матчей турнира (название поля в API может отличаться)
        return sum(v for k, v in x.items() if isinstance(v, (int, float)) and ("upcoming" in k.lower() or "future" in k.lower()))
    if key == "tennis":  # публикуем только ATP и WTA — челленджеры, ITF и пары не нужны
        def main_tour(x):
            text = f"{x.get('categoryName', '')} {x.get('tournamentName', '')}".lower()
            return ("atp" in text or "wta" in text) and not any(w in text for w in ("challenger", "itf", "doubles", "qualif"))
        items = [x for x in items if main_tour(x)]
    ids = [x["tournamentId"] for x in sorted(items, key=upcoming, reverse=True) if upcoming(x) > 0][:MAX_TOURNAMENTS]
    if not ids:
        ids = [x["tournamentId"] for x in items][:MAX_TOURNAMENTS]
    t[key] = {"at": pd.Timestamp.now(tz=MSK).isoformat(), "ids": ids}
    return ids


def refresh(state: dict) -> None:
    """Обновляет линию, если пора (раз в REFRESH_HOURS). Результат — в кэше на диске."""
    if not enabled():
        return
    meta = _meta(state)
    if not meta.get("sports") or not meta.get("winner"):
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    if state["oddspapi"].get("ver") != VERSION:  # паузы от прошлой версии клиента (с ошибкой в запросе) не в счёт
        state["oddspapi"]["last"] = {}
        state["oddspapi"]["tournaments"] = {}
        state["oddspapi"]["ver"] = VERSION
    last = state["oddspapi"].setdefault("last", {})
    now = pd.Timestamp.now(tz=MSK)
    for key, sid in meta["sports"].items():
        if key not in meta["winner"]:
            continue
        every = REFRESH.get(key, REFRESH_HOURS)
        if last.get(key) and now - pd.Timestamp(last[key]) < pd.Timedelta(hours=every):
            continue
        # следующая попытка не раньше чем через RETRY_HOURS, даже если сейчас не получится — бережём лимит
        last[key] = (now - pd.Timedelta(hours=max(every - RETRY_HOURS, 0))).isoformat()
        ids = _tournaments(state, key, sid)
        if not ids:
            continue
        data = _get(state, "/odds-by-tournaments", tournamentIds=",".join(map(str, ids)), bookmakers=BOOKMAKERS,
                    oddsFormat="decimal")
        if data is None:
            continue
        w = meta["winner"][key]
        rows = []
        for f in data if isinstance(data, list) else data.get("data", []):
            for book in ("pinnacle", "bet365"):
                mkt = ((f.get("bookmakerOdds") or {}).get(book) or {}).get("markets", {}).get(w["market"])
                if not mkt:
                    continue
                try:
                    p1 = mkt["outcomes"][w["p1"]]["players"]["0"]["price"]
                    p2 = mkt["outcomes"][w["p2"]]["players"]["0"]["price"]
                except (KeyError, TypeError):
                    continue
                if p1 and p2 and p1 > 1 and p2 > 1:
                    markets = ((f.get("bookmakerOdds") or {}).get(book) or {}).get("markets", {})
                    rows.append({"start": f.get("startTime"), "p1": f.get("participant1Name", ""),
                                 "p2": f.get("participant2Name", ""), "o1": float(p1), "o2": float(p2),
                                 "book": "Pinnacle" if book == "pinnacle" else "Bet365",
                                 "extra": _parse_extra(markets, (meta.get("extra") or {}).get(key, {}))})
                    break
        (CACHE / f"{key}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        last[key] = now.isoformat()
        print(f"  OddsPapi: линия {key} — {len(rows)} матчей")


def _parse_extra(markets: dict, wanted: dict) -> dict:
    """{'tot': [2.5, больше, меньше], 'hcp': [фора первого, кэф первого, кэф второго]}"""
    out = {}
    for mid, (kind, h, o1, o2) in wanted.items():
        mkt = markets.get(mid)
        if not mkt or kind in out:
            continue
        try:
            a = mkt["outcomes"][o1]["players"]["0"]["price"]
            b = mkt["outcomes"][o2]["players"]["0"]["price"]
        except (KeyError, TypeError):
            continue
        if a and b and a > 1 and b > 1:
            out[kind] = [h, float(a), float(b)]
    return out


def _surname(name: str) -> str:
    n = names.norm(name.replace(",", " "))
    return n.split()[-1] if n else ""


def lookup(e: dict) -> dict | None:
    """Коэффициенты на победу для матча тенниса/киберспорта: {'H', 'A', 'src'} или None."""
    if not enabled():
        return None
    key = "tennis" if e["sport"] == "tennis" else e["div"]
    path = CACHE / f"{key}.json"
    if not path.exists():
        return None
    k = pd.Timestamp(e["kickoff"])
    h, a = e["home"]["name"], e["away"]["name"]
    best, score, swap = None, 0.0, False
    for r in json.loads(path.read_text(encoding="utf-8")):
        try:
            if abs(pd.Timestamp(r["start"]) - k) > pd.Timedelta(hours=6):
                continue
        except Exception:
            continue
        for flip in (False, True):
            x, y = (r["p2"], r["p1"]) if flip else (r["p1"], r["p2"])
            if e["sport"] == "tennis":  # у теннисистов надёжнее всего сравнивать фамилии
                s = (_surname(h) == _surname(x) or _surname(h) in names.norm(x)) + \
                    (_surname(a) == _surname(y) or _surname(a) in names.norm(y))
            else:
                s = names.similarity(h, x) + names.similarity(a, y)
            if s > score:
                best, score, swap = r, s, flip
    if best is None or score < (2 if e["sport"] == "tennis" else 1.4):
        return None
    o1, o2 = (best["o2"], best["o1"]) if swap else (best["o1"], best["o2"])
    extra = dict(best.get("extra") or {})
    if swap and extra.get("hcp"):  # фора записана для первого участника линии — переворачиваем
        h, a, b = extra["hcp"]
        extra["hcp"] = [-h, b, a]
    return {"H": o1, "A": o2, "src": best["book"], "extra": extra}
