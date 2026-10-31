"""Тематические посты каждые 3 часа (с картинкой от нейросети) и интерактив: опросы и викторины.

  10:00 — 🔥 Экспресс дня (3 самых надёжных исхода дня в одной ставке; потом бот пишет, зашёл ли он)
  13:00 — 🧠 Ликбез + викторина (по понедельникам — 🏆 итоги недели)
  16:00 — ⭐ Матч дня + опрос «Кто победит?»
  19:00 — 📺 Топ-матчи вечера по всем видам спорта
  22:00 — 📊 Интересные цифры из статистики бота
  23:00 — 🌙 Итоги дня: все прогнозы дня с ✅/❌
  после матча дня — 🤖 Бот против 👥 подписчиков: кто угадал в опросе
"""
import random
from html import escape

import pandas as pd

from . import card, fun, sports, telegram
from . import markets as mk
from .leagues import ALL, ORDER, title
from .sports import EMOJI, SPORT_RU
from .texts import MONTHS

MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
              "Ноябрь", "Декабрь"]

SLOTS = {10: "express", 13: "learn", 16: "match_of_day", 19: "evening", 20: "risky", 22: "facts", 23: "recap"}
RISKY_MIN_ODDS = 10.0  # «экспресс на яйцах» — итоговый кэф от 10
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
                         "home": e["home"]["ru"], "away": e["away"]["ru"], "league": _sport_title(e),
                         "logos": [e["home"].get("logo"), e["away"].get("logo")],
                         "colors": [e["home"].get("color"), e["away"].get("color")],
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
    png = card.express_card(picked, total, p_all, f"{now.day} {MONTHS[now.month - 1]}", brand)
    mid = _post(png, _express_text(picked, total, p_all))
    state["express"] = {"msg": mid, "legs": picked, "odds": total, "day": str(now.date()), "done": False}
    return True


def _risky_legs(football: list[dict], other: list[dict], now: pd.Timestamp) -> list[dict]:
    """Кандидаты в «экспресс на яйцах»: матчи вечера и ночи, где у победы шанс 38–62% и кэф 1.6–2.7."""
    end = now + pd.Timedelta(hours=10)
    legs = []
    for e in football + other:
        k = pd.Timestamp(e["kickoff"])
        o = e.get("odds") or {}
        if e["state"] != "pre" or not (now + pd.Timedelta(minutes=30) < k <= end) or not (o.get("H") and o.get("A")):
            continue
        if "ru" not in e["home"] or e.get("sport") == "tennis":
            continue
        p = mk.fair([o["H"], o["D"], o["A"]]) if o.get("D") else mk.fair([o["H"], o["A"]])
        for side, prob, odds in (("home", float(p[0]), float(o["H"])), ("away", float(p[-1]), float(o["A"]))):
            if 0.38 <= prob <= 0.62 and 1.6 <= odds <= 2.7:
                team = e[side]["ru"]
                legs.append({"sport": e.get("sport", "football"), "div": e["div"], "id": e["id"], "side": side,
                             "p": prob, "odds": odds, "kickoff": e["kickoff"],
                             "home": e["home"]["ru"], "away": e["away"]["ru"], "league": _sport_title(e),
                             "logos": [e["home"].get("logo"), e["away"].get("logo")],
                             "colors": [e["home"].get("color"), e["away"].get("color")],
                             "label": f"Победа: {team}" + (" (с ОТ)" if e.get("sport") in ("hockey", "basketball") else "")})
    return sorted(legs, key=lambda x: -x["p"])


