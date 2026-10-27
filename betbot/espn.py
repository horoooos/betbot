"""Расписание, коэффициенты, таблица, форма, составы и итоги матчей с открытого API ESPN (бесплатно)."""
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day}"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={id}"
MSK = "Europe/Moscow"


def _get(url: str) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1 + attempt)
    return None


def decimal(ml) -> float | None:
    """Американский коэффициент → десятичный."""
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return round(1 + (ml / 100 if ml > 0 else 100 / -ml), 3)


def _odds(comp: dict) -> dict:
    """Коэффициенты букмекера, которые ESPN показывает прямо в расписании."""
    for o in comp.get("odds") or []:
        if not isinstance(o, dict):
            continue
        # в расписании и в карточке матча ESPN отдаёт коэффициенты в разном виде
        ml, tot = o.get("moneyline") or {}, o.get("total") or {}

        def close(block: dict, side: str):
            return ((block.get(side) or {}).get("close") or {}).get("odds")

        out = {
            "H": decimal((o.get("homeTeamOdds") or {}).get("moneyLine") or close(ml, "home")),
            "D": decimal((o.get("drawOdds") or {}).get("moneyLine") or close(ml, "draw")),
            "A": decimal((o.get("awayTeamOdds") or {}).get("moneyLine") or close(ml, "away")),
            "line": o.get("overUnder"),
            "over": decimal(o.get("overOdds") or close(tot, "over")),
            "under": decimal(o.get("underOdds") or close(tot, "under")),
        }
        if out["H"] and out["D"] and out["A"]:
            return out
    return {}


def _team(t: dict) -> dict:
    team = t["team"]
    return {
        "id": team.get("id"),
        "name": team.get("displayName") or team.get("name"),
        "short": team.get("shortDisplayName") or team.get("displayName"),
        "logo": team.get("logo"),
        "color": team.get("color") or "3b4a7a",
        "alt": team.get("alternateColor") or "ffffff",
        "form": t.get("form") or "",
        "score": t.get("score"),
    }


def _event(code: str, slug: str, e: dict) -> dict | None:
    comp = e["competitions"][0]
    teams = {t["homeAway"]: t for t in comp["competitors"]}
    if "home" not in teams or "away" not in teams:
        return None
    st = e["status"]["type"]
    return {
        "id": e["id"],
        "div": code,
        "slug": slug,
        "kickoff": pd.Timestamp(e["date"]).tz_convert(MSK).isoformat(),
        "state": st.get("state"),                       # pre / in / post
        "completed": bool(st.get("completed")),
        "status": st.get("name", ""),                   # STATUS_FULL_TIME, STATUS_POSTPONED…
        "detail": st.get("shortDetail", ""),
        "home": _team(teams["home"]),
        "away": _team(teams["away"]),
        "odds": _odds(comp),
        "venue": (comp.get("venue") or {}).get("fullName"),
    }


def scoreboard(leagues: dict[str, str], days: list[str]) -> list[dict]:
    """Все матчи указанных лиг за указанные дни (YYYYMMDD). leagues: code → slug."""
    jobs = [(code, slug, d) for code, slug in leagues.items() for d in days]

    def one(job):
        code, slug, day = job
        data = _get(SB.format(slug=slug, day=day)) or {}
        return [ev for e in data.get("events", []) if (ev := _event(code, slug, e))]

    with ThreadPoolExecutor(12) as ex:
        events = [ev for part in ex.map(one, jobs) for ev in part]
    return list({e["id"]: e for e in events}.values())


# ── подробности матча ────────────────────────────────────────────────────────

def _stat(stats: list, key: str):
    for s in stats:
        if s.get("abbreviation") == key or s.get("name") == key:
            return s.get("displayValue", s.get("value"))
    return None


def summary(slug: str, event_id: str) -> dict:
    s = _get(SUMMARY.format(slug=slug, id=event_id)) or {}
    out = {"table": {}, "last5": {}, "h2h": [], "h2h_summary": "", "lineups": {}, "goals": [],
           "reds": [], "stats": {}, "venue": None, "city": None}

    gi = (s.get("gameInfo") or {}).get("venue") or {}
    out["venue"] = gi.get("fullName")
    out["city"] = (gi.get("address") or {}).get("city")

    # турнирная таблица
    for g in (s.get("standings") or {}).get("groups", []):
        entries = (g.get("standings") or {}).get("entries", [])
        for e in entries:
            st = e.get("stats", [])
            out["table"][str(e.get("id"))] = {
                "rank": _stat(st, "R"), "gp": _stat(st, "GP"), "w": _stat(st, "W"), "d": _stat(st, "D"),
                "l": _stat(st, "L"), "gd": _stat(st, "GD"), "pts": _stat(st, "P"), "of": len(entries),
            }

    # последние 5 игр каждой команды
    for t in s.get("lastFiveGames") or []:
        tid = str(t.get("team", {}).get("id"))
        games = []
        for ev in t.get("events", []):
            home = str(ev.get("homeTeamId")) == tid
            try:
                hs, as_ = int(ev.get("homeTeamScore")), int(ev.get("awayTeamScore"))
            except (TypeError, ValueError):
                continue
            games.append({"res": ev.get("gameResult"), "gf": hs if home else as_, "ga": as_ if home else hs,
                          "opp": (ev.get("opponent") or {}).get("displayName", ""), "home": home,
                          "date": ev.get("gameDate", "")[:10]})
        out["last5"][tid] = games

    # личные встречи
    for ser in s.get("seasonseries") or []:
        out["h2h_summary"] = ser.get("summary", "")
        for ev in ser.get("events", []):
            comps = {c.get("homeAway"): c for c in ev.get("competitors", [])}
            if "home" in comps and "away" in comps:
                out["h2h"].append({
                    "date": (ev.get("date") or "")[:10],
                    "home_id": str(comps["home"].get("team", {}).get("id") or comps["home"].get("id")),
                    "hs": comps["home"].get("score"), "as": comps["away"].get("score"),
                })
        break

    # составы (появляются примерно за час до матча)
    for r in s.get("rosters") or []:
        tid = str(r.get("team", {}).get("id"))
        starters = [p["athlete"]["displayName"] for p in r.get("roster", []) if p.get("starter")]
        if starters:
            out["lineups"][tid] = {"formation": r.get("formation"), "starters": starters}

    # голы и удаления
    for k in s.get("keyEvents") or []:
        typ = (k.get("type") or {}).get("type", "")
        who = ""
        if k.get("participants"):
            who = (k["participants"][0].get("athlete") or {}).get("displayName", "")
        item = {"min": (k.get("clock") or {}).get("displayValue", ""), "team": str((k.get("team") or {}).get("id")),
                "player": who, "own": "own" in typ, "pen": "penalty" in typ}
        if k.get("scoringPlay") and "shootout" not in typ:
            out["goals"].append(item)
        elif typ == "red-card":
            out["reds"].append(item)

    # статистика матча
    for t in (s.get("boxscore") or {}).get("teams", []):
        tid = str(t.get("team", {}).get("id"))
        out["stats"][tid] = {x["name"]: x.get("displayValue") for x in t.get("statistics", [])}
    return out
