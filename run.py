"""Один запуск бота. На GitHub Actions — каждые 20 минут днём и каждый час ночью.

Что делает:
  • утром (после 08:00 МСК) — статистика за вчера/7/30 дней и расписание матчей на день;
  • примерно за час до каждого матча — картинка + прогноз + полный разбор;
  • после каждого матча — итог, угадал ли бот, статистика за день;
  • раз в сутки — переобучается на свежих результатах.

Запуск:  python run.py   (без TELEGRAM_TOKEN посты сохраняются в data/preview/)
"""
import difflib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from betbot import card, content, esports, live, names, news, oddspapi, pro, reviews, site, sports, tables, telegram, texts
from betbot import markets as mk
from betbot.data import MSK, load_fixtures, load_history
from betbot.engine import add_market, fit_full, fit_weights, walk_forward
from betbot.espn import _get as espn_get, scoreboard, summary
from betbot.leagues import ALL, EXTRA, MAIN, NATIONAL, ORDER

# Лиги, по которым бот делает обзоры (код → см. betbot/leagues.py). Сейчас — весь доступный футбол.
# Чтобы постов было меньше, перечисли нужные коды, например ["E0", "SP1", "I1", "D1", "F1", "RUS", "UCL"].
REVIEW_LEAGUES = [
    # лиги
    "E0", "E1", "SP1", "I1", "D1", "F1", "N1", "P1", "T1", "B1", "SC0", "RUS", "BRA", "ARG", "USA", "MEX", "KSA",
    # еврокубки и Южная Америка
    "UCL", "UEL", "UECL", "UCLQ", "USC", "LIB", "SUD",
    # национальные кубки (только матчи профессиональных команд, см. CUP_SOURCES)
    "FAC", "ELC", "CDR", "DFB", "CIT", "CDF", "TPO", "SCC",
    # сборные
    "UNL", "WCQE", "WCQS", "WC", "EURO", "FRI",
]
# В кубках играют и любители — берём матч, только если обе команды есть в профессиональных лигах страны
# (названия лиг ESPN: из их таблиц берём список профессиональных команд — названия совпадают с кубковыми)
CUP_SOURCES = {"FAC": ["eng.1", "eng.2", "eng.3", "eng.4"], "ELC": ["eng.1", "eng.2", "eng.3", "eng.4"],
               "CDR": ["esp.1", "esp.2"], "DFB": ["ger.1", "ger.2", "ger.3"], "CIT": ["ita.1", "ita.2"],
               "CDF": ["fra.1", "fra.2"], "TPO": ["por.1", "por.2"], "SCC": ["sco.1", "sco.2"]}
MORNING_HOUR = 8        # во сколько (МСК) выходит расписание
VALUE_HOUR = 11         # во сколько выходит 💎 value дня
DAY_START_HOUR = 6      # «игровой день» — с 06:00 до 06:00 следующего дня
VALUE_EDGE = (0.05, 0.30)

DATA = Path(__file__).resolve().parent / "data"
STATE, MATCHES, RESULTS = DATA / "state.json", DATA / "matches.json", DATA / "results.csv"
OTHER = DATA / "other.json"  # хоккей, баскетбол, теннис, киберспорт
LIVE = DATA / "live.json"    # что уже опубликовано в live (начало матча, счёт)
REPOST = DATA / "repost.json"  # разовая просьба переотправить посты: {"id": "...", "items": ["value", ...]}
HIST_LEAGUES = [c for c in REVIEW_LEAGUES if c in MAIN or c in EXTRA]
BRAND = os.environ.get("TELEGRAM_CHAT_ID", "") if os.environ.get("TELEGRAM_CHAT_ID", "").startswith("@") else ""


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def cup_teams(state: dict, daily: bool) -> dict:
    """Профессиональные команды каждой страны — из таблиц ESPN (обновляется раз в день)."""
    if daily or not state.get("cup_teams"):
        by_league = {}
        for slug in sorted({x for v in CUP_SOURCES.values() for x in v}):
            data = espn_get(f"https://site.api.espn.com/apis/v2/sports/soccer/{slug}/standings") or {}
            groups = data.get("children") or [data]
            by_league[slug] = [e["team"]["displayName"] for g in groups
                               for e in (g.get("standings") or {}).get("entries", [])]
        state["cup_teams"] = {cup: sorted({t for slug in src for t in by_league.get(slug, [])})
                              for cup, src in CUP_SOURCES.items()}
    return state["cup_teams"]


