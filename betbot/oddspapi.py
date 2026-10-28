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
RETRY_HOURS = 3        # после неудачного запроса — повтор не раньше чем через 3 часа
TOURNAMENTS_DAYS = 3
BOOKMAKERS = "pinnacle"  # бесплатный тариф принимает ровно одного букмекера; Pinnacle — самая точная линия
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
        print(f"  ! OddsPapi {path}: {r.status_code} {r.text[:120]}")
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
    return meta


def _tournaments(state: dict, key: str, sport_id: int) -> list[int]:
    t = state["oddspapi"].setdefault("tournaments", {})
    saved = t.get(key)
    if saved and pd.Timestamp.now(tz=MSK) - pd.Timestamp(saved["at"]) < pd.Timedelta(days=TOURNAMENTS_DAYS):
        return saved["ids"]
    items = _get(state, "/tournaments", sportId=sport_id) or []

    def upcoming(x):  # число будущих матчей турнира (название поля в API может отличаться)
        return sum(v for k, v in x.items() if isinstance(v, (int, float)) and ("upcoming" in k.lower() or "future" in k.lower()))
    ids = [x["tournamentId"] for x in sorted(items, key=upcoming, reverse=True) if upcoming(x) > 0][:40]
    if not ids:
        ids = [x["tournamentId"] for x in items][:40]
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
    last = state["oddspapi"].setdefault("last", {})
    now = pd.Timestamp.now(tz=MSK)
    for key, sid in meta["sports"].items():
        if key not in meta["winner"]:
            continue
        if last.get(key) and now - pd.Timestamp(last[key]) < pd.Timedelta(hours=REFRESH_HOURS):
            continue
        # следующая попытка не раньше чем через RETRY_HOURS, даже если сейчас не получится — бережём лимит
        last[key] = (now - pd.Timedelta(hours=REFRESH_HOURS - RETRY_HOURS)).isoformat()
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
                    rows.append({"start": f.get("startTime"), "p1": f.get("participant1Name", ""),
                                 "p2": f.get("participant2Name", ""), "o1": float(p1), "o2": float(p2),
                                 "book": "Pinnacle" if book == "pinnacle" else "Bet365"})
                    break
        (CACHE / f"{key}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        last[key] = now.isoformat()
        print(f"  OddsPapi: линия {key} — {len(rows)} матчей")


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
    return {"H": o1, "A": o2, "src": best["book"]}
