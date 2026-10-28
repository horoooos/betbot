"""Все тексты постов на русском (HTML-разметка Telegram)."""
from html import escape

import pandas as pd

from . import names
from .leagues import ALL, ORDER, title

DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
LINE = "━━━━━━━━━━━━━━"
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"
FORM = {"W": "🟢", "D": "⚪", "L": "🔴"}


def pct(p: float) -> str:
    return f"{100 * p:.0f}%"


def ts(m: dict) -> pd.Timestamp:
    return pd.Timestamp(m["kickoff"])


def date_ru(t: pd.Timestamp) -> str:
    return f"{t.day} {MONTHS[t.month - 1]}"


def when(t: pd.Timestamp) -> str:
    return f"{t:%H:%M} · {DAYS_SHORT[t.weekday()]}, {date_ru(t)} · МСК"


def league_plain(code: str) -> str:
    _, country, league, _ = ALL[code]
    return f"{country} · {league}"


def tip_line(t: dict) -> str:
    if not t:
        return ""
    approx = "≈" if t.get("est") else ""
    return f"{escape(t['label'])} — {pct(t['p'])} · кэф {approx}{t['odds']:.2f}"


# ── утреннее расписание ─────────────────────────────────────────────────────

def schedule(matches: list[dict], day: pd.Timestamp, extra: str = "") -> str:
    """Расписание дня: футбол по лигам, затем хоккей/баскетбол/теннис (extra)."""
    head = (f"📅 <b>МАТЧИ ДНЯ · {DAYS[day.weekday()].upper()}, {date_ru(day).upper()}</b>\n"
            f"Футбольных матчей: <b>{len(matches)}</b>. Прогноз на каждый матч — примерно за час до начала 👇\n{LINE}")
    blocks = [head]
    by_league: dict[str, list] = {}
    for m in sorted(matches, key=lambda m: (ORDER.get(m["div"], 999), m["kickoff"])):
        by_league.setdefault(m["div"], []).append(m)
    for code, ms in by_league.items():
        lines = [f"<b>{title(code)}</b>"]
        for m in sorted(ms, key=lambda m: m["kickoff"]):
            fav = ""
            if m.get("fav"):
                fav = f" · <i>фаворит: {escape(m['fav'][0])} {pct(m['fav'][1])}</i>"
            lines.append(f"🕒 {ts(m):%H:%M}  {escape(m['home']['ru'])} — {escape(m['away']['ru'])}{fav}")
        blocks.append("\n".join(lines))
    if extra:
        blocks.append(f"{LINE}\n<b>ДРУГИЕ ВИДЫ СПОРТА</b>")
        blocks.append(extra)
    blocks.append(FOOTER)
    return "\n\n".join(blocks)


# ── обзор перед матчем ──────────────────────────────────────────────────────

def caption(m: dict, venue: str | None) -> str:
    h, a = escape(m["home"]["ru"]), escape(m["away"]["ru"])
    lines = [f"⚽️ <b>{h} — {a}</b>",
             f"🏆 {title(m['div'])}",
             f"⏰ {when(ts(m))}"]
    if venue:
        lines.append(f"🏟 {escape(venue)}")
    lines += ["", f"🎯 <b>Основной прогноз:</b> {tip_line(m['main'])}"]
    if m.get("bold"):
        lines.append(f"🔥 <b>Смелый прогноз:</b> {tip_line(m['bold'])}")
    if m.get("value"):
        v = m["value"]
        lines.append(f"💎 <b>Value:</b> {escape(v['label'])} @ {v['odds']:.2f} (перевес +{100 * v['edge']:.1f}%)")
    lines += ["", "👇 <i>Полный разбор — в ответе к посту</i>"]
    return "\n".join(lines)


def _table_line(team: dict, row: dict | None) -> str:
    if not row or not row.get("rank"):
        return f"{escape(team['ru'])} — нет данных"
    return (f"{escape(team['ru'])} — <b>{row['rank']}-е</b> место из {row['of']}, {row['pts']} очк. "
            f"({row['w']}-{row['d']}-{row['l']}, разница {row['gd']})")


def _form_line(team: dict, games: list[dict]) -> tuple[str, int, float, float]:
    if not games:
        form = team.get("form") or ""
        return f"{escape(team['ru'])}: {''.join(FORM.get(c, '') for c in form) or 'нет данных'}", 0, 0, 0
    gf, ga = sum(g["gf"] for g in games), sum(g["ga"] for g in games)
    pts = sum(3 if g["res"] == "W" else 1 if g["res"] == "D" else 0 for g in games)
    btts = sum(1 for g in games if g["gf"] > 0 and g["ga"] > 0)
    icons = "".join(FORM.get(g["res"], "▫️") for g in games)
    return (f"{escape(team['ru'])}: {icons}  голы {gf}:{ga}, обе забили в {btts} из {len(games)}",
            pts, (gf + ga) / len(games), btts / len(games))


