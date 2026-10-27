"""Загрузка данных с football-data.co.uk (бесплатно, без ключей)."""
import io
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

LEAGUES = {
    "E0": "🏴 Англия, Премьер-лига",
    "SP1": "🇪🇸 Испания, Ла Лига",
    "I1": "🇮🇹 Италия, Серия A",
    "D1": "🇩🇪 Германия, Бундеслига",
    "F1": "🇫🇷 Франция, Лига 1",
}

# Колонки, которые нам нужны (остальное выбрасываем)
KEEP = [
    "Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
    "AvgH", "AvgD", "AvgA", "MaxH", "MaxD", "MaxA",
    "PSH", "PSD", "PSA",
    "Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5",
]

CACHE = Path(__file__).resolve().parent.parent / "data" / "raw"


def current_season_code(today: date | None = None) -> str:
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def season_codes(first_start_year: int, today: date | None = None) -> list[str]:
    last = int(current_season_code(today)[:2])
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(first_start_year, 2000 + last + 1)]


def _get_csv(url: str) -> pd.DataFrame:
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "betbot/1.0"})
            r.raise_for_status()
            text = r.content.decode("utf-8-sig", errors="replace")
            return pd.read_csv(io.StringIO(text), on_bad_lines="skip")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "Date"])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed", errors="coerce")
    df = df.dropna(subset=["Date"])
    for c in df.columns:
        if c not in ("Div", "Date", "HomeTeam", "AwayTeam"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_history(first_start_year: int = 2019, refresh_current: bool = True) -> pd.DataFrame:
    """Все сыгранные матчи по выбранным лигам. Старые сезоны кэшируются на диске."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cur = current_season_code()
    frames = []
    for season in season_codes(first_start_year):
        for league in LEAGUES:
            path = CACHE / f"{league}_{season}.csv"
            if path.exists() and not (refresh_current and season == cur):
                df = pd.read_csv(path)
            else:
                try:
                    df = _get_csv(BASE.format(season=season, league=league))
                except Exception as e:
                    print(f"  ! не удалось скачать {league} {season}: {e}")
                    continue
                df.to_csv(path, index=False)
            df = _clean(df)
            df["Season"] = season
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["FTHG", "FTAG"])
    out["FTHG"] = out["FTHG"].astype(int)
    out["FTAG"] = out["FTAG"].astype(int)
    return out.sort_values("Date").reset_index(drop=True)


def load_fixtures() -> pd.DataFrame:
    """Ближайшие матчи с текущими коэффициентами."""
    df = _clean(_get_csv(FIXTURES_URL))
    return df[df["Div"].isin(LEAGUES)].reset_index(drop=True)
