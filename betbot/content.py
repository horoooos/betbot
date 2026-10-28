"""Тематические посты каждые 3 часа (с картинкой от нейросети) и интерактив: опросы и викторины.

  10:00 — 🔥 Экспресс дня (3 самых надёжных исхода дня в одной ставке; потом бот пишет, зашёл ли он)
  13:00 — 🧠 Ликбез + викторина (по понедельникам — 🏆 итоги недели)
  16:00 — ⭐ Матч дня + опрос «Кто победит?»
  19:00 — 📺 Топ-матчи вечера по всем видам спорта
  22:00 — 📊 Интересные цифры из статистики бота
"""
from html import escape

import pandas as pd

from . import card, sports, telegram
from . import markets as mk
from .leagues import ALL, ORDER, title
from .sports import EMOJI, SPORT_RU

SLOTS = {10: "express", 13: "learn", 16: "match_of_day", 19: "evening", 22: "facts"}
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"

LESSONS = [
    {"title": "Что такое фора", "text": "Фора — это гандикап: к счёту команды прибавляют или отнимают голы. "
     "<b>Ф1 (−1.5)</b> зайдёт, если хозяева выиграют с разницей в 2 мяча и больше. <b>Ф2 (+1.5)</b> — если гости "
     "не проиграют больше чем в один мяч.", "q": "Счёт 2:1. Какая ставка выиграла?",
     "options": ["Ф1 (−1.5)", "Ф2 (+1.5)", "Обе проиграли"], "correct": 1,
     "why": "Хозяева выиграли в один мяч: −1.5 не хватило, а гостям +1.5 хватило.", "prompt": "soccer scoreboard handicap concept, neon, cinematic"},
    {"title": "Что такое тотал", "text": "Тотал — сумма голов обеих команд. <b>ТБ 2.5</b> зайдёт при 3 голах и больше, "
     "<b>ТМ 2.5</b> — при 0, 1 или 2 голах. Половинка (.5) нужна, чтобы не было возврата.",
     "q": "Счёт 1:1. Что выиграло?", "options": ["ТБ 2.5", "ТМ 2.5", "Возврат"], "correct": 1,
     "why": "2 гола меньше 2.5 — зашёл тотал меньше.", "prompt": "soccer goal net close up, soccer ball, dramatic stadium lights"},
    {"title": "Как кэф превращается в вероятность", "text": "Вероятность ≈ 1 / коэффициент. Кэф 2.00 — это примерно 50%, "
     "1.50 — 67%, 3.00 — 33%. Сумма по всем исходам у букмекера всегда больше 100% — разница и есть его маржа.",
     "q": "Какую вероятность заложил букмекер в кэф 4.00?", "options": ["40%", "25%", "4%"], "correct": 1,
     "why": "1 / 4 = 0.25, то есть 25%.", "prompt": "sports betting odds board glowing numbers, futuristic"},
    {"title": "Что такое value-ставка", "text": "Value — ставка, где ваша вероятность × коэффициент больше 1. "
     "Если исход случается в 50% случаев, а кэф 2.20 — это value (0.5 × 2.2 = 1.1). На длинной дистанции только такие "
     "ставки дают плюс.", "q": "Вероятность 40%, кэф 2.30. Это value?", "options": ["Да", "Нет"], "correct": 1,
     "why": "0.4 × 2.3 = 0.92 < 1 — в долгую это минус.", "prompt": "diamond on a soccer pitch, value concept, cinematic"},
    {"title": "Банкролл-менеджмент", "text": "Главное правило — ставить фиксированную небольшую часть банка, обычно 1–3%. "
     "Тогда серия проигрышей (а она будет у любого) не обнулит счёт. Никогда не отыгрывайтесь, удваивая ставки.",
     "q": "Банк 10 000 ₽. Какая ставка разумна по правилу 1–3%?", "options": ["100–300 ₽", "1 000–3 000 ₽", "5 000 ₽"],
     "correct": 0, "why": "1–3% от 10 000 — это 100–300 ₽.", "prompt": "piggy bank and coins, money management concept, soft light"},
    {"title": "Двойной шанс", "text": "<b>1X</b> — хозяева не проиграют, <b>X2</b> — гости не проиграют, <b>12</b> — "
     "кто-то победит (без ничьей). Кэф ниже, зато заходит чаще.", "q": "Счёт 0:0. Какие ставки зашли?",
     "options": ["1X и X2", "Только 12", "Только 1X"], "correct": 0,
     "why": "Ничья устраивает и 1X, и X2.", "prompt": "two soccer teams shaking hands, stadium, cinematic"},
    {"title": "Экспресс", "text": "Экспресс — несколько исходов в одной ставке, кэфы перемножаются. Он заходит, только если "
     "сыграли все события. Три исхода по 70% вместе — уже всего ~34%.", "q": "Кэфы 1.5, 1.6 и 1.7 в экспрессе. Итоговый кэф?",
     "options": ["4.80", "4.08", "3.40"], "correct": 1, "why": "1.5 × 1.6 × 1.7 = 4.08.", "prompt": "betting slip with three soccer matches, neon"},
    {"title": "Почему ничья в хоккее особенная", "text": "В хоккее «П1» обычно включает овертайм и буллиты, а ставки "
     "«в основное время» — нет. Ничья в основное время бывает примерно в каждом 4–5-м матче.",
     "q": "Основное время 2:2, хозяева победили по буллитам. Зашла ли «П1 в основное время»?",
     "options": ["Да", "Нет"], "correct": 1, "why": "В основное время была ничья.", "prompt": "ice hockey shootout dramatic arena lights"},
]