def _h2h(m: dict, s: dict) -> tuple[list[str], float | None]:
    games = s.get("h2h") or []
    if not games:
        return ["Очных встреч в последнее время не было"], None
    hid = str(m["home"]["id"])
    w_h = w_a = dr = goals = 0
    for g in games:
        try:
            hs, as_ = int(g["hs"]), int(g["as"])
        except (TypeError, ValueError):
            continue
        goals += hs + as_
        home_first = g["home_id"] == hid
        mine, theirs = (hs, as_) if home_first else (as_, hs)
        if mine > theirs:
            w_h += 1
        elif mine < theirs:
            w_a += 1
        else:
            dr += 1
    n = w_h + w_a + dr
    if not n:
        return ["Очных встреч в последнее время не было"], None
    last = games[0]
    lh = m["home"]["ru"] if last["home_id"] == hid else m["away"]["ru"]
    la = m["away"]["ru"] if last["home_id"] == hid else m["home"]["ru"]
    day = f"{pd.Timestamp(last['date']):%d.%m.%Y} " if last.get("date") else ""
    return ([f"{escape(m['home']['ru'])} {w_h} — ничьих {dr} — {w_a} {escape(m['away']['ru'])} "
             f"(матчей: {n}, в среднем {goals / n:.1f} гола)",
             f"Последняя: {day}{escape(lh)} {last['hs']}:{last['as']} {escape(la)}"], goals / n)


def _markets_table(m: dict) -> str:
    p = m["probs"]
    h, a = m["home"]["ru"][:12], m["away"]["ru"][:12]
    rows = [
        ("Исход", f"П1 {pct(p['H'])}  Х {pct(p['D'])}  П2 {pct(p['A'])}"),
        ("Двойной шанс", f"1X {pct(p['1X'])}  12 {pct(p['12'])}  X2 {pct(p['X2'])}"),
        ("Обе забьют", f"да {pct(p['BTTS_Y'])}  нет {pct(p['BTTS_N'])}"),
        ("Тотал 1.5", f"Б {pct(p['O15'])}  М {pct(p['U15'])}"),
        ("Тотал 2.5", f"Б {pct(p['O25'])}  М {pct(p['U25'])}"),
        ("Тотал 3.5", f"Б {pct(p['O35'])}  М {pct(p['U35'])}"),
        (f"ИТ1 {h}", f"Б0.5 {pct(p['H_O05'])}  Б1.5 {pct(p['H_O15'])}"),
        (f"ИТ2 {a}", f"Б0.5 {pct(p['A_O05'])}  Б1.5 {pct(p['A_O15'])}"),
        ("Фора −1.5", f"Ф1 {pct(p['H-1.5'])}  Ф2 {pct(p['A-1.5'])}"),
        ("Фора +1.5", f"Ф1 {pct(p['H+1.5'])}  Ф2 {pct(p['A+1.5'])}"),
    ]
    width = max(len(r[0]) for r in rows)
    return "<code>" + "\n".join(f"{escape(n.ljust(width))}  {v}" for n, v in rows) + "</code>"


