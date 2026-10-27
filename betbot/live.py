"""Live-счёт матчей с открытого API ESPN (бесплатно, без ключей)."""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from .leagues import ALL

URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day}"


def _fetch(code: str, slug: str, day: str) -> list[dict]:
    try:
        r = requests.get(URL.format(slug=slug, day=day), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        events = r.json().get("events", [])
    except Exception:
        return []
    rows = []
    for e in events:
        comp = e["competitions"][0]
        teams = {t["homeAway"]: t for t in comp["competitors"]}
        if "home" not in teams or "away" not in teams:
            continue
        st = e["status"]
        rows.append({
            "Div": code,
            "id": e["id"],
            "Kickoff": pd.Timestamp(e["date"]).tz_convert("Europe/Moscow"),
            "home": teams["home"]["team"]["displayName"],
            "away": teams["away"]["team"]["displayName"],
            "hs": teams["home"].get("score"),
            "aws": teams["away"].get("score"),
            "state": st["type"]["state"],          # pre / in / post
            "clock": st.get("displayClock", ""),
            "detail": st["type"].get("shortDetail", ""),
        })
    return rows


def scoreboard(day_msk: pd.Timestamp) -> pd.DataFrame:
    """Все матчи наших лиг, которые начинаются в этот день по Москве (или ещё идут)."""
    # ESPN группирует по своему дню, поэтому берём вчера/сегодня/завтра и фильтруем сами
    days = [(day_msk + pd.Timedelta(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
    jobs = [(code, v[3], d) for code, v in ALL.items() for d in days]
    with ThreadPoolExecutor(12) as ex:
        rows = [r for part in ex.map(lambda j: _fetch(*j), jobs) for r in part]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates("id")
    same_day = df["Kickoff"].dt.date == day_msk.date()
    return df[same_day | (df["state"] == "in")].sort_values("Kickoff").reset_index(drop=True)
