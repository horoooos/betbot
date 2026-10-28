"""Киберспорт (CS2 и Dota 2) через PandaScore (бесплатный тариф, нужен ключ в секрете PANDASCORE_TOKEN).

Коэффициентов в бесплатном тарифе нет, поэтому вероятности — по своему рейтингу Эло команд,
посчитанному по истории матчей. Берём только турниры уровня S, A и B, чтобы не тонуть в мелочи.
Без ключа модуль просто ничего не делает.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.pandascore.co"
GAMES = {"CS2": "csgo", "DOTA": "dota2"}  # код лиги в боте → игра в PandaScore
TIERS = {"s", "a", "b"}
CACHE = Path(__file__).resolve().parent.parent / "data" / "raw" / "esports"
MSK = "Europe/Moscow"


def enabled() -> bool:
    return bool(os.environ.get("PANDASCORE_TOKEN"))


def _get(path: str, **params) -> list:
    headers = {"Authorization": f"Bearer {os.environ['PANDASCORE_TOKEN']}", "Accept": "application/json"}
    for attempt in range(3):
        try:
            r = requests.get(API + path, params=params, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                print(f"  ! PandaScore отказал в доступе ({r.status_code}) — проверь ключ PANDASCORE_TOKEN")
                return []
        except Exception:
            pass
        time.sleep(1 + attempt)
    return []


def _tier(m: dict) -> str:
    return str((m.get("tournament") or {}).get("tier") or "").lower()


def _normalize(code: str, m: dict) -> dict | None:
    opp = [o.get("opponent") or {} for o in m.get("opponents") or []]
    if len(opp) != 2 or not all(o.get("id") for o in opp):
        return None
    status = m.get("status")
    if status in ("canceled", "postponed"):
        return None
    begin = m.get("begin_at") or m.get("scheduled_at")
    if not begin:
        return None
    scores = {str(r.get("team_id")): r.get("score") for r in m.get("results") or []}
    winner = str(m.get("winner_id")) if m.get("winner_id") else None
    teams = []
    for o in opp:
        tid = str(o["id"])
        teams.append({"id": tid, "name": o.get("name") or o.get("acronym") or "?", "ru": o.get("name") or "?",
                      "logo": o.get("image_url"), "color": "3b4a7a", "score": scores.get(tid),
                      "winner": winner == tid if winner else False})
    league = (m.get("league") or {}).get("name", "")
    serie = (m.get("serie") or {}).get("full_name") or (m.get("serie") or {}).get("name") or ""
    return {"id": str(m["id"]), "div": code, "sport": "esports",
            "tournament": " · ".join(x for x in (league, serie) if x),
            "bo": int(m.get("number_of_games") or 1),
            "kickoff": pd.Timestamp(begin).tz_convert(MSK).isoformat(),
            "state": {"not_started": "pre", "running": "in", "finished": "post"}.get(status, "pre"),
            "completed": status == "finished", "status": status or "", "tier": _tier(m),
            "home": teams[0], "away": teams[1]}


def fetch() -> list[dict]:
    """Ближайшие, идущие и недавно закончившиеся матчи CS2 и Dota 2 (турниры S/A/B)."""
    if not enabled():
        return []
    out = []
    for code, game in GAMES.items():
        for kind, params in (("upcoming", {"per_page": 100, "sort": "begin_at"}),
                             ("running", {"per_page": 50}),
                             ("past", {"per_page": 100, "sort": "-end_at"})):
            for m in _get(f"/{game}/matches/{kind}", **params):
                if _tier(m) in TIERS and (e := _normalize(code, m)):
                    out.append(e)
    return list({(e["div"], e["id"]): e for e in out}.values())


def history(refresh: bool) -> list[dict]:
    """Завершённые матчи за год (все уровни — для рейтинга важны и мелкие турниры). Кэш дополняется раз в день."""
    if not enabled():
        return []
    CACHE.mkdir(parents=True, exist_ok=True)
    all_matches = []
    for code, game in GAMES.items():
        path = CACHE / f"{code}.json"
        known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if refresh or not known:
            seen = {m["id"] for m in known}
            for page in range(1, 31 if not known else 6):
                batch = _get(f"/{game}/matches/past", per_page=100, page=page, sort="-end_at")
                fresh = [e for m in batch if (e := _normalize(code, m)) and e["completed"]]
                new = [e for e in fresh if e["id"] not in seen]
                known.extend(new)
                seen.update(e["id"] for e in new)
                if len(batch) < 100 or (known and not new):
                    break
            year_ago = (pd.Timestamp.now(tz=MSK) - pd.Timedelta(days=365)).isoformat()
            known = [m for m in known if m["kickoff"] >= year_ago]
            path.write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")
        all_matches.extend(known)
    return sorted(all_matches, key=lambda m: m["kickoff"])