def review(m: dict, s: dict) -> str:
    home, away = m["home"], m["away"]
    hid, aid = str(home["id"]), str(away["id"])
    p = m["probs"]
    parts = [f"🔎 <b>ПОЛНЫЙ РАЗБОР: {escape(home['ru'])} — {escape(away['ru'])}</b>"]

    t_h, t_a = s["table"].get(hid), s["table"].get(aid)
    if t_h or t_a:
        parts.append("📊 <b>Турнирная таблица</b>\n" + _table_line(home, t_h) + "\n" + _table_line(away, t_a))

    fh, pts_h, goals_h, btts_h = _form_line(home, s["last5"].get(hid, []))
    fa, pts_a, goals_a, btts_a = _form_line(away, s["last5"].get(aid, []))
    parts.append("📈 <b>Форма: 5 последних матчей</b> (все турниры)\n" + fh + "\n" + fa)

    h2h_lines, h2h_goals = _h2h(m, s)
    parts.append("🤝 <b>Личные встречи</b>\n" + "\n".join(h2h_lines))

    lu = s.get("lineups") or {}
    if lu:
        lines = ["👥 <b>Стартовые составы</b>"]
        for team, tid in ((home, hid), (away, aid)):
            if tid in lu:
                players = ", ".join(names.player(x).split()[-1] for x in lu[tid]["starters"])
                schema = f" ({lu[tid]['formation']})" if lu[tid].get("formation") else ""
                lines.append(f"<b>{escape(team['ru'])}{schema}:</b> {escape(players)}")
        parts.append("\n".join(lines))
    else:
        parts.append("👥 <b>Составы</b>: ещё не объявлены")

    sc = ", ".join(f"{s_} ({pct(pr)})" for s_, pr in m["scores"])
    parts.append(f"🧮 <b>Модель</b>\nОжидаемые голы (xG): <b>{m['lam'][0]:.1f} : {m['lam'][1]:.1f}</b>\n"
                 f"Самые вероятные счета: {sc}")
    parts.append("📋 <b>Вероятности по всем рынкам</b>\n" + _markets_table(m))

    # вывод: собираем факторы в связный текст
    why = []
    fav_p, fav_name = max((p["H"], home["ru"]), (p["A"], away["ru"]))
    if fav_p >= 0.6:
        why.append(f"{escape(fav_name)} — явный фаворит ({pct(fav_p)} на победу).")
    elif fav_p >= 0.45:
        why.append(f"Небольшой перевес у команды {escape(fav_name)} ({pct(fav_p)}).")
    else:
        why.append(f"Равный матч: шансы почти поровну, ничья — {pct(p['D'])}.")
    if t_h and t_a and t_h.get("rank") and t_a.get("rank"):
        gap = int(t_a["rank"]) - int(t_h["rank"])
        if abs(gap) >= 5:
            up = home["ru"] if gap > 0 else away["ru"]
            why.append(f"В таблице {escape(up)} выше на {abs(gap)} позиций.")
    if pts_h or pts_a:
        if pts_h - pts_a >= 5:
            why.append(f"{escape(home['ru'])} в лучшей форме: {pts_h} очков из 15 против {pts_a}.")
        elif pts_a - pts_h >= 5:
            why.append(f"{escape(away['ru'])} в лучшей форме: {pts_a} очков из 15 против {pts_h}.")
        else:
            why.append(f"По форме команды близки ({pts_h} и {pts_a} очков из 15).")
    avg_goals = (goals_h + goals_a) / 2 if (goals_h or goals_a) else None
    if avg_goals is not None:
        if avg_goals >= 3:
            why.append(f"В матчах обеих команд много голов: в среднем {avg_goals:.1f} за игру.")
        elif avg_goals <= 2:
            why.append(f"Команды играют скупо: в среднем {avg_goals:.1f} гола за игру.")
    if btts_h >= 0.6 and btts_a >= 0.6:
        why.append("Обе команды регулярно и забивают, и пропускают.")
    if h2h_goals is not None and h2h_goals >= 3:
        why.append(f"Очные встречи обычно результативные ({h2h_goals:.1f} гола в среднем).")
    why.append(f"Итог: <b>{tip_line(m['main'])}</b>.")
    parts.append("🧠 <b>Вывод</b>\n" + "\n".join(f"• {w}" for w in why))
    src = m.get("odds_src", "")
    parts.append(f"<i>Вероятности: коэффициенты ({src}) без маржи букмекера + модель голов. "
                 f"Доверие модели сейчас {pct(m.get('model_w', 0))}. Выбор прогноза учитывает статистику "
                 f"бота: какие типы ставок у него реально заходят.</i>\n{FOOTER}")
    return "\n\n".join(parts)


# ── итог матча ──────────────────────────────────────────────────────────────

def _mark(hit: bool | None) -> str:
    return "✅ <b>ЗАШЁЛ</b>" if hit else "❌ мимо"


