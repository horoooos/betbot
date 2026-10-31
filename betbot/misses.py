"""«Почему не зашло»: раз в неделю — 3 самых обидных промаха основного прогноза с объяснением.

Обидный промах — тот, где бот был уверен сильнее всего (высокая вероятность) и/или промахнулся совсем чуть-чуть
(не хватило одного гола, ничья вместо победы). Объяснение строится по счёту и типу ставки — без выдумок.
"""
import re

import pandas as pd

UNIT = {"football": ("гол", "гола", "голов"), "hockey": ("шайба", "шайбы", "шайб"),
        "basketball": ("очко", "очка", "очков"), "tennis": ("сет", "сета", "сетов"), "esports": ("карта", "карты", "карт")}


GEN1 = {"football": "гола", "hockey": "шайбы", "basketball": "очка", "tennis": "сета", "esports": "карты"}
GENN = {"football": "голов", "hockey": "шайб", "basketball": "очков", "tennis": "сетов", "esports": "карт"}


def _word(n: float, forms: tuple) -> str:
    n = abs(int(round(n)))
    return forms[0] if n % 10 == 1 and n % 100 != 11 else forms[1] if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else forms[2]


def _hits(col: pd.Series) -> pd.Series:
    return col.astype(str).str.lower().isin(["true", "1", "1.0"])


def explain(r: pd.Series) -> tuple[str, float]:
    """(объяснение, «близость» 0–1: 1 — промахнулись совсем чуть-чуть)."""
    key, sport = str(r["main_key"]), str(r.get("sport") or "football")
    if sport == "nan":
        sport = "football"
    try:
        hs, as_ = (int(x) for x in str(r["score"]).split(":"))
    except ValueError:
        return "Матч сложился не так, как ждала линия.", 0.3
    total, diff = hs + as_, hs - as_
    u = UNIT.get(sport, UNIT["football"])
    m = re.search(r"([OU])(\d+(?:\.\d+)?)$", key.replace("HK_", "").replace("BB_", ""))
    if m and not key.startswith(("H_", "A_", "HK_IT")):  # тотал матча
        line = float(m.group(2))
        if re.fullmatch(r"[OU]\d\d", key):  # футбольные ключи: O25 = 2.5, U35 = 3.5
            line = int(key[1]) + int(key[2]) / 10
        gap = abs(total - line) + 0.5
        if m.group(1) == "O":
            need = "одного " + GEN1.get(sport, "гола") if gap <= 1 else f"{gap:.0f} " + GENN.get(sport, "голов")
            return (f"До тотала больше {line:g} не хватило {need}: в матче всего {total}.",
                    1.0 if gap <= 1 else 0.5)
        return f"Тотал меньше {line:g} сломался: в матче {total} {_word(total, u)} — на {gap:.0f} больше линии.", (1.0 if gap <= 1 else 0.5)
    if key in ("BTTS_Y",):
        return f"Обе команды должны были забить, но {'хозяева' if hs == 0 else 'гости'} остались без гола ({hs}:{as_}).", 0.7
    if key in ("BTTS_N",):
        return f"Ждали, что кто-то останется без гола, но забили обе ({hs}:{as_}).", 0.6
    if key in ("H", "HK_H", "HK_ML_H", "BB_ML_H", "TN_W1", "ES_W1", "1X") or key.endswith(("_H", "W1")):
        if diff == 0:
            return f"Фаворит-хозяин не дожал: ничья {hs}:{as_}.", 0.9
        return f"Сенсация: гости выиграли {hs}:{as_}, хотя линия была за хозяев.", 0.4
    if key in ("A", "HK_A", "HK_ML_A", "BB_ML_A", "TN_W2", "ES_W2", "X2") or key.endswith(("_A", "W2")):
        if diff == 0:
            return f"Фаворит-гость не дожал: ничья {hs}:{as_}.", 0.9
        return f"Сенсация: хозяева выиграли {hs}:{as_}, хотя линия была за гостей.", 0.4
    if key == "12":
        return f"Единственный исход против нас — ничья, и она случилась: {hs}:{as_}.", 0.8
    if key == "TN_2S":
        return f"Ждали короткий матч в два сета, но он ушёл в третий ({hs}:{as_}).", 0.8
    if key == "TN_3S":
        return f"Ждали упорную борьбу в три сета, а всё решилось в двух ({hs}:{as_}).", 0.7
    if "-1.5" in key or "−1.5" in str(r["main_label"]):
        return f"Победа была, но разницы не хватило: {hs}:{as_}, а нужно было выиграть в два {u[1]} и больше.", 0.9
    if "+1.5" in key:
        return f"Фора не спасла: проигрыш {hs}:{as_} — с разницей больше, чем закрывала фора.", 0.6
    if key.startswith(("H_O", "A_O", "HK_IT")):
        return f"Команда не набрала нужного индивидуального тотала (счёт {hs}:{as_}).", 0.6
    return f"Итоговый счёт {hs}:{as_} не совпал с прогнозом.", 0.3


def worst(res: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, n: int = 3) -> list[dict]:
    """Самые обидные промахи за период: обидность = уверенность бота × (0.6 + 0.4 × «близость»)."""
    if res is None or res.empty:
        return []
    d = pd.to_datetime(res["date"])
    part = res[(d >= start) & (d < end)]
    part = part[~_hits(part["main_hit"]) & part["score"].astype(str).str.contains(":")]
    part = part[part["score"].astype(str) != "0:0"] if "sport" in part else part
    out = []
    for _, r in part.iterrows():
        why, close = explain(r)
        p = float(r["main_p"])
        out.append({"home": str(r["home"]), "away": str(r["away"]), "score": str(r["score"]),
                    "label": str(r["main_label"]), "p": p, "odds": float(r["main_odds"]),
                    "sport": str(r.get("sport") if pd.notna(r.get("sport")) else "football"),
                    "why": why, "pain": p * (0.6 + 0.4 * close)})
    out.sort(key=lambda x: -x["pain"])
    picked, kinds = [], set()
    for x in out:  # разные типы ставок — разбор интереснее, чем три одинаковые ничьи
        if x["label"] not in kinds:
            picked.append(x)
            kinds.add(x["label"])
        if len(picked) == n:
            return picked
    return (picked + [x for x in out if x not in picked])[:n]


def lesson(p: float) -> str:
    """Короткий вывод о том, почему такие промахи — нормальная часть игры."""
    miss = round((1 - p) * 10)
    return f"При шансе {100 * p:.0f}% промах случается примерно в {miss} матчах из 10 — это не ошибка модели, а дисперсия."