def _pct(p: float) -> str:
    return f"{100 * p:.0f}%"


def _sport_title(e: dict) -> str:
    return title(e["div"]) if e["div"] in ALL else sports.title(e["div"])


def _favourites(football: list[dict], other: list[dict], now: pd.Timestamp, hours: int) -> list[dict]:
    """Кандидаты в экспресс: явные фавориты (60–82%) с реальным коэффициентом, в ближайшие N часов."""
    end = now + pd.Timedelta(hours=hours)
    legs = []
    for e in football + other:
        k = pd.Timestamp(e["kickoff"])
        o = e.get("odds") or {}
        if e["state"] != "pre" or not (now + pd.Timedelta(minutes=30) < k <= end) or not (o.get("H") and o.get("A")):
            continue
        if "ru" not in e["home"] or e.get("sport") == "tennis":
            continue
        p = mk.fair([o["H"], o["D"], o["A"]]) if o.get("D") else mk.fair([o["H"], o["A"]])
        ph, pa = float(p[0]), float(p[-1])
        side, prob, odds = ("home", ph, o["H"]) if ph >= pa else ("away", pa, o["A"])
        if 0.6 <= prob <= 0.82:
            team = e[side]["ru"]
            legs.append({"sport": e.get("sport", "football"), "div": e["div"], "id": e["id"], "side": side,
                         "p": prob, "odds": float(odds), "kickoff": e["kickoff"],
                         "home": e["home"]["ru"], "away": e["away"]["ru"],
                         "label": f"Победа: {team}" + (" (с ОТ)" if e.get("sport") in ("hockey", "basketball") else "")})
    return sorted(legs, key=lambda x: -x["p"])


def _post(png: bytes, text: str) -> int:
    if len(text) <= telegram.CAPTION_LIMIT:
        return telegram.send_photo(png, text)
    head, _, rest = text.partition("\n\n")
    mid = telegram.send_photo(png, head)
    telegram.send(rest, reply_to=mid, silent=True)
    return mid


def express(state: dict, football, other, now, brand) -> bool:
    legs = _favourites(football, other, now, 14)
    picked, seen = [], set()
    for leg in legs:
        if leg["id"] not in seen:
            picked.append(leg)
            seen.add(leg["id"])
        if len(picked) == 3:
            break
    if len(picked) < 2:
        return False
    total = 1.0
    p_all = 1.0
    for leg in picked:
        total *= leg["odds"]
        p_all *= leg["p"]
    lines = ["🔥 <b>ЭКСПРЕСС ДНЯ</b>", "Самые надёжные исходы сегодняшнего дня в одной ставке:\n"]
    for i, leg in enumerate(picked, 1):
        k = pd.Timestamp(leg["kickoff"])
        lines.append(f"{i}. {k:%H:%M} {escape(leg['home'])} — {escape(leg['away'])}\n"
                     f"   ✅ <b>{escape(leg['label'])}</b> · {_pct(leg['p'])} · кэф {leg['odds']:.2f}")
    lines += [f"\n💰 Итоговый кэф: <b>{total:.2f}</b> · шанс, что зайдёт всё: <b>{_pct(p_all)}</b>",
              "Вечером бот напишет, зашёл ли экспресс 👇", FOOTER]
    png = card.ai_card("sports betting slip glowing on stadium background, neon, cinematic, high detail",
                       "Экспресс дня", f"{len(picked)} события · кэф {total:.2f}", brand)
    mid = _post(png, "\n".join(lines))
    state["express"] = {"msg": mid, "legs": picked, "odds": total, "day": str(now.date()), "done": False}
    return True


