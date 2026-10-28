"""Полный разбор матча для хоккея, баскетбола, тенниса и киберспорта — ответом к посту с картинкой.

  хоккей/баскетбол — данные ESPN: таблица, форма, личные встречи, травмы, лидеры команд;
  теннис/киберспорт — история матчей бота за год: рейтинг, баланс, форма, личные встречи.
"""
from html import escape

import pandas as pd

from . import names

FORM = {"W": "🟢", "D": "⚪", "L": "🔴"}
INJURY = {"Out": "не сыграет", "Day-To-Day": "под вопросом", "Injured Reserve": "в лазарете",
          "Questionable": "под вопросом", "Doubtful": "вряд ли сыграет", "Suspension": "дисквалификация"}
LEADER = {"Goals": "голы", "Assists": "передачи", "Points": "очки", "Rebounds": "подборы",
          "Plus/Minus": "плюс/минус", "Saves": "сейвы", "Wins": "победы", "Steals": "перехваты",
          "Blocks": "блок-шоты", "Rating": "рейтинг"}
FOOTER = "<i>⚠️ 18+. Прогноз — не гарантия. Ставьте только то, что не жалко потерять.</i>"


def _pct(p: float) -> str:
    return f"{100 * p:.0f}%"


def _markets(m: dict) -> str:
    rows = [(m["labels"][k], m["probs"][k]) for k in m["probs"]]
    width = min(max(len(r[0]) for r in rows), 30)
    return "📋 <b>Вероятности по всем рынкам</b>\n<code>" + "\n".join(
        f"{escape(n[:30].ljust(width))} {_pct(p):>4}" for n, p in rows[:16]) + "</code>"


def _tip(t: dict) -> str:
    return f"{escape(t['label'])} — {_pct(t['p'])} · кэф {'≈' if t.get('est') else ''}{t['odds']:.2f}"


def _verdict(m: dict, why: list[str]) -> str:
    why.append(f"Итог: <b>{_tip(m['main'])}</b>." + (f" Для риска — {_tip(m['bold'])}." if m.get("bold") else ""))
    return "🧠 <b>Вывод</b>\n" + "\n".join(f"• {w}" for w in why)


# ── хоккей и баскетбол ──────────────────────────────────────────────────────

def _standing(team: dict, row: dict | None, hockey: bool) -> str:
    if not row:
        return f"{escape(team['ru'])} — нет данных"
    r = row.get("raw") or {}
    streak = f", серия {r['STRK']}" if r.get("STRK") else ""
    if hockey:
        goals = f", шайбы {r['GF']}:{r['GA']}" if r.get("GF") and r.get("GA") else ""
        return (f"{escape(team['ru'])} — {r.get('W', '?')}-{r.get('L', '?')}-{r.get('OTL', '0')} (В-П-ПО), "
                f"<b>{r.get('PTS', '?')}</b> очк.{goals}{streak}")
    ppg = f", в среднем {r['PPG']} очк. за игру" if r.get("PPG") else ""
    return f"{escape(team['ru'])} — {r.get('W', '?')}-{r.get('L', '?')} ({r.get('PCT', '?')} побед){ppg}{streak}"


def _wins(n: int) -> str:
    return f"{n} {'победа' if n % 10 == 1 and n % 100 != 11 else 'победы' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'побед'}"


ROUNDS = {"Round 1": "1-й круг", "Round 2": "2-й круг", "Round 3": "3-й круг", "Round 4": "4-й круг",
          "Round of 128": "1/64 финала", "Round of 64": "1/32 финала", "Round of 32": "1/16 финала",
          "Round of 16": "1/8 финала", "Quarterfinal": "Четвертьфинал", "Quarterfinals": "Четвертьфинал",
          "Semifinal": "Полуфинал", "Semifinals": "Полуфинал", "Final": "Финал", "Round Robin": "Групповой этап"}


def _form(team: dict, games: list[dict]) -> tuple[str, int]:
    if not games:
        return f"{escape(team['ru'])}: нет данных", 0
    wins = sum(1 for g in games if g["res"] == "W")
    icons = "".join(FORM.get(g["res"], "▫️") for g in games)
    gf, ga = sum(g["gf"] for g in games), sum(g["ga"] for g in games)
    return f"{escape(team['ru'])}: {icons}  {_wins(wins)} из {len(games)}, счёт {gf}:{ga}", wins