def professional(e: dict, cup_teams: dict) -> bool:
    """Кубковый матч берём, только если обе команды играют в профессиональных лигах страны."""
    teams = cup_teams.get(e["div"])
    if not teams:  # не кубок (или список ещё не собран) — пропускаем фильтр
        return True
    def known(name: str) -> bool:  # почти полное совпадение: «UD Castellonense» ≠ «Castellón»
        n = names.norm(name)
        return name in teams or any(difflib.SequenceMatcher(None, n, names.norm(t)).ratio() >= 0.9 for t in teams)
    return known(e["home"]["name"]) and known(e["away"]["name"])


def matchday(t: pd.Timestamp) -> pd.Timestamp:
    """Матч в 01:30 ночи относится к предыдущему игровому дню."""
    return (t - pd.Timedelta(hours=DAY_START_HOUR)).normalize()


def gap_minutes(now: pd.Timestamp) -> int:
    """Сколько минут до следующего запуска (LOOP_MINUTES в .github/workflows/daily.yml)."""
    return int(os.environ.get("LOOP_MINUTES", "20"))


# ── коэффициенты и вероятности ──────────────────────────────────────────────

def find_fixture(ev: dict, fx: pd.DataFrame) -> pd.Series | None:
    """Ищем этот матч в файле football-data (там средние и лучшие коэффициенты 40+ букмекеров)."""
    if fx is None or fx.empty:
        return None
    k = pd.Timestamp(ev["kickoff"])
    cand = fx[(fx["Div"] == ev["div"]) & ((fx["Kickoff"] - k).abs() <= pd.Timedelta(hours=26))]
    best, score = None, 0.0
    for _, r in cand.iterrows():
        s = names.similarity(ev["home"]["name"], r["HomeTeam"]) + names.similarity(ev["away"]["name"], r["AwayTeam"])
        if s > score:
            best, score = r, s
    return best if score >= 1.3 else None


def _real_max(real: dict, key: str | None, odds) -> None:
    """Настоящий кэф рынка; если один рынок пришёл из двух мест (Ф1(−0.5) = П1) — берём лучший."""
    if key and odds and not pd.isna(odds) and odds > 1.01:
        real[key] = max(float(odds), float(real.get(key) or 0))


def market(ev: dict, row: pd.Series | None) -> dict | None:
    def ok(*vals):
        return all(v is not None and not pd.isna(v) and v > 1.01 for v in vals)

    if row is not None and ok(row.get("AvgH"), row.get("AvgD"), row.get("AvgA")):
        sharp = ok(row.get("PSH"), row.get("PSD"), row.get("PSA"))
        p1x2 = mk.fair([row["PSH"], row["PSD"], row["PSA"]] if sharp else [row["AvgH"], row["AvgD"], row["AvgA"]])
        real = {"H": row["AvgH"], "D": row["AvgD"], "A": row["AvgA"]}
        line = p_over = None
        if ok(row.get("Avg>2.5"), row.get("Avg<2.5")):
            line, p_over = 2.5, float(mk.fair([row["Avg>2.5"], row["Avg<2.5"]])[0])
            real.update({"O25": row["Avg>2.5"], "U25": row["Avg<2.5"]})
        best = {s: row.get(f"Max{s}") for s in "HDA"}
        if ok(row.get("AvgAHH"), row.get("AvgAHA")) and not pd.isna(row.get("AHh")):
            h = float(row["AHh"])
            for side, hh, odd in (("H", h, row["AvgAHH"]), ("A", -h, row["AvgAHA"])):
                _real_max(real, mk.handicap_key(side, hh), odd)
        return {"p1x2": p1x2, "line": line, "p_over": p_over, "real": real, "max": best,
                "src": "среднее по букмекерам"}
    o = ev.get("odds") or {}
    if ok(o.get("H"), o.get("D"), o.get("A")):
        real = {"H": o["H"], "D": o["D"], "A": o["A"]}
        line = p_over = None
        if o.get("line") and ok(o.get("over"), o.get("under")):
            line, p_over = float(o["line"]), float(mk.fair([o["over"], o["under"]])[0])
            tag = {1.5: "15", 2.5: "25", 3.5: "35", 4.5: "45"}.get(line)
            if tag:
                real.update({f"O{tag}": o["over"], f"U{tag}": o["under"]})
        for side, key in (("H", "spread_h"), ("A", "spread_a")):
            if o.get(key) and ok(o[key][1]):
                _real_max(real, mk.handicap_key(side, o[key][0]), o[key][1])
        return {"p1x2": mk.fair([o["H"], o["D"], o["A"]]), "line": line, "p_over": p_over, "real": real,
                "max": {}, "src": "DraftKings"}
    return None