def risky(state: dict, football, other, now, brand) -> bool:
    """🥚 Экспресс на яйцах: 3–6 событий вечера с итоговым кэфом от 10 — ставка «на кураж» на копейки."""
    picked, seen, total, p_all = [], set(), 1.0, 1.0
    for leg in _risky_legs(football, other, now):
        if leg["id"] in seen:
            continue
        picked.append(leg)
        seen.add(leg["id"])
        total *= leg["odds"]
        p_all *= leg["p"]
        if total >= RISKY_MIN_ODDS and len(picked) >= 3:
            break
        if len(picked) == 6:
            break
    if total < RISKY_MIN_ODDS or len(picked) < 3:
        return False
    picked.sort(key=lambda x: x["kickoff"])  # в посте и на картинке — по времени начала
    lines = ["🥚 <b>ЭКСПРЕСС НА ЯЙЦАХ</b>", "Вечерняя ставка на кураж: кэф от 10, событий больше — риск выше.\n"]
    for i, leg in enumerate(picked, 1):
        k = pd.Timestamp(leg["kickoff"])
        lines.append(f"{i}. {k:%H:%M} {escape(leg['home'])} — {escape(leg['away'])}\n"
                     f"   🎲 <b>{escape(leg['label'])}</b> · {_pct(leg['p'])} · кэф {leg['odds']:.2f}")
    lines += [f"\n💰 Итоговый кэф: <b>{total:.2f}</b> · шанс, что зайдёт всё: <b>{_pct(p_all)}</b>",
              "🧠 Это лотерея, а не стратегия: ставь сумму, которую не жалко, — максимум 0.5% банка.",
              "Бот будет отмечать каждый матч ответом на этот пост 👇", FOOTER]
    png = card.express_card(picked, total, p_all, f"{now.day} {MONTHS[now.month - 1]} · вечер", brand,
                            title="Экспресс на яйцах", colors=((200, 40, 90), (120, 50, 220)))
    mid = _post(png, "\n".join(lines))
    state["express_risk"] = {"msg": mid, "legs": picked, "odds": total, "day": str(now.date()), "done": False}
    return True


def repost_express(state: dict, football: list[dict], other: list[dict], now, brand) -> bool:
    """Переотправить сегодняшний экспресс с новой картинкой (логотипы берём из текущего расписания)."""
    ex = state.get("express")
    if not ex or ex.get("day") != str(now.date()) or ex.get("done"):
        return express(state, football, other, now, brand)
    by_key = {f"{e['div']}|{e['id']}": e for e in football + other}
    for leg in ex["legs"]:
        e = by_key.get(f"{leg['div']}|{leg['id']}")
        if e:
            leg.setdefault("logos", [e["home"].get("logo"), e["away"].get("logo")])
            leg.setdefault("colors", [e["home"].get("color"), e["away"].get("color")])
            leg.setdefault("league", _sport_title(e))
    p_all = 1.0
    for leg in ex["legs"]:
        p_all *= leg["p"]
    png = card.express_card(ex["legs"], ex["odds"], p_all, f"{now.day} {MONTHS[now.month - 1]}", brand)
    ex["msg"] = _post(png, _express_text(ex["legs"], ex["odds"], p_all))  # итог придёт ответом на новый пост
    return True


def _express_text(legs: list[dict], total: float, p_all: float) -> str:
    lines = ["🔥 <b>ЭКСПРЕСС ДНЯ</b>", "Самые надёжные исходы сегодняшнего дня в одной ставке:\n"]
    for i, leg in enumerate(legs, 1):
        k = pd.Timestamp(leg["kickoff"])
        lines.append(f"{i}. {k:%H:%M} {escape(leg['home'])} — {escape(leg['away'])}\n"
                     f"   ✅ <b>{escape(leg['label'])}</b> · {_pct(leg['p'])} · кэф {leg['odds']:.2f}")
    lines += [f"\n💰 Итоговый кэф: <b>{total:.2f}</b> · шанс, что зайдёт всё: <b>{_pct(p_all)}</b>",
              "Вечером бот напишет, зашёл ли экспресс 👇", FOOTER]
    return "\n".join(lines)


EXPRESSES = (("express", "ЭКСПРЕСС ДНЯ", "завтра в 10:00 новый"), ("express_risk", "ЭКСПРЕСС НА ЯЙЦАХ", "завтра в 20:00 новый"))


def settle_express(state: dict, finished: dict) -> None:
    """finished: (div, id) → итоговый словарь с hs/as. Отмечаем каждый сыгранный матч обоих экспрессов."""
    for key, name, again in EXPRESSES:
        _settle_one(state.get(key), finished, name, again)


