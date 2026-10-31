"""Угловые и жёлтые карточки по статистике команд (football-data: HC/AC — угловые, HY/AY — жёлтые).

Бесплатных кэфов букмекеров на эти рынки нет, поэтому это аналитика для разбора, а не ставка бота:
ожидаемое число и вероятности тоталов по распределению Пуассона.
"""
import pandas as pd
from scipy.stats import poisson

MIN_GAMES = 5      # меньше матчей у команды — статистике не доверяем
LAST_GAMES = 20    # берём последние матчи команды (дома и в гостях)


def _team(hist: pd.DataFrame, team: str, for_col: tuple[str, str]) -> pd.Series | None:
    """Значения показателя «за» и «против» в последних матчах команды."""
    home = hist[hist["HomeTeam"] == team][["Date", for_col[0], for_col[1]]].rename(columns={for_col[0]: "f", for_col[1]: "a"})
    away = hist[hist["AwayTeam"] == team][["Date", for_col[1], for_col[0]]].rename(columns={for_col[1]: "f", for_col[0]: "a"})
    g = pd.concat([home, away]).dropna().sort_values("Date").tail(LAST_GAMES)
    return g if len(g) >= MIN_GAMES else None


def _over(mean: float, line: float) -> float:
    return float(1 - poisson.cdf(int(line), mean))


def corners_cards(hist: pd.DataFrame, div: str, home: str, away: str) -> dict | None:
    if hist is None or hist.empty or not {"HC", "AC", "HY", "AY"} <= set(hist.columns):
        return None
    lg = hist[hist["Div"] == div].dropna(subset=["HC", "AC"])
    lg = lg[lg["Date"] >= lg["Date"].max() - pd.Timedelta(days=400)]
    if len(lg) < 50:
        return None
    out = {}
    hc, ac = _team(lg, home, ("HC", "AC")), _team(lg, away, ("HC", "AC"))
    if hc is not None and ac is not None:
        base = (lg["HC"].mean() + lg["AC"].mean()) / 2  # средние угловые одной команды в лиге
        eh = hc["f"].mean() * ac["a"].mean() / base   # атака хозяев × «пропускаемые» угловые гостей
        ea = ac["f"].mean() * hc["a"].mean() / base
        total = eh + ea
        out["corners"] = {"home": eh, "away": ea, "total": total,
                          "lines": {L: _over(total, L) for L in (8.5, 9.5, 10.5)}}
    hy, ay = _team(lg.dropna(subset=["HY", "AY"]), home, ("HY", "AY")), _team(lg.dropna(subset=["HY", "AY"]), away, ("HY", "AY"))
    if hy is not None and ay is not None:
        total = (hy["f"].mean() + ay["f"].mean() + hy["a"].mean() + ay["a"].mean()) / 2  # свои + «провоцируемые» у соперника
        out["cards"] = {"total": total, "lines": {L: _over(total, L) for L in (3.5, 4.5, 5.5)}}
    return out or None