def lambdas(ev, row, mkt, w, hist_loader) -> tuple[float, float] | None:
    lam_mkt = mk.implied_lambdas(mkt["p1x2"], mkt["line"], mkt["p_over"]) if mkt else None
    lam_model = None
    if row is not None and (w > 0 or lam_mkt is None) and ev["div"] in HIST_LEAGUES:
        hist = hist_loader()
        if (hist["Div"] == ev["div"]).sum() >= 200:
            model = fit_full(hist, ev["div"], pd.Timestamp.now(tz=MSK).tz_localize(None))
            lam_model = model.expected_goals(row["HomeTeam"], row["AwayTeam"])
    if lam_mkt and lam_model:  # смешиваем с весом, который бот выучил сам
        return tuple(float(a ** (1 - w) * b ** w) for a, b in zip(lam_mkt, lam_model))
    return lam_mkt or lam_model


def value_pick(probs: dict, mkt: dict | None) -> dict | None:
    if not mkt or not mkt.get("max"):
        return None
    best = None
    for s in "HDA":
        o = mkt["max"].get(s)
        if o is None or pd.isna(o):
            continue
        edge = probs[s] * o - 1
        if VALUE_EDGE[0] <= edge <= VALUE_EDGE[1] and (best is None or edge > best["edge"]):
            best = {"key": s, "label": mk.label(s), "odds": float(o), "edge": float(edge), "p": probs[s]}
    return best


# ── шаги бота ───────────────────────────────────────────────────────────────

def learn(state: dict, now: pd.Timestamp) -> None:
    try:
        hist = load_history(refresh_current=True, leagues=HIST_LEAGUES)
        start = str((now.tz_localize(None) - pd.Timedelta(days=730)).date())
        state["weights"] = fit_weights(add_market(walk_forward(hist, start=start)))
        print(f"    переобучение: вес модели {state['weights']}")
    except Exception as e:
        print(f"  ! переобучение не удалось: {e}")
        state.setdefault("weights", {"1X2": 0.0, "OU25": 0.0})


def read_results() -> pd.DataFrame:
    # тип прогноза «12» — это текст, а не число
    if not RESULTS.exists():
        return pd.DataFrame()
    res = pd.read_csv(RESULTS, dtype={"main_key": str, "bold_key": str, "score": str})
    if "sport" in res:  # теннис «0:0» — несыгранный матч (снятие), засчитан по ошибке старой версией
        res = res[~((res["sport"] == "tennis") & (res["score"] == "0:0"))]
    return res


def post(png: bytes, text: str, reply_to: int | None = None) -> int:
    """Картинка + текст. Длинный текст не влезает в подпись (1024 символа) — тогда он идёт ответом."""
    if len(text) <= telegram.CAPTION_LIMIT:
        return telegram.send_photo(png, text, reply_to)
    head, _, rest = text.partition("\n\n")
    mid = telegram.send_photo(png, head, reply_to)
    telegram.send(rest, reply_to=mid, silent=True)
    return mid