def _settle_one(ex: dict | None, finished: dict, name: str, again: str) -> None:
    if not ex or ex.get("done"):
        return
    fresh = False
    for leg in ex["legs"]:
        f = finished.get(f"{leg['div']}|{leg['id']}")
        if f is None or "win" in leg:
            continue
        leg["win"] = f["hs"] > f["as"] if leg["side"] == "home" else f["as"] > f["hs"]
        leg["score"] = f"{f['hs']}:{f['as']}"
        fresh = True
    if not fresh:
        last = max(pd.Timestamp(leg["kickoff"]) for leg in ex["legs"])
        if pd.Timestamp.now(tz="Europe/Moscow") - last > pd.Timedelta(hours=36):
            ex["done"] = True  # матч пропал из расписания ESPN (перенос/отмена) — больше не ждём
        return
    played = [leg for leg in ex["legs"] if "win" in leg]
    waiting = [leg for leg in ex["legs"] if "win" not in leg]
    lost = any(not leg["win"] for leg in played)

    def row(leg):
        return f"{'✅' if leg['win'] else '❌'} {escape(leg['home'])} {leg['score']} {escape(leg['away'])} — {escape(leg['label'])}"
    if lost or not waiting:  # итог: либо одно событие не зашло, либо сыграли все
        ok = not lost
        lines = [f"{'✅' if ok else '❌'} <b>{name} {'ЗАШЁЛ' if ok else 'НЕ ЗАШЁЛ'}</b>"
                 + (f" · кэф {ex['odds']:.2f}" if ok else "")] + [row(leg) for leg in played]
        lines += [f"⏳ {escape(leg['home'])} — {escape(leg['away'])} — уже не важно" for leg in waiting]
        lines.append(f"\n<i>{'Касса! 💰 Экспресс собран полностью' if ok else f'Экспресс сгорел — {again} 🔄'}</i>")
        ex["done"] = True
    else:  # промежуточный итог: событие зашло, ждём остальные
        lines = [f"🔥 <b>{name}: {len(played)} из {len(ex['legs'])} уже зашли!</b>"] + [row(leg) for leg in played]
        lines += [f"⏳ {escape(leg['home'])} — {escape(leg['away'])} · {escape(leg['label'])} · "
                  f"{pd.Timestamp(leg['kickoff']):%H:%M} МСК" for leg in waiting]
        lines.append("\nДержим кулачки 🤞")
    telegram.send("\n".join(lines), reply_to=ex["msg"])


def learn(state: dict, now, brand) -> bool:
    """🧠 Ликбез с викториной: следующая тема из банка (betbot/lessons.py), рубрики по очереди, без повторов."""
    from . import lessons
    used = state.setdefault("lesson_titles", [])
    les = lessons.next_lesson(used)
    used.append(les["title"])
    sport, rubric = les["sport"], les["rubric"]
    png = card.ai_card(f"{random.choice(SCENES_LEARN.get(sport, SCENES_LEARN['football']))}, cinematic, no text, no people",
                       les["title"], f"Ликбез · {rubric}", brand, sport=sport, accent=card.RUBRIC["lesson"])
    mid = _post(png, f"🧠 <b>ЛИКБЕЗ · {escape(rubric).upper()}: {escape(les['title']).upper()}</b>\n\n"
                     f"{escape(les['text'])}\n\nПроверь себя в викторине 👇")
    telegram.send_poll(les["q"], les["options"], quiz_correct=les["correct"], explanation=les["why"], reply_to=mid)
    return True


SCENES_LEARN = {
    "football": ["empty football stadium at golden hour, green pitch", "soccer ball on chalk line, stadium lights"],
    "hockey": ["empty ice hockey rink, puck and stick on ice", "hockey arena lights over fresh ice"],
    "basketball": ["empty basketball court, ball near the hoop", "basketball hoop from below, arena lights"],
    "tennis": ["empty tennis court at night, ball on the baseline", "clay tennis court with racket and ball"],
    "esports": ["empty esports stage with neon lights and gaming PCs", "glowing gaming keyboard and mouse, neon"],
}