def team_review(m: dict, s: dict) -> str:
    hockey = m["sport"] == "hockey"
    home, away = m["home"], m["away"]
    hid, aid = str(home["id"]), str(away["id"])
    parts = [f"🔎 <b>ПОЛНЫЙ РАЗБОР: {escape(home['ru'])} — {escape(away['ru'])}</b>"]
    table = s.get("table") or {}
    if table.get(hid) or table.get(aid):
        parts.append("📊 <b>Положение в лиге</b>\n" + _standing(home, table.get(hid), hockey) + "\n"
                     + _standing(away, table.get(aid), hockey))
    fh, wh = _form(home, (s.get("last5") or {}).get(hid, []))
    fa, wa = _form(away, (s.get("last5") or {}).get(aid, []))
    parts.append("📈 <b>Форма: 5 последних игр</b>\n" + fh + "\n" + fa)
    h2h = s.get("h2h") or []
    if h2h:
        lines, wins_h = [], 0
        for g in h2h[:5]:
            try:
                hs, as_ = int(g["hs"]), int(g["as"])
            except (TypeError, ValueError):
                continue
            first = home["ru"] if g["home_id"] == hid else away["ru"]
            second = away["ru"] if g["home_id"] == hid else home["ru"]
            wins_h += (hs > as_) == (g["home_id"] == hid)
            day = f"{pd.Timestamp(g['date']):%d.%m.%Y} " if g.get("date") else ""
            lines.append(f"{day}{escape(first)} {hs}:{as_} {escape(second)}")
        parts.append(f"🤝 <b>Личные встречи</b> ({escape(home['ru'])} выиграл {wins_h} из {len(lines)})\n" + "\n".join(lines))
    inj = s.get("injuries") or {}
    if inj.get(hid) or inj.get(aid):
        lines = ["🚑 <b>Травмы и потери</b>"]
        for team, tid in ((home, hid), (away, aid)):
            if inj.get(tid):
                who = ", ".join(f"{names.player(n)} ({INJURY.get(st, st.lower())})" for n, st in inj[tid][:4])
                lines.append(f"<b>{escape(team['ru'])}:</b> {escape(who)}")
        parts.append("\n".join(lines))
    lead = s.get("leaders") or {}
    if lead.get(hid) or lead.get(aid):
        lines = ["⭐ <b>Лидеры команд</b>"]
        for team, tid in ((home, hid), (away, aid)):
            if lead.get(tid):
                items = "; ".join(f"{LEADER.get(c, c.lower())}: {names.player(p)} ({v})" for c, p, v in lead[tid] if p)
                lines.append(f"<b>{escape(team['ru'])}:</b> {escape(items)}")
        parts.append("\n".join(lines))
    parts.append(f"🧮 <b>Модель</b>: {escape(m['center'])}")
    parts.append(_markets(m))

    p_home = m["bar"][0]
    fav, fp = (home["ru"], p_home) if p_home >= m["bar"][2] else (away["ru"], m["bar"][2])
    why = [f"{escape(fav)} — {'явный ' if fp >= 0.62 else ''}фаворит ({_pct(fp)} на победу)."]
    if wh - wa >= 2:
        why.append(f"{escape(home['ru'])} в лучшей форме: {_wins(wh)} из 5 против {wa}.")
    elif wa - wh >= 2:
        why.append(f"{escape(away['ru'])} в лучшей форме: {_wins(wa)} из 5 против {wh}.")
    nh, na = len(inj.get(hid, [])), len(inj.get(aid, []))
    if abs(nh - na) >= 2:
        why.append(f"Больше потерь у команды {escape(home['ru'] if nh > na else away['ru'])} ({max(nh, na)} игрока).")
    model = m.get("model") or {}
    if hockey and model.get("lh"):
        why.append(f"Ожидается около {model['lh'] + model['la']:.1f} шайб на двоих.")
    if not hockey and model.get("T"):
        why.append(f"Букмекеры ждут около {model['T']:.0f} очков на двоих.")
    parts.append(_verdict(m, why))
    parts.append(FOOTER)
    return "\n\n".join(parts)


# ── теннис и киберспорт ─────────────────────────────────────────────────────

def _player_games(hist: list[dict], pid: str) -> list[dict]:
    out = []
    for g in hist:
        for me, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
            if me["id"] == pid:
                score = f"{sum(me.get('set_won') or [])}:{sum(opp.get('set_won') or [])}" if "set_won" in me \
                    else f"{me.get('score') or 0}:{opp.get('score') or 0}"
                out.append({"won": bool(me.get("winner")), "opp": opp["name"], "opp_id": opp["id"],
                            "score": score, "date": g["kickoff"][:10], "tour": g.get("tournament", "")})
    return out