def morning(state: dict, events: list[dict], other: list[dict], now: pd.Timestamp) -> None:
    res = read_results()
    today = now.normalize()
    if len(res):
        rows = [(name, *texts.numbers(df)) for name, df in texts.periods(res, today)]
        png = card.stats_card(f"на {texts.date_ru(today)}", rows, BRAND)
        curve = pro.bank_curve(res)
        extra = [f"💼 <b>Виртуальный банк</b> (ставки ровно по рекомендациям бота): {pro.BANK_START:,} → "
                 f"<b>{curve[-1]:,.0f} ₽</b> ({100 * (curve[-1] / pro.BANK_START - 1):+.1f}%)".replace(",", " ")]
        if pro.clv_summary(res):
            extra.append(pro.clv_summary(res))
        post(png, texts.stats(res, today, mk.calibration(res)) + "\n\n" + "\n\n".join(extra))
    start = pd.Timestamp(today) + pd.Timedelta(hours=DAY_START_HOUR)
    day = [e for e in events if e["state"] == "pre" and start <= pd.Timestamp(e["kickoff"]) < start + pd.Timedelta(days=1)
           and (e["div"] in HIST_LEAGUES or (e.get("odds") or {}).get("H"))]  # только матчи, на которые будет прогноз
    for e in day:
        o = e.get("odds") or {}
        if o.get("H") and o.get("D") and o.get("A"):
            p = mk.fair([o["H"], o["D"], o["A"]])
            if max(p[0], p[2]) >= 0.45:
                e["fav"] = (e["home"]["ru"], p[0]) if p[0] > p[2] else (e["away"]["ru"], p[2])
    extra = sports.schedule_block(other, start)  # хоккей, баскетбол, теннис
    if day or extra:
        top = sorted(day, key=lambda e: (ORDER.get(e["div"], 999), e["kickoff"]))[:8]
        rows = [(f"{pd.Timestamp(e['kickoff']):%H:%M}", e["home"]["ru"], e["away"]["ru"], ALL[e["div"]][2])
                for e in sorted(top, key=lambda e: e["kickoff"])]
        title = f"{texts.DAYS[today.weekday()]}, {texts.date_ru(today)}"
        post(card.schedule_card(title, rows, len(day) - len(top), BRAND), texts.schedule(day, now, extra))
    print(f"Утренний пост: футбольных матчей в расписании {len(day)}")
    try:
        pro.post_top(state, events, other, now, BRAND)  # 3 главных прогноза дня — закрепляются
    except Exception as ex:
        print(f"  ! прогнозы дня не удались: {ex}")


def review(ev: dict, w: dict, fx_loader, hist_loader, calib: dict, state: dict) -> dict | None:
    row = find_fixture(ev, fx_loader())
    mkt = market(ev, row)
    lam = lambdas(ev, row, mkt, w.get("1X2", 0.0), hist_loader)
    if lam is None:
        print(f"  нет коэффициентов и истории: {ev['home']['name']} — {ev['away']['name']}")
        return None
    probs = mk.all_markets(*lam)
    scores = probs.pop("scores")
    main, bold = mk.tips(probs, mkt["real"] if mkt else {}, calib)
    for t in (main, bold):
        if t:
            t["stake"] = pro.stake(t)
    m = {**ev, "open": pro.snapshot(ev, [main.get("key"), (bold or {}).get("key")]),
         "top": pro.is_top(state, ev["div"], ev["id"]), "lam": list(lam), "probs": probs, "scores": scores, "main": main, "bold": bold,
         "value": value_pick(probs, mkt), "odds_src": mkt["src"] if mkt else "нет, только модель",
         "model_w": w.get("1X2", 0.0) if mkt else 1.0,
         "learned_n": len(read_results())}
    s = summary(ev["slug"], ev["id"])
    kick = pd.Timestamp(ev["kickoff"])
    tip = f"{main['label']} · {texts.pct(main['p'])}"
    png = card.match_card(texts.league_plain(ev["div"]), texts.when(kick), ev["home"], ev["away"],
                          (probs["H"], probs["D"], probs["A"]), tip, f"xG {lam[0]:.1f} : {lam[1]:.1f}", BRAND)
    m["msg_id"] = telegram.send_photo(png, texts.caption(m, s.get("venue") or ev.get("venue")))
    telegram.send(texts.review(m, s), reply_to=m["msg_id"], silent=True)
    m["status"] = "reviewed"
    print(f"  обзор: {ev['home']['ru']} — {ev['away']['ru']} → {main['label']}")
    return m