def result(m: dict, s: dict, hs: int, as_: int, day_stats: dict) -> str:
    home, away = m["home"], m["away"]
    hid = str(home["id"])
    lines = [f"🏁 <b>ФИНАЛ: {escape(home['ru'])} {hs}:{as_} {escape(away['ru'])}</b>"]
    if s.get("goals"):
        g = []
        for x in s["goals"]:
            team = home["ru"] if x["team"] == hid else away["ru"]
            tag = " (пен.)" if x["pen"] else " (автогол)" if x["own"] else ""
            g.append(f"{x['min']} {escape(names.player(x['player']))}{tag} — {escape(team)}")
        lines.append("⚽️ " + "\n⚽️ ".join(g))
    for x in s.get("reds") or []:
        team = home["ru"] if x["team"] == hid else away["ru"]
        lines.append(f"🟥 {x['min']} {escape(names.player(x['player']))} — {escape(team)}")
    st = s.get("stats") or {}
    sh, sa = st.get(hid, {}), st.get(str(away["id"]), {})
    if sh and sa:
        def pair(k, suffix=""):
            return f"{sh.get(k, '—')}{suffix}–{sa.get(k, '—')}{suffix}"
        lines.append(f"📊 Удары {pair('totalShots')} (в створ {pair('shotsOnTarget')}) · "
                     f"владение {pair('possessionPct', '%')} · угловые {pair('wonCorners')}")
    lines.append("")
    lines.append(f"🎯 Основной: {escape(m['main']['label'])} — {_mark(m['main_hit'])}")
    if m.get("bold"):
        lines.append(f"🔥 Смелый: {escape(m['bold']['label'])} — {_mark(m['bold_hit'])}")
    if m.get("value"):
        lines.append(f"💎 Value: {escape(m['value']['label'])} @ {m['value']['odds']:.2f} — {_mark(m['value_hit'])}")
    if day_stats["n"]:
        lines.append(f"\n📅 Сегодня: основной {day_stats['main']}/{day_stats['n']} ({pct(day_stats['main'] / day_stats['n'])})"
                     + (f" · смелый {day_stats['bold']}/{day_stats['nb']}" if day_stats["nb"] else ""))
    return "\n".join(lines)


# ── статистика ──────────────────────────────────────────────────────────────

def _hits(col: pd.Series) -> pd.Series:
    return col.astype(str).str.lower().isin(["true", "1", "1.0"])


def numbers(df: pd.DataFrame) -> tuple[int, int, float | None]:
    """Угадано, всего и ROI основного прогноза за период."""
    if df.empty:
        return 0, 0, None
    hit = _hits(df["main_hit"])
    profit = (hit * (df["main_odds"].astype(float) - 1) - (~hit)).sum()
    return int(hit.sum()), len(df), float(100 * profit / len(df))


def periods(res: pd.DataFrame, today: pd.Timestamp) -> list[tuple[str, pd.DataFrame]]:
    d = pd.to_datetime(res["date"]).dt.date if len(res) else pd.Series(dtype=object)
    yday = today - pd.Timedelta(days=1)
    return [(f"Вчера, {date_ru(yday)}", res[d == yday.date()]),
            ("За 7 дней", res[d > (today - pd.Timedelta(days=8)).date()]),
            ("За 30 дней", res[d > (today - pd.Timedelta(days=31)).date()]),
            ("За всё время", res)]


def _period(df: pd.DataFrame, name: str) -> str:
    hits, n, roi = numbers(df)
    if not n:
        return f"<b>{name}:</b> матчей не было"
    b = df.dropna(subset=["bold_hit"])
    bold = f" · смелый {int(_hits(b['bold_hit']).sum())}/{len(b)}" if len(b) else ""
    return f"<b>{name}:</b> основной {hits}/{n} (<b>{pct(hits / n)}</b>){bold} · ROI ≈ <b>{roi:+.1f}%</b>"


def stats(res: pd.DataFrame, today: pd.Timestamp, calib: dict | None = None) -> str:
    from .markets import label  # здесь, чтобы не тянуть scipy ради одного текста
    lines = [f"📊 <b>СТАТИСТИКА БОТА</b>\n{LINE}"] + [_period(df, name) for name, df in periods(res, today)]
    if "sport" in res and res["sport"].nunique() > 1:
        from .sports import EMOJI, SPORT_RU
        week = periods(res, today)[1][1]
        parts = []
        for sport, g in week.assign(sport=week["sport"].fillna("football")).groupby("sport"):
            hits, n, _ = numbers(g)
            parts.append(f"{EMOJI.get(sport, '')} {SPORT_RU.get(sport, sport)} {hits}/{n} ({pct(hits / n)})")
        if parts:
            lines.append("🏅 <b>За 7 дней по видам спорта:</b> " + " · ".join(parts))
    learned = sorted(((k, r, n) for k, (r, n) in (calib or {}).items() if n >= 5 and abs(r - 1) >= 0.05),
                     key=lambda x: -abs(x[1] - 1))[:4]
    if learned:
        lines.append("🧠 <b>Чему бот научился на своих прогнозах</b>\n" + "\n".join(
            f"{'📈' if r > 1 else '📉'} {escape(label(k))}: заходит {'чаще' if r > 1 else 'реже'} обещанного "
            f"({r:.2f}×, прогнозов: {n}) — {'выбирает охотнее' if r > 1 else 'выбирает реже'}"
            for k, r, n in learned))
    lines.append("<i>ROI — прибыль на 1 ед. ставки по кэфам из постов (≈ — оценочный кэф)</i>")
    return "\n\n".join(lines)
