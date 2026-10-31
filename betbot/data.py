"""Загрузка данных с football-data.co.uk (бесплатно, без ключей)."""
import io
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .leagues import EXTRA, MAIN

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
EXTRA_URL = "https://www.football-data.co.uk/new/{code}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
EXTRA_FIXTURES_URL = "https://www.football-data.co.uk/new_league_fixtures.csv"
MSK = "Europe/Moscow"

# Колонки, которые нам нужны (остальное выбрасываем)
KEEP = [
    "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
    "AvgH", "AvgD", "AvgA", "MaxH", "MaxD", "MaxA",
    "PSH", "PSD", "PSA",
    "Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5",
    "AHh", "AvgAHH", "AvgAHA", "MaxAHH", "MaxAHA",
    "HC", "AC", "HY", "AY",  # угловые и жёлтые карточки — для разбора матча
]
# В файлах доп. лиг другие названия колонок и только коэффициенты закрытия
EXTRA_RENAME = {
    "Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG",
    "AvgCH": "AvgH", "AvgCD": "AvgD", "AvgCA": "AvgA",
    "MaxCH": "MaxH", "MaxCD": "MaxD", "MaxCA": "MaxA",
    "PSCH": "PSH", "PSCD": "PSD", "PSCA": "PSA",
}

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
            df = pd.read_csv(io.StringIO(text), on_bad_lines="skip")
            df.columns = [c.strip().lstrip("﻿").lstrip("ï»¿") for c in df.columns]
            return df
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
        if c not in ("Div", "Date", "Time", "HomeTeam", "AwayTeam"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _cached(path: Path, url: str, refresh: bool) -> pd.DataFrame | None:
    if path.exists() and not refresh:
        return pd.read_csv(path)
    try:
        df = _get_csv(url)
    except Exception as e:
        print(f"  ! не удалось скачать {url}: {e}")
        return pd.read_csv(path) if path.exists() else None
    df.to_csv(path, index=False)
    return df


def load_history(first_start_year: int = 2021, refresh_current: bool = True,
                 leagues: list[str] | None = None) -> pd.DataFrame:
    """Все сыгранные матчи. Старые сезоны кэшируются на диске, текущий — обновляется."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cur = current_season_code()
    frames = []
    for league in MAIN:
        if leagues and league not in leagues:
            continue
        for season in season_codes(first_start_year):
            df = _cached(CACHE / f"{league}_{season}.csv", BASE.format(season=season, league=league),
                         refresh_current and season == cur)
            if df is None or df.empty:
                continue
            df = _clean(df)
            df["Div"] = league
            frames.append(df)
    for code in EXTRA:
        if leagues and code not in leagues:
            continue
        df = _cached(CACHE / f"{code}_all.csv", EXTRA_URL.format(code=code), refresh_current)
        if df is None or df.empty:
            continue
        df = _clean(df.rename(columns=EXTRA_RENAME))
        df["Div"] = code
        frames.append(df[df["Date"] >= pd.Timestamp(first_start_year, 1, 1)])
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["FTHG", "FTAG"])
    out["FTHG"] = out["FTHG"].astype(int)
    out["FTAG"] = out["FTAG"].astype(int)
    out["Season"] = [current_season_code(d.date()) for d in out["Date"]]
    return out.sort_values("Date").reset_index(drop=True)


def _kickoff(df: pd.DataFrame) -> pd.Series:
    """Время начала по Москве (в файлах указано британское время)."""
    t = df["Time"].fillna("15:00").astype(str).str.slice(0, 5)
    dt = pd.to_datetime(df["Date"].dt.strftime("%Y-%m-%d") + " " + t, errors="coerce")
    return dt.dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert(MSK)


def load_fixtures() -> pd.DataFrame:
    """Ближайшие матчи всех лиг с текущими коэффициентами."""
    main = _clean(_get_csv(FIXTURES_URL))
    main = main[main["Div"].isin(MAIN)]
    frames = [main]
    try:
        extra = _get_csv(EXTRA_FIXTURES_URL)
        by_country = {v[4]: k for k, v in EXTRA.items()}
        extra["Div"] = extra["Country"].map(by_country)
        frames.append(_clean(extra.dropna(subset=["Div"]).rename(columns=EXTRA_RENAME)))
    except Exception as e:
        print(f"  ! доп. лиги недоступны: {e}")
    df = pd.concat(frames, ignore_index=True)
    df["Kickoff"] = _kickoff(df)
    return df.dropna(subset=["Kickoff"]).reset_index(drop=True)