def add_result(m: dict, score: str, sport: str) -> dict:
    """Записывает итог прогноза в results.csv и возвращает статистику за этот день по этому виду спорта."""
    bold = m.get("bold") or {}
    day = str(matchday(pd.Timestamp(m["kickoff"])).date())
    row = {"date": day, "sport": sport, "id": m["id"], "div": m["div"], "home": m["home"]["ru"], "away": m["away"]["ru"],
           "score": score, "main_key": m["main"]["key"], "main_label": m["main"]["label"],
           "main_p": m["main"]["p"], "main_odds": m["main"]["odds"], "main_est": m["main"]["est"],
           "main_hit": m["main_hit"], "bold_key": bold.get("key"), "bold_label": bold.get("label"),
           "bold_p": bold.get("p"), "bold_odds": bold.get("odds"), "bold_hit": m.get("bold_hit"),
           "value_odds": (m.get("value") or {}).get("odds"), "value_hit": m.get("value_hit"),
           "main_stake": m["main"].get("stake", pro.STAKE_MIN), "main_clv": pro.clv(m, m["main"]["key"]),
           "bold_clv": pro.clv(m, bold.get("key"))}
    res = pd.concat([read_results(), pd.DataFrame([row])], ignore_index=True)
    res["sport"] = res["sport"].fillna("football")
    res = res.drop_duplicates(["sport", "id"], keep="last")
    res.to_csv(RESULTS, index=False)
    today = res[(res["date"] == day) & (res["sport"] == sport)]
    tb = today.dropna(subset=["bold_hit"])
    return {"n": len(today), "main": int(texts._hits(today["main_hit"]).sum()),
            "nb": len(tb), "bold": int(texts._hits(tb["bold_hit"]).sum())}


# ── хоккей, баскетбол, теннис ───────────────────────────────────────────────

def other_review(e: dict, calib: dict, ctx: dict, state: dict) -> dict | None:
    """Пост перед матчем (хоккей, баскетбол, теннис, киберспорт): картинка + прогноз, полный разбор — ответом."""
    hist, ratings = ctx.get(e["sport"], ([], {}))
    a = sports.analyse(e, ratings)
    if a is None:
        return None
    m = {**e, **a}
    m["main"], m["bold"] = sports.pick(a, calib)
    for t in (m["main"], m["bold"]):
        if t:
            t["stake"] = pro.stake(t)
    m["open"] = pro.snapshot(e, [m["main"].get("key"), (m["bold"] or {}).get("key")])
    m["top"] = pro.is_top(state, e["div"], e["id"])
    kick = pd.Timestamp(e["kickoff"])
    tip = f"{m['main']['label']} · {texts.pct(m['main']['p'])}"
    png = card.match_card(sports.league_plain(e["div"]), texts.when(kick), e["home"], e["away"], a["bar"], tip,
                          a["center"], BRAND, sport=e["sport"])
    m["msg_id"] = telegram.send_photo(png, sports.caption(m, texts.when(kick)))
    if e["sport"] in ("hockey", "basketball"):
        sport, slug = sports.LEAGUES[e["div"]][3].split("/")
        text = reviews.team_review(m, summary(slug, e["id"], sport))
    else:
        text = reviews.history_review(m, hist, ratings)
    telegram.send(text, reply_to=m["msg_id"], silent=True)
    m["status"] = "reviewed"
    print(f"  обзор ({e['sport']}): {e['home']['ru']} — {e['away']['ru']} → {m['main']['label']}")
    return m