def match_of_day(football: list[dict], now, brand, state: dict | None = None) -> bool:
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
    poll = telegram.send_poll(f"Кто победит: {e['home']['ru']} — {e['away']['ru']}?",
                              [f"П1 · {e['home']['ru']}", "Ничья", f"П2 · {e['away']['ru']}"], reply_to=mid)
    if state is not None:
        state["mod_poll"] = {"key": f"{e['div']}|{e['id']}", "id": e["id"], "poll": poll, "post": mid,
                             "home": e["home"]["ru"], "away": e["away"]["ru"], "kickoff": e["kickoff"]}
    return True


def _votes(n: int) -> str:
    return "голос" if n % 10 == 1 and n % 100 != 11 else "голоса" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "голосов"


def settle_poll(state: dict, finished: dict, matches: dict, brand: str) -> None:
    """🤖 Бот против 👥 подписчиков: после матча дня закрываем опрос и сравниваем с прогнозом бота."""
    mp = state.get("mod_poll")
    if not mp or mp["key"] not in finished:
        return
    state.pop("mod_poll")
    f = finished[mp["key"]]
    hs, as_ = f["hs"], f["as"]
    try:
        poll = telegram.stop_poll(mp["poll"])
    except Exception as ex:
        print(f"  ! опрос матча дня не закрылся: {ex}")
        return
    if not poll or (poll.get("total_voter_count") or 0) < 3:  # 1–2 голоса — не соревнование
        return
    votes = [o["voter_count"] for o in poll["options"]]
    total = sum(votes)
    names_ = ["П1", "Ничья", "П2"]
    crowd = max(range(3), key=lambda i: votes[i])
    real = 0 if hs > as_ else 1 if hs == as_ else 2
    m = matches.get(str(mp["id"])) or {}
    bot = None
    if m.get("probs"):
        bot = max(range(3), key=lambda i: m["probs"][["H", "D", "A"][i]])
    lines = ["⚔️ <b>БОТ ПРОТИВ ПОДПИСЧИКОВ</b>\n",
             f"⚽️ <b>{escape(mp['home'])} {hs}:{as_} {escape(mp['away'])}</b>\n",
             f"👥 Подписчики ({total} {_votes(total)}):"]
    for i in range(3):
        share = votes[i] / total
        lines.append(f"<code>{names_[i].ljust(5)} {fun.bar(share)} {100 * share:.0f}%</code>" + (" ✅" if i == real else ""))
    lines.append("")
    crowd_ok = crowd == real
    lines.append(f"👥 Большинство за <b>{names_[crowd]}</b> — {'угадали ✅' if crowd_ok else 'мимо ❌'}")
    if bot is not None:
        bot_ok = bot == real
        lines.append(f"🤖 Бот считал фаворитом <b>{names_[bot]}</b> — {'угадал ✅' if bot_ok else 'мимо ❌'}")
        score = state.setdefault("battle", {"bot": 0, "crowd": 0})
        score["bot"] += bot_ok
        score["crowd"] += crowd_ok
        verdict = ("Ничья в споре 🤝" if bot_ok == crowd_ok else "Бот оказался умнее толпы 🤖" if bot_ok
                   else "Подписчики переиграли бота 👏")
        lines.append(f"\n<b>{verdict}</b>\n📈 Общий счёт: 🤖 {score['bot']} : {score['crowd']} 👥")
    lines.append("\nНовый матч дня с опросом — завтра в 16:00 🗳")
    try:
        telegram.send("\n".join(lines), reply_to=mp["post"])
    except Exception as ex:
        print(f"  ! пост «бот против подписчиков» не удался: {ex}")