def history_review(m: dict, hist: list[dict], ratings: dict) -> str:
    tennis = m["sport"] == "tennis"
    home, away = m["home"], m["away"]
    show = names.player if tennis else (lambda n: n)
    parts = [f"🔎 <b>ПОЛНЫЙ РАЗБОР: {escape(home['ru'])} — {escape(away['ru'])}</b>"]
    info = [f"🏆 {escape(m.get('tournament', ''))}"]
    if tennis and m.get("round"):
        info.append(f"Раунд: {escape(ROUNDS.get(m['round'], m['round']))}")
    if not tennis:
        info.append(f"Формат: BO{m.get('bo', 1)} · уровень турнира: {str(m.get('tier', '')).upper() or '—'}")
    parts.append("\n".join(info))

    active = sorted((v[0] for k, v in ratings.items() if v[1] >= 10), reverse=True)
    lines = ["📊 <b>Рейтинг и баланс за год</b>"]
    stats = {}
    for p in (home, away):
        games = _player_games(hist, p["id"])
        r = ratings.get(p["id"], (1500, 0))
        place = 1 + sum(1 for x in active if x > r[0])
        w = sum(g["won"] for g in games)
        stats[p["id"]] = {"games": games, "w": w, "n": len(games), "elo": r[0],
                          "last10": sum(g["won"] for g in games[-10:]), "n10": len(games[-10:])}
        share = f"{_pct(w / len(games))}" if games else "—"
        lines.append(f"{escape(p['ru'])}: Эло <b>{r[0]:.0f}</b> (~{place}-е место), {w}-{len(games) - w} за год ({share} побед)")
    parts.append("\n".join(lines))

    form = ["📈 <b>Форма: 5 последних матчей</b>"]
    for p in (home, away):
        last = stats[p["id"]]["games"][-5:]
        if not last:
            form.append(f"{escape(p['ru'])}: нет данных")
            continue
        icons = "".join("🟢" if g["won"] else "🔴" for g in last)
        tail = ", ".join(f"{'✓' if g['won'] else '✗'} {escape(show(g['opp']).split()[-1])} {g['score']}" for g in last[-3:])
        form.append(f"{escape(p['ru'])}: {icons}  ({tail})")
    parts.append("\n".join(form))

    h2h = [g for g in stats[home["id"]]["games"] if g["opp_id"] == away["id"]]
    if h2h:
        wh = sum(g["won"] for g in h2h)
        last = h2h[-1]
        parts.append(f"🤝 <b>Личные встречи</b>: {escape(home['ru'])} {wh} — {len(h2h) - wh} {escape(away['ru'])}\n"
                     f"Последняя: {last['date']}, {'победа' if last['won'] else 'поражение'} {escape(home['ru'])} "
                     f"({last['score']})")
    else:
        parts.append("🤝 <b>Личные встречи</b>: за год не встречались")
    parts.append(f"🧮 <b>Модель</b>: {escape(m['center'])}")
    parts.append(_markets(m))

    sh, sa = stats[home["id"]], stats[away["id"]]
    fav = home if m["bar"][0] >= m["bar"][2] else away
    fp = max(m["bar"][0], m["bar"][2])
    why = [f"{escape(fav['ru'])} — {'явный ' if fp >= 0.65 else ''}фаворит по рейтингу ({_pct(fp)})."]
    if sh["n10"] and sa["n10"] and abs(sh["last10"] / sh["n10"] - sa["last10"] / sa["n10"]) >= 0.25:
        better = home if sh["last10"] / sh["n10"] > sa["last10"] / sa["n10"] else away
        b = sh if better is home else sa
        why.append(f"{escape(better['ru'])} в лучшей форме: {_wins(b['last10'])} в последних {b['n10']} матчах.")
    if h2h and len(h2h) >= 2:
        wh = sum(g["won"] for g in h2h)
        if wh != len(h2h) - wh:
            leader = home if wh > len(h2h) - wh else away
            why.append(f"В личных встречах преимущество у {escape(leader['ru'])}.")
    if min(sh["n"], sa["n"]) < 15:
        why.append("У одного из соперников мало матчей в истории — прогноз менее надёжен.")
    parts.append(_verdict(m, why))
    parts.append("<i>Вероятности — по рейтингу Эло бота (история матчей за год), коэффициентов по этому виду "
                 f"спорта в бесплатных источниках нет.</i>\n{FOOTER}")
    return "\n\n".join(parts)