def other_settle(m: dict, e: dict) -> None:
    f = sports.final(e)
    if f is None:
        return
    if f.get("void"):  # снятие, отказ, неявка — ставки возвращаются, в статистику не идёт
        telegram.send(f"↩️ <b>Матч не состоялся</b>: {f['reason']}.\nПрогноз не засчитывается, ставки по нему "
                      f"у букмекеров обычно возвращаются.", reply_to=m["msg_id"])
        m["status"] = "void"
        return
    for side in ("home", "away"):  # у матчей, опубликованных старой версией, может не быть цвета для картинки
        m[side] = {"color": "3b4a7a", "logo": None, **m[side]}
    m["main_hit"] = sports.won(m["main"]["key"], f)
    m["bold_hit"] = sports.won(m["bold"]["key"], f) if m.get("bold") else None
    ds = add_result(m, f.get("sets") or f"{f['hs']}:{f['as']}", m["sport"])
    verdicts = [(f"Основной: {m['main']['label']}", m["main_hit"])]
    if m.get("bold"):
        verdicts.append((f"Смелый: {m['bold']['label']}", m["bold_hit"]))
    png = card.result_card(sports.league_plain(m["div"]), m["home"], m["away"], f["hs"], f["as"], verdicts, BRAND,
                           sport=m["sport"])
    post(png, sports.result_caption(m, f, ds) + pro.clv_line(m), reply_to=m["msg_id"])
    m["status"] = "done"


def other_sports(state: dict, events: list[dict], now: pd.Timestamp, calib: dict, daily: bool) -> None:
    store = load_json(OTHER, {})
    lead = pd.Timedelta(minutes=60 + gap_minutes(now))
    ctx = {}  # история и рейтинг Эло для тенниса и киберспорта — загружаем, только когда нужны
    try:
        oddspapi.refresh(state)  # настоящая линия на теннис и киберспорт (раз в ~11 часов, без ключа — пропуск)
    except Exception as ex:
        print(f"  ! OddsPapi: {ex}")
    for e in sorted(events, key=lambda e: e["kickoff"]):
        key = f"{e['div']}|{e['id']}"
        if e["state"] == "pre" and key not in store and "ru" in e["home"]                 and now < pd.Timestamp(e["kickoff"]) <= now + lead:
            if e["sport"] in ("tennis", "esports") and e["sport"] not in ctx:
                hist = sports.tennis_history(refresh=daily) if e["sport"] == "tennis" else esports.history(refresh=daily)
                ctx[e["sport"]] = (hist, sports.elo(hist))
            if e["sport"] in ("tennis", "esports"):
                e["odds"] = oddspapi.lookup(e) or {}
            try:
                store[key] = other_review(e, calib, ctx, state) or {"status": "skipped", "kickoff": e["kickoff"]}
            except Exception as ex:
                print(f"  ! обзор не удался {key}: {ex}")
            save_json(OTHER, store)
    by_key = {f"{e['div']}|{e['id']}": e for e in events}
    for key, m in store.items():
        capture_close(m, by_key.get(key), now)
    for key, m in store.items():
        e = by_key.get(key)
        if m.get("sport") and m.get("status") == "reviewed" and e and e["completed"]:
            try:
                other_settle(m, e)
            except Exception as ex:
                print(f"  ! итог не удался {key}: {ex}")
            save_json(OTHER, store)
    old = now - pd.Timedelta(days=3)
    save_json(OTHER, {k: v for k, v in store.items() if pd.Timestamp(v["kickoff"]) > old})


def capture_close(m: dict, e: dict | None, now: pd.Timestamp) -> None:
    """Запоминаем линию за несколько минут до начала — с ней сравнивается линия при публикации (CLV)."""
    if not e or m.get("status") != "reviewed" or m.get("close") or e["state"] != "pre":
        return
    if pd.Timestamp(e["kickoff"]) - now <= pd.Timedelta(minutes=8):
        keys = [m["main"].get("key"), (m.get("bold") or {}).get("key")]
        m["close"] = pro.snapshot(e, keys) or {"_": None}


def finished_scores(football: list[dict], other: list[dict]) -> dict:
    """div|id → счёт законченных матчей (для подсчёта экспресса)."""
    out = {}
    for e in football:
        if e["completed"] and str(e["home"]["score"]).isdigit():
            out[f"{e['div']}|{e['id']}"] = {"hs": int(e["home"]["score"]), "as": int(e["away"]["score"])}
    for e in other:
        if e["completed"] and e["sport"] != "tennis" and (f := sports.final(e)):
            out[f"{e['div']}|{e['id']}"] = f
    return out