def settle_express(state: dict, finished: dict) -> None:
    """finished: (div, id) → итоговый словарь с hs/as. Когда сыграли все события — пишем итог экспресса."""
    ex = state.get("express")
    if not ex or ex.get("done"):
        return
    results = []
    for leg in ex["legs"]:
        f = finished.get(f"{leg['div']}|{leg['id']}")
        if f is None:
            return  # ещё не все матчи закончились
        win = f["hs"] > f["as"] if leg["side"] == "home" else f["as"] > f["hs"]
        results.append((leg, win, f))
    ok = all(w for _, w, _ in results)
    lines = [f"{'✅' if ok else '❌'} <b>ЭКСПРЕСС ДНЯ {'ЗАШЁЛ' if ok else 'НЕ ЗАШЁЛ'}</b>"
             + (f" · кэф {ex['odds']:.2f}" if ok else "")]
    for leg, w, f in results:
        lines.append(f"{'✅' if w else '❌'} {escape(leg['home'])} {f['hs']}:{f['as']} {escape(leg['away'])} — {escape(leg['label'])}")
    telegram.send("\n".join(lines), reply_to=ex["msg"])
    ex["done"] = True


def learn(state: dict, now, brand) -> bool:
    i = int(now.strftime("%j")) % len(LESSONS)
    les = LESSONS[i]
    png = card.ai_card(les["prompt"], les["title"], "Ликбез для ставок", brand)
    mid = _post(png, f"🧠 <b>ЛИКБЕЗ: {escape(les['title']).upper()}</b>\n\n{les['text']}\n\nПроверь себя в викторине 👇")
    telegram.send_poll(les["q"], les["options"], quiz_correct=les["correct"], explanation=les["why"], reply_to=mid)
    return True


def match_of_day(football: list[dict], now, brand) -> bool:
    cands = [e for e in football if e["state"] == "pre" and "ru" in e["home"]
             and now + pd.Timedelta(hours=1) < pd.Timestamp(e["kickoff"]) <= now + pd.Timedelta(hours=14)]
    if not cands:
        return False
    e = min(cands, key=lambda e: (ORDER.get(e["div"], 999), e["kickoff"]))
    k = pd.Timestamp(e["kickoff"])
    o = e.get("odds") or {}
    odds_line = ""
    if o.get("H") and o.get("D") and o.get("A"):
        p = mk.fair([o["H"], o["D"], o["A"]])
        odds_line = f"\n📈 Букмекеры: П1 {_pct(p[0])} · Х {_pct(p[1])} · П2 {_pct(p[2])}"
    text = (f"⭐ <b>МАТЧ ДНЯ</b>\n\n⚽️ <b>{escape(e['home']['ru'])} — {escape(e['away']['ru'])}</b>\n"
            f"🏆 {_sport_title(e)}\n⏰ {k:%H:%M} МСК{odds_line}\n\n"
            "Полный разбор с прогнозом бот выложит примерно за час до начала. А как думаешь ты? 👇")
    png = card.ai_card(f"epic soccer match atmosphere, soccer ball, {e['home']['name']} versus {e['away']['name']}, stadium at night, "
                       "fans, flares, cinematic", "Матч дня", f"{e['home']['ru']} — {e['away']['ru']} · {k:%H:%M} МСК", brand)
    mid = _post(png, text)
    telegram.send_poll(f"Кто победит: {e['home']['ru']} — {e['away']['ru']}?",
                       [f"П1 · {e['home']['ru']}", "Ничья", f"П2 · {e['away']['ru']}"], reply_to=mid)
    return True


def evening(football: list[dict], other: list[dict], now, brand) -> bool:
    end = now + pd.Timedelta(hours=8)
    soon = [e for e in football + other if e["state"] == "pre" and "ru" in e["home"]
            and now < pd.Timestamp(e["kickoff"]) <= end and e.get("sport") != "tennis"]
    if not soon:
        return False
    rank = {"NHL": 5, "NBA": 5}
    top = sorted(soon, key=lambda e: (ORDER.get(e["div"], rank.get(e["div"], 60)), e["kickoff"]))[:8]
    top = sorted(top, key=lambda e: e["kickoff"])
    lines = ["📺 <b>ТОП-МАТЧИ ВЕЧЕРА</b>\n"]
    for e in top:
        lines.append(f"{EMOJI[e.get('sport', 'football')]} {pd.Timestamp(e['kickoff']):%H:%M} "
                     f"<b>{escape(e['home']['ru'])} — {escape(e['away']['ru'])}</b> · {_sport_title(e)}")
    lines.append("\nПрогноз на каждый матч — примерно за час до начала. Включи уведомления 🔔")
    rows = [(f"{pd.Timestamp(e['kickoff']):%H:%M}", e["home"]["ru"], e["away"]["ru"], _sport_title(e).split(" · ")[-1])
            for e in top]
    png = card.schedule_card(f"{now.day:02d}.{now.month:02d} · всего матчей: {len(soon)}", rows, 0, brand,
                             heading="Топ-матчи вечера")
    _post(png, "\n".join(lines))
    return True