def recap(res: pd.DataFrame, now, brand) -> bool:
    """🌙 Итоги дня: все рассчитанные сегодня прогнозы одним постом."""
    if res is None or res.empty:
        return False
    day = res[res["date"].astype(str) == str(now.date())]
    if len(day) < 3:
        return False
    hit = day["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    sport = day["sport"].fillna("football") if "sport" in day else pd.Series("football", index=day.index)
    lines = [f"🌙 <b>ИТОГИ ДНЯ · {now.day} {MONTHS[now.month - 1]}</b>\n"]
    for (_, r), h, s in list(zip(day.iterrows(), hit, sport))[-25:]:
        lines.append(f"{'✅' if h else '❌'} {EMOJI.get(s, '⚽️')} {escape(str(r['home']))} — {escape(str(r['away']))} "
                     f"<b>{escape(str(r['score']))}</b> · {escape(str(r['main_label']))}")
    n, w = len(day), int(hit.sum())
    mood = ("🔥 Отличный день!" if w / n >= 0.7 else "👍 День в плюс по проходу" if w / n >= 0.55
            else "😤 Тяжёлый день — завтра отыграемся")
    lines.append(f"\n🎯 Зашло <b>{w} из {n}</b> ({_pct(w / n)}) · {mood}")
    lines.append("\nУтром — расписание и новые прогнозы. Спокойной ночи 😴")
    png = card.ai_card("night stadium with lights turning off, moon above, calm cinematic atmosphere", "Итоги дня",
                       f"Зашло {w} из {n} · {_pct(w / n)}", brand)
    _post(png, "\n".join(lines))
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


def summary(res: pd.DataFrame, now, brand, start: pd.Timestamp, end: pd.Timestamp, heading: str, period: str) -> bool:
    """🏆 Итоги недели/месяца: карточка по видам спорта, лучшие попадания, ROI и value-ставки."""
    from . import pro, texts
    if res is None or res.empty:
        return False
    d = pd.to_datetime(res["date"])
    part = res[(d >= start) & (d < end)].copy()
    if len(part) < 5:
        return False
    part["sport"] = part["sport"].fillna("football") if "sport" in part else "football"
    hit = part["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    rows = [(f"Все виды спорта", *texts.numbers(part))]
    for sp, g in sorted(part.groupby("sport"), key=lambda x: -len(x[1]))[:4]:
        rows.append((f"{SPORT_RU.get(sp, sp)}", *texts.numbers(g)))
    roi = texts.roi_real(part)
    lines = [f"🏆 <b>{heading}</b> · {period}\n",
             f"🎯 Основной прогноз зашёл: <b>{int(hit.sum())} из {len(part)}</b> ({_pct(hit.mean())})"
             + (f" · ROI <b>{roi:+.1f}%</b>" if roi is not None else "")]
    for name, h, n, _ in rows[1:]:
        lines.append(f"   {EMOJI.get(next((k for k, v in SPORT_RU.items() if v == name), ''), '•')} {name}: {h}/{n} ({_pct(h / n)})")
    top = part[hit].sort_values("main_odds", ascending=False).head(3)
    if len(top):
        lines.append("\n💎 <b>Лучшие попадания:</b>")
        for _, r in top.iterrows():
            lines.append(f"✅ {escape(str(r['home']))} — {escape(str(r['away']))} ({r['score']}): "
                         f"{escape(str(r['main_label']))} @ {float(r['main_odds']):.2f}")
    best_day = part.assign(h=hit).groupby("date")["h"].agg(["sum", "size"])
    best_day = best_day[best_day["size"] >= 3]
    if len(best_day):
        bd = (best_day["sum"] / best_day["size"]).idxmax()
        lines.append(f"📅 Лучший день: {texts.date_ru(pd.Timestamp(bd))} — "
                     f"{int(best_day.loc[bd, 'sum'])} из {int(best_day.loc[bd, 'size'])}")
    if pro.value_summary():
        lines.append("\n" + pro.value_summary())
    lines.append("\n<i>Всё посчитано честно — по каждому опубликованному прогнозу.</i>")
    png = card.stats_card(period, rows, brand)
    _post(png, "\n".join(lines))
    return True


def misses_post(res: pd.DataFrame, now, brand) -> bool:
    """😤 Почему не зашло: три самых обидных промаха недели с объяснением и выводом про дисперсию."""
    from . import misses
    today = now.tz_localize(None).normalize()
    rows = misses.worst(res, today - pd.Timedelta(days=7), today + pd.Timedelta(days=1))
    if len(rows) < 2:
        return False
    lines = ["😤 <b>ПОЧЕМУ НЕ ЗАШЛО</b>", "Разбираем три самых обидных промаха недели — честно, без отмазок.\n"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {EMOJI.get(r['sport'], '⚽️')} <b>{escape(r['home'])} {r['score']} {escape(r['away'])}</b>\n"
                     f"   ❌ {escape(r['label'])} · {_pct(r['p'])} · кэф {r['odds']:.2f}\n"
                     f"   💬 {escape(r['why'])}")
    lines.append(f"\n🧠 {misses.lesson(sum(r['p'] for r in rows) / len(rows))}")
    lines.append("Поэтому бот ставит 1–3% банка и оценивает себя на сотнях матчей, а не по одному вечеру.")
    period = f"{(today - pd.Timedelta(days=6)).day} {MONTHS[(today - pd.Timedelta(days=6)).month - 1]} — {today.day} {MONTHS[today.month - 1]}"
    _post(card.misses_card(rows, period, brand), "\n".join(lines))
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
            done = False
            today = now.tz_localize(None).normalize()
            if now.day == 1:  # 1-го числа — итоги прошедшего месяца + слайды «Wrapped»
                try:
                    wrapped(res, now, brand)
                except Exception as ex:
                    print(f"  ! итоги месяца (слайды) не удались: {ex}")
                start = (today - pd.Timedelta(days=1)).replace(day=1)
                done = summary(res, now, brand, start, today, "ИТОГИ МЕСЯЦА",
                               f"{MONTHS_NOM[start.month - 1]} {start.year}")
            if now.weekday() == 0:  # по понедельникам — итоги прошедшей недели
                start = today - pd.Timedelta(days=7)
                done = summary(res, now, brand, start, today, "ИТОГИ НЕДЕЛИ",
                               f"{start.day} {MONTHS[start.month - 1]} — {(today - pd.Timedelta(days=1)).day} "
                               f"{MONTHS[(today - pd.Timedelta(days=1)).month - 1]}") or done
            if now.weekday() == 6 and not done:  # по воскресеньям — разбор провалов недели
                done = misses_post(res, now, brand)
            done = done or learn(state, now, brand)
        elif kind == "match_of_day":
            done = match_of_day(football, now, brand, state)
        elif kind == "evening":
            done = evening(football, other, now, brand)
        elif kind == "risky":
            done = risky(state, football, other, now, brand)
        elif kind == "recap":
            done = recap(res, now, brand)
        else:
            done = facts(res, now, brand) or learn(state, now, brand)
        print(f"Тематический пост ({kind}): {'опубликован' if done else 'нечего публиковать'}")
    except Exception as e:
        print(f"  ! тематический пост ({kind}) не удался: {e}")


GUIDE = (
    "📌 <b>ПУТЕВОДИТЕЛЬ ПО КАНАЛУ «АИ СТАВИТ»</b>\n\n"
    "Бот сам разбирает матчи по футболу, хоккею, баскетболу, теннису и киберспорту, даёт прогнозы и честно "
    "считает каждый — включая промахи.\n\n"
    "🕗 <b>08:00</b> — статистика, расписание и ⭐ прогнозы дня #прогнозы_дня\n"
    "🎯 <b>за час до матча</b> — прогноз и полный разбор #прогноз #разбор\n"
    "🔴 <b>во время матча</b> — старт, голы и итог #live #итог\n"
    "🔥 <b>10:00</b> — экспресс дня #экспресс\n"
    "💎 <b>11:00</b> — value: кэфы выше справедливых #value\n"
    "🧠 <b>13:00</b> — ликбез с викториной #ликбез · по воскресеньям — разбор провалов #провалы\n"
    "⭐ <b>16:00</b> — матч дня и опрос #матч_дня\n"
    "🥚 <b>20:00</b> — экспресс на яйцах, кэф 10+ #экспресс_на_яйцах\n"
    "🌙 <b>23:00</b> — итоги дня #итоги_дня\n"
    "📰 новости — каждый час с 8:00 до 2:00 · 🏆 по понедельникам — итоги недели\n\n"
    "📊 Вся статистика, банк и ROI: horoooos.github.io/betbot\n"
    "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"
)


def guide(brand: str) -> int:
    """📌 Закреплённый путеводитель: что за канал, расписание рубрик и хештеги."""
    rows = [("08:00", "Статистика, расписание, прогнозы дня", "#прогнозы_дня"),
            ("за 1 ч", "Прогноз и полный разбор матча", "#прогноз"),
            ("live", "Старт, голы и итог матча", "#live"),
            ("10:00", "Экспресс дня", "#экспресс"),
            ("13:00", "Ликбез · по вс — разбор провалов", "#ликбез"),
            ("16:00", "Матч дня и опрос", "#матч_дня"),
            ("20:00", "Экспресс на яйцах · кэф 10+", "#экспресс_на_яйцах"),
            ("23:00", "Итоги дня", "#итоги_дня")]
    png = card.list_card("АИ СТАВИТ", "путеводитель по каналу", rows, brand)
    mid = _post(png, GUIDE)
    telegram.pin(mid)
    return mid


def weekend_poster(events: list[dict], now, brand) -> bool:
    """🎪 Пятничная афиша: главные матчи субботы и воскресенья."""
    start = now.normalize() + pd.Timedelta(days=1)
    end = start + pd.Timedelta(days=2)
    games = [e for e in events if e["state"] == "pre" and "ru" in e["home"] and start <= pd.Timestamp(e["kickoff"]) < end]
    rank = {"NHL": 30, "NBA": 30}
    top = sorted(games, key=lambda e: (ORDER.get(e["div"], rank.get(e["div"], 90)), e["kickoff"]))[:8]
    if len(top) < 3:
        return False
    top.sort(key=lambda e: e["kickoff"])
    days = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}
    rows = [(f"{days[pd.Timestamp(e['kickoff']).weekday()]} {pd.Timestamp(e['kickoff']):%H:%M}",
             f"{e['home']['ru']} — {e['away']['ru']}", _sport_title(e).split(" · ")[-1]) for e in top]
    lines = ["🎪 <b>АФИША ВЫХОДНЫХ</b>", "Главные матчи субботы и воскресенья — прогноз на каждый выйдет за час до начала:\n"]
    for (t, match, league), e in zip(rows, top):
        lines.append(f"{EMOJI.get(e.get('sport', 'football'), '⚽️')} {t} <b>{escape(match)}</b> · {escape(league)}")
    lines.append("\nВключай уведомления, чтобы не пропустить 🔔")
    png = card.list_card("Афиша выходных", f"{start.day} — {(end - pd.Timedelta(days=1)).day} {MONTHS[(end - pd.Timedelta(days=1)).month - 1]}",
                         [(t.split()[0] + " " + t.split()[1], m, lg) for t, m, lg in rows], brand,
                         colors=((230, 60, 120), (60, 120, 255)), style="stars")
    _post(png, "\n".join(lines))
    return True


def wrapped(res: pd.DataFrame, now, brand) -> bool:
    """🎁 Итоги месяца в формате «Wrapped»: альбом из 5 слайдов."""
    from . import misses
    if res is None or res.empty:
        return False
    today = now.tz_localize(None).normalize()
    start = (today - pd.Timedelta(days=1)).replace(day=1)
    d = pd.to_datetime(res["date"])
    part = res[(d >= start) & (d < today)].copy()
    if len(part) < 20:
        return False
    part["sport"] = part["sport"].fillna("football") if "sport" in part else "football"
    hit = part["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    month = MONTHS_NOM[start.month - 1].upper()
    n, w = len(part), int(hit.sum())
    slides = [card.slide_card(f"итоги месяца · {month}", f"{n}", "прогнозов опубликовал бот",
                              [f"Основной прогноз зашёл {w} раз — это {100 * w / n:.0f}%",
                               f"Видов спорта: {part['sport'].nunique()} · дней с прогнозами: {part['date'].nunique()}"],
                              ((255, 170, 0), (120, 60, 255)), n="1 / 5", brand=brand)]
    best = part[hit].sort_values("main_odds", ascending=False).head(1)
    if len(best):
        b = best.iloc[0]
        slides.append(card.slide_card("лучший заход месяца", f"{float(b['main_odds']):.2f}",
                                      f"{b['home']} {b['score']} {b['away']}", [f"Прогноз: {b['main_label']} ✓"],
                                      ((46, 204, 113), (20, 120, 160)), accent=(46, 204, 113), n="2 / 5", brand=brand))
    pain = misses.worst(res, start, today, 1)
    if pain:
        x = pain[0]
        slides.append(card.slide_card("самый обидный промах", f"{x['home']} {x['score']} {x['away']}",
                                      f"Прогноз: {x['label']} · {100 * x['p']:.0f}%", [x["why"]],
                                      ((231, 76, 60), (90, 40, 120)), accent=(231, 76, 60), n="3 / 5", brand=brand))
    by_div = part.assign(h=hit).groupby("div")["h"].agg(["size", "mean"])
    by_div = by_div[by_div["size"] >= 5].sort_values("mean", ascending=False)
    if len(by_div):
        div = by_div.index[0]
        name = title(div).split(" · ", 1)[-1] if div in ALL else sports.league_plain(div)
        slides.append(card.slide_card("любимая лига бота", f"{100 * by_div.iloc[0]['mean']:.0f}%",
                                      card.safe(name), [f"{int(by_div.iloc[0]['size'] * by_div.iloc[0]['mean'])} заходов "
                                                        f"из {int(by_div.iloc[0]['size'])}"],
                                      ((60, 150, 255), (40, 200, 190)), accent=(70, 150, 255), n="4 / 5", brand=brand))
    by_sp = part.assign(h=hit).groupby("sport")["h"].agg(["size", "mean"]).sort_values("size", ascending=False)
    slides.append(card.slide_card("по видам спорта", f"{100 * w / n:.0f}%", "общий процент заходов",
                                  [f"{SPORT_RU.get(s, s)}: {100 * r['mean']:.0f}% ({int(r['size'])})" for s, r in by_sp.iterrows()],
                                  ((170, 100, 255), (255, 120, 60)), accent=(170, 100, 255), n=f"{len(slides) + 1} / 5", brand=brand))
    text = (f"🎁 <b>ИТОГИ МЕСЯЦА · {month}</b>\n\n{n} прогнозов · зашло {w} ({100 * w / n:.0f}%)\n"
            "Листай карточки → лучший заход, самый обидный промах, любимая лига бота.")
    telegram.send_album(slides, text)
    return True


DESCRIPTION = ("🤖 Бесплатные прогнозы на спорт от ИИ: футбол, хоккей, NBA, теннис, CS2, Dota 2. Прогноз за час до "
               "матча, live, экспрессы и честная статистика каждого прогноза 📊 horoooos.github.io/betbot · 18+")


def invite(res: pd.DataFrame, brand: str, channel: str = "@aistavvit") -> int:
    """📣 Пост-приглашение «Почему стоит подписаться» — удобно пересылать и отдавать партнёрам по взаимопиару."""
    n = len(res) if res is not None else 0
    hit = res["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"]) if n else pd.Series(dtype=bool)
    days = res["date"].nunique() if n else 0
    stats = [(f"{n}", "прогнозов"), (f"{100 * hit.mean():.0f}%" if n else "—", "основной зашёл"), ("5", "видов спорта")]
    bullets = ["Прогноз и разбор за час до каждого матча", "Live: старт, голы и итог прямо в ленте",
               "Экспресс дня и «экспресс на яйцах» с кэфом 10+", "Честно считаем каждый прогноз — и промахи тоже"]
    png = card.invite_card(stats, bullets, channel, brand)
    text = (f"📣 <b>ПОЧЕМУ СТОИТ ПОДПИСАТЬСЯ НА</b> {channel}\n\n"
            f"🤖 Бот на базе ИИ разбирает матчи по футболу, хоккею, NBA, теннису и киберспорту — и даёт прогнозы бесплатно.\n\n"
            f"✅ Прогноз и полный разбор за час до каждого матча\n"
            f"🔴 Live: старт, голы и итог прямо в ленте\n"
            f"🔥 Экспресс дня в 10:00 и 🥚 экспресс на яйцах (кэф 10+) в 20:00\n"
            f"🧠 Ликбезы с викторинами, итоги недели и разбор провалов\n\n"
            f"📊 <b>Честная статистика:</b> {n} прогнозов за {days} дн., основной зашёл в "
            f"{100 * hit.mean():.0f}% случаев" + (". Все прогнозы — с плюсами и минусами — на сайте: horoooos.github.io/betbot" if n else "")
            + f"\n\n👉 Подписывайся: {channel}\n<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>")
    return _post(png, text)