def settle(m: dict, ev: dict) -> None:
    hs, as_ = int(ev["home"]["score"]), int(ev["away"]["score"])
    s = summary(ev["slug"], ev["id"])
    m["main_hit"] = mk.won(m["main"]["key"], hs, as_)
    m["bold_hit"] = mk.won(m["bold"]["key"], hs, as_) if m.get("bold") else None
    m["value_hit"] = mk.won(m["value"]["key"], hs, as_) if m.get("value") else None
    bold = m.get("bold") or {}
    ds = add_result(m, f"{hs}:{as_}", "football")
    verdicts = [(f"Основной: {m['main']['label']}", m["main_hit"])]
    if bold:
        verdicts.append((f"Смелый: {bold['label']}", m["bold_hit"]))
    if m.get("value"):
        verdicts.append((f"Value: {m['value']['label']}", m["value_hit"]))
    png = card.result_card(texts.league_plain(m["div"]), m["home"], m["away"], hs, as_, verdicts, BRAND)
    post(png, texts.result(m, s, hs, as_, ds) + pro.clv_line(m), reply_to=m["msg_id"])
    m["status"] = "done"
    print(f"  итог: {m['home']['ru']} {hs}:{as_} {m['away']['ru']} → {'✅' if m['main_hit'] else '❌'}")