def facts(res: pd.DataFrame, now, brand) -> bool:
    if res is None or len(res) < 10:
        return False
    hit = res["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    lines = ["📊 <b>ЦИФРЫ ДНЯ ОТ БОТА</b>\n", f"Всего прогнозов: <b>{len(res)}</b>, основной зашёл в <b>{_pct(hit.mean())}</b>."]
    if "sport" in res:
        by = res.assign(h=hit, s=res["sport"].fillna("football")).groupby("s")["h"].agg(["size", "mean"])
        lines.append("По видам спорта: " + " · ".join(f"{EMOJI.get(s, '')} {SPORT_RU.get(s, s)} {_pct(v['mean'])} ({int(v['size'])})"
                                                      for s, v in by.iterrows()))
    by = res.assign(h=hit).groupby("main_label")["h"].agg(["size", "mean"])
    by = by[by["size"] >= 5].sort_values("mean", ascending=False)
    if len(by):
        lines.append(f"Самый удачный тип прогноза: <b>{escape(by.index[0])}</b> — {_pct(by.iloc[0]['mean'])} "
                     f"из {int(by.iloc[0]['size'])}.")
    best = res[hit].sort_values("main_odds", ascending=False).head(1)
    if len(best):
        b = best.iloc[0]
        lines.append(f"Самый крупный зашедший кэф: <b>{b['main_odds']:.2f}</b> — {escape(str(b['home']))} — "
                     f"{escape(str(b['away']))} ({escape(str(b['main_label']))}).")
    streak = 0
    for h in reversed(hit.tolist()):
        if not h:
            break
        streak += 1
    if streak >= 3:
        lines.append(f"🔥 Сейчас серия: <b>{streak}</b> основных прогнозов подряд зашли!")
    lines.append("\n<i>Вся статистика считается честно — по каждому опубликованному прогнозу.</i>")
    png = card.ai_card("futuristic sports analytics dashboard, glowing charts, dark blue, cinematic", "Цифры дня",
                       f"Основной прогноз заходит в {_pct(hit.mean())}", brand)
    _post(png, "\n".join(lines))
    return True


def weekly(res: pd.DataFrame, now, brand) -> bool:
    if res is None or res.empty:
        return False
    d = pd.to_datetime(res["date"])
    week = res[d > now.tz_localize(None).normalize() - pd.Timedelta(days=8)]
    if week.empty:
        return False
    hit = week["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    profit = (hit * (week["main_odds"].astype(float) - 1) - (~hit)).sum()
    lines = ["🏆 <b>ИТОГИ НЕДЕЛИ</b>\n", f"Прогнозов: <b>{len(week)}</b> · основной зашёл: <b>{int(hit.sum())}</b> "
             f"({_pct(hit.mean())}) · ROI ≈ <b>{100 * profit / len(week):+.1f}%</b>"]
    top = week[hit].sort_values("main_odds", ascending=False).head(3)
    if len(top):
        lines.append("\n💎 <b>Лучшие попадания недели:</b>")
        for _, r in top.iterrows():
            lines.append(f"✅ {escape(str(r['home']))} — {escape(str(r['away']))} ({r['score']}): "
                         f"{escape(str(r['main_label']))} @ {r['main_odds']:.2f}")
    png = card.ai_card("golden trophy on a stadium pitch, confetti, cinematic lighting", "Итоги недели",
                       f"{int(hit.sum())} из {len(week)} · {_pct(hit.mean())}", brand)
    _post(png, "\n".join(lines))
    return True


def run(state: dict, football: list[dict], other: list[dict], res: pd.DataFrame, now: pd.Timestamp, brand: str) -> None:
    """Вызывается каждый запуск: публикует пост своего часа один раз."""
    if now.hour not in SLOTS:
        return
    slot = f"{now.date()}-{now.hour}"
    if state.get("content_slot") == slot:
        return
    state["content_slot"] = slot
    kind = SLOTS[now.hour]
    try:
        if kind == "express":
            done = express(state, football, other, now, brand)
        elif kind == "learn":
            done = weekly(res, now, brand) if now.weekday() == 0 else False
            done = done or learn(state, now, brand)
        elif kind == "match_of_day":
            done = match_of_day(football, now, brand)
        elif kind == "evening":
            done = evening(football, other, now, brand)
        else:
            done = facts(res, now, brand) or learn(state, now, brand)
        print(f"Тематический пост ({kind}): {'опубликован' if done else 'нечего публиковать'}")
    except Exception as e:
        print(f"  ! тематический пост ({kind}) не удался: {e}")