def main():
    DATA.mkdir(exist_ok=True)
    now = pd.Timestamp.now(tz=MSK)
    state = load_json(STATE, {})
    matches = load_json(MATCHES, {})
    today = str(now.date())

    daily = state.get("learned") != today
    if daily:
        print("Переобучаюсь на свежих результатах...")
        learn(state, now)
        state["learned"] = today
    w = state.get("weights", {"1X2": 0.0, "OU25": 0.0})

    utc = now.tz_convert("UTC")
    days = [(utc + pd.Timedelta(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
    events = scoreboard({c: ALL[c][3] for c in REVIEW_LEAGUES}, days)
    events = [e for e in events if "POSTPONED" not in e["status"] and "CANCELED" not in e["status"]]
    pros = cup_teams(state, daily)
    events = [e for e in events if professional(e, pros)]
    # русские названия только для матчей ближайших суток — начиная с самых близких по времени
    for e in sorted(events, key=lambda e: abs(pd.Timestamp(e["kickoff"]) - now)):
        if abs(pd.Timestamp(e["kickoff"]) - now) <= pd.Timedelta(hours=30):
            nat = e["div"] in NATIONAL
            e["home"]["ru"] = names.team(e["home"]["name"], nat)
            e["away"]["ru"] = names.team(e["away"]["name"], nat)
    events = [e for e in events if "ru" in e["home"]]
    try:
        other = sports.fetch(now)
        sports.ru_names(other, now)
    except Exception as e:
        print(f"  ! хоккей/баскетбол/теннис недоступны: {e}")
        other = []
    print(f"Матчей в окне: футбол {len(events)}, другие виды спорта {len(other)}")

    if state.get("schedule_day") != today and now.hour >= MORNING_HOUR:
        morning(state, events, other, now)
        state["schedule_day"] = today
    content.run(state, events, other, read_results(), now, BRAND)  # тематический пост раз в 3 часа

    cache = {}

    def fx_loader():
        if "fx" not in cache:
            try:
                cache["fx"] = load_fixtures()
            except Exception as e:
                print(f"  ! football-data недоступен: {e}")
                cache["fx"] = None
        return cache["fx"]

    def hist_loader():
        if "hist" not in cache:
            cache["hist"] = load_history(refresh_current=False, leagues=HIST_LEAGUES)
        return cache["hist"]

    # публикуем в последний запуск, который успевает до «за час»: обзор выходит за 60–80 минут
    lead = pd.Timedelta(minutes=60 + gap_minutes(now))
    calib = mk.calibration(read_results())  # чему бот научился на своих прошлых прогнозах
    for ev in sorted(events, key=lambda e: e["kickoff"]):
        kick = pd.Timestamp(ev["kickoff"])
        if ev["state"] == "pre" and ev["id"] not in matches and now < kick <= now + lead:
            try:
                m = review(ev, w, fx_loader, hist_loader, calib, state)
            except Exception as e:  # один сломанный матч не должен ронять весь запуск
                print(f"  ! обзор не удался {ev['id']}: {e}")
                continue
            matches[ev["id"]] = m or {"status": "skipped", "kickoff": ev["kickoff"]}
            save_json(MATCHES, matches)

    by_id = {e["id"]: e for e in events}
    for mid, m in matches.items():
        capture_close(m, by_id.get(mid), now)
    for mid, m in matches.items():
        ev = by_id.get(mid)
        if m.get("status") == "reviewed" and ev and ev["completed"] and str(ev["home"]["score"]).isdigit():
            try:
                settle(m, ev)
            except Exception as e:
                print(f"  ! итог не удался {mid}: {e}")
            save_json(MATCHES, matches)

    other_sports(state, other, now, calib, daily)
    content.settle_express(state, finished_scores(events, other))
    try:
        content.settle_poll(state, finished_scores(events, other), matches, BRAND)
    except Exception as e:
        print(f"  ! бот против подписчиков не удался: {e}")
    try:
        pro.post_streak(state, read_results(), BRAND)  # «🔥 N заходов подряд!»
    except Exception as e:
        print(f"  ! пост про серию не удался: {e}")

    # live: «матч начался» и голы — ответом к посту с прогнозом на этот матч
    reviews = {f"{m['div']}|{k}": {"msg": m["msg_id"], "tip": m.get("main")}
               for k, m in matches.items() if m.get("msg_id") and m.get("div")}
    reviews.update({k: {"msg": m["msg_id"], "tip": m.get("main")} for k, m in load_json(OTHER, {}).items() if m.get("msg_id")})
    live_store = load_json(LIVE, {})
    try:
        live.run(live_store, events + [e for e in other if e["sport"] != "tennis"], reviews, BRAND)
    except Exception as e:
        print(f"  ! live не удался: {e}")
    save_json(LIVE, live.cleanup(live_store, now))

    # разовая переотправка постов по запросу (data/repost.json) — выполняется один раз на каждый id
    req = load_json(REPOST, {})
    if req.get("id") and state.get("repost_done") != req["id"]:
        state["repost_done"] = req["id"]  # отмечаем сразу — чтобы при ошибке не постить по кругу
        for item in req.get("items", []):
            try:
                if item == "value":
                    pro.post_value(fx_loader(), events, now, BRAND)
                elif item == "streak":
                    pro.post_streak(state, read_results(), BRAND, force=True)
                elif item == "express":
                    content.repost_express(state, events, other, now, BRAND)
                print(f"Переотправка: {item}")
            except Exception as e:
                print(f"  ! переотправка {item} не удалась: {e}")

    if now.hour == VALUE_HOUR and state.get("value_day") != today:  # 💎 value дня
        state["value_day"] = today
        try:
            pro.post_value(fx_loader(), events, now, BRAND)
        except Exception as e:
            print(f"  ! value дня не удался: {e}")
    site_res = read_results()
    # публичная страница со статистикой — после каждого нового результата (и хотя бы раз в час)
    stamp = f"{len(site_res)}|{now:%Y-%m-%d %H}"
    if state.get("site_stamp") != stamp or not site.OUT.exists():
        state["site_stamp"] = stamp
        try:
            site.build(site_res, now)
        except Exception as e:
            print(f"  ! страница статистики не собралась: {e}")

    for step in (news.run, tables.run):  # новость раз в час и таблица/рейтинг дня
        try:
            step(state, now, BRAND)
        except Exception as e:
            print(f"  ! {step.__module__} не удался: {e}")

    # храним только последние 3 дня, остальное уже в results.csv
    old = now - pd.Timedelta(days=3)
    matches = {k: v for k, v in matches.items() if pd.Timestamp(v["kickoff"]) > old}
    save_json(MATCHES, matches)
    save_json(STATE, state)
    names.save()


if __name__ == "__main__":
    main()
