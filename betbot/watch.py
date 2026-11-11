"""Страница «смотреть онлайн бесплатно» на КАЖДЫЙ матч — под поисковые запросы вида
«Ботсвана U23 — Гвинея U23 смотреть онлайн бесплатно».

Матчи: всё, что показывает наша трансляция (docs/matches.json: футбол, хоккей, баскетбол, теннис) +
весь футбол ESPN на сегодня и завтра (сборные, молодёжные U21/U23, женские, мелкие лиги).
На каждой странице: заголовок и описание с ключевыми словами матча, крупная кнопка трансляции,
время по Москве, турнир, стадион, прогноз бота (если есть), FAQ и разметка для поисковиков
(SportsEvent + BroadcastEvent + FAQPage). Плюс раздел watch/ — «смотреть футбол онлайн сегодня».

Страницы пишутся через pages._write: новые сразу уходят в Яндекс и Bing (IndexNow).
Старше 10 дней — удаляем (и из карты сайта), чтобы репозиторий не разрастался.
"""
from __future__ import annotations

import html as H
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests

from . import names, pages

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "watch"
CACHE = ROOT / "data" / "watch.json"        # id → турнир, путь ESPN, русские названия (чтобы не спрашивать заново)
COUNTRIES = ROOT / "data" / "countries_ru.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/"
NEW_PER_PASS = 30      # сколько новых матчей ESPN разбираем за проход (перевод названий, турнир) — не тормозим бота
KEEP_DAYS = 10
SPORT_RU = {"football": "Футбол", "hockey": "Хоккей", "basketball": "Баскетбол", "tennis": "Теннис"}
SPORT_WORD = {"football": "футбол", "hockey": "хоккей", "basketball": "баскетбол", "tennis": "теннис"}
MSK = "Europe/Moscow"
AGE = re.compile(r"\s+(U-?\d{2}|Women|W|II|B)$")


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _country(name: str, cache: dict) -> str:
    """Страна по-русски в именительном падеже («Ботсвана») — как её пишут в поиске."""
    if name in cache:
        return cache[name]
    ru = ""
    try:
        r = requests.get("https://www.wikidata.org/w/api.php", timeout=15, headers={"User-Agent": "AIStavitBot/1.0 (https://horoooos.github.io/betbot/)"},
                         params={"action": "wbsearchentities", "format": "json", "search": name, "language": "en", "limit": 5}).json()
        for x in r.get("search", []):
            d = (x.get("description") or "").lower()
            if any(w in d for w in ("country", "state in", "island", "territory", "kingdom", "republic", "nation")):
                e = requests.get("https://www.wikidata.org/w/api.php", timeout=15, headers={"User-Agent": "AIStavitBot/1.0"},
                                 params={"action": "wbgetentities", "format": "json", "ids": x["id"], "props": "labels",
                                         "languages": "ru"}).json()
                ru = ((e.get("entities", {}).get(x["id"], {}).get("labels", {}).get("ru") or {}).get("value") or "")
                break
    except Exception:
        return name   # Wikidata не ответила — попробуем в следующий раз
    cache[name] = ru or name
    return cache[name]


def _team_ru(t: dict, countries: dict, women: bool = False) -> str:
    """Русское название: сборные — «Ботсвана U23», клубы — из словаря бота (Wikidata); женские — с пометкой «(ж)»."""
    name = t.get("displayName") or t.get("name") or ""
    age = AGE.search(name)
    base = AGE.sub("", name) if age else name
    suffix = ""
    if age:
        a = age.group(1).replace("-", "")
        suffix = " (ж)" if a in ("Women", "W") else f" {a}"
    if women and "(ж)" not in suffix:
        suffix += " (ж)"
    if "/countries/" in (t.get("logo") or ""):
        return _country(base, countries) + suffix
    ru = names.team(base)
    if not re.search(r"[А-Яа-яЁё]", ru):   # клуба с таким названием нет — возможно, это сборная (India, Maldives)
        c = _country(base, countries)
        if re.search(r"[А-Яа-яЁё]", c):
            ru = c
    return ru + suffix


def _espn_football(now: pd.Timestamp, known: set, cache: dict, countries: dict) -> list[dict]:
    """Весь футбол ESPN на сегодня и завтра (по всем турнирам), кроме матчей, которые уже есть у бота."""
    out, budget = [], NEW_PER_PASS
    for d in (now.tz_convert("UTC"), now.tz_convert("UTC") + pd.Timedelta(days=1)):
        try:
            evs = requests.get(f"{ESPN}soccer/all/scoreboard?dates={d:%Y%m%d}", timeout=30).json().get("events", [])
        except Exception:
            continue
        for e in evs:
            eid = str(e["id"])
            if eid in known or "ncaa" in ((cache.get(eid) or {}).get("slug") or ""):
                continue
            info = cache.get(eid)
            if info is None:
                if budget <= 0:
                    continue
                budget -= 1
                comp = e["competitions"][0]
                teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
                slug, league = "all", ""
                try:   # турнир и его код — из сводки матча (в общем расписании их нет)
                    lg = requests.get(f"{ESPN}soccer/all/summary?event={eid}", timeout=20).json().get("header", {}).get("league", {})
                    slug, league = lg.get("slug") or "all", lg.get("name") or ""
                except Exception:
                    pass
                women = ".w." in f".{slug}." or slug.endswith(".w") or "women" in league.lower() or "femenil" in league.lower()                     or "wsl" in league.lower() or "première ligue" in league.lower()
                info = {"slug": slug, "league": league, "venue": (comp.get("venue") or {}).get("fullName", ""),
                        "home": _team_ru(teams["home"], countries, women), "away": _team_ru(teams["away"], countries, women),
                        "hl": teams["home"].get("logo", ""), "al": teams["away"].get("logo", ""),
                        "kickoff": pd.Timestamp(e["date"]).tz_convert(MSK).isoformat()}
                cache[eid] = info
            if re.search(r"[A-Za-z]{3}", info["home"] + info["away"]) and not re.search(r"[А-Яа-я]", info["home"] + info["away"]):
                continue   # русских названий нет — по-английски наши запросы не ищут
            p = f"soccer/{info['slug']}"
            url = f"live.html?s=soccer&p={quote_plus(p)}&e={eid}&h={quote_plus(info['home'])}&a={quote_plus(info['away'])}"
            out.append({"sport": "football", "id": eid, "league": info["league"] or "Футбол", "kickoff": info["kickoff"],
                        "home": info["home"], "away": info["away"], "hl": info["hl"], "al": info["al"],
                        "venue": info["venue"], "url": url, "tip": "", "bot": None,
                        "pred": predict(e["competitions"][0])})   # прогноз по линии — каждый проход по свежим кэфам
    return out


def predict(comp: dict) -> dict | None:
    """Прогноз по линии букмекера (DraftKings из расписания ESPN) — та же математика, что у бота:
    кэфы → честные шансы → ожидаемые голы → шансы всех рынков → ставка по правилам бота (mk.choose)."""
    from . import espn
    from . import markets as mk
    o = espn._odds(comp)
    if not all(o.get(k) and o[k] > 1.01 for k in ("H", "D", "A")):
        return None
    real = {"H": o["H"], "D": o["D"], "A": o["A"]}
    line = p_over = None
    if o.get("line") and o.get("over") and o.get("under") and o["over"] > 1.01 and o["under"] > 1.01:
        line, p_over = float(o["line"]), float(mk.fair([o["over"], o["under"]])[0])
        tag = {1.5: "15", 2.5: "25", 3.5: "35", 4.5: "45"}.get(line)
        if tag:
            real.update({f"O{tag}": o["over"], f"U{tag}": o["under"]})
    try:
        lh, la = mk.implied_lambdas(mk.fair([o["H"], o["D"], o["A"]]), line, p_over)
        probs = mk.all_markets(lh, la)
    except Exception:
        return None
    keys = [k for k in probs if k != "scores" and not k.startswith("HT_") and 0 < probs[k] < 1]
    main, _ = mk.choose(keys, probs, real, lambda k: probs[k])
    if not main:
        return None
    odds = real.get(main) or mk.MARGIN / probs[main]
    show = [k for k in ("1X", "X2", "O25", "U25", "BTTS_Y", "BTTS_N") if k in probs and k != main][:4]
    return {"label": mk.label(main), "p": round(probs[main], 3), "odds": round(float(odds), 2), "est": main not in real,
            "bar": [round(probs["H"], 3), round(probs["D"], 3), round(probs["A"], 3)], "xg": [round(lh, 2), round(la, 2)],
            "more": [(mk.label(k), round(probs[k], 3)) for k in show], "scores": probs.get("scores", [])[:3]}


def _url(m: dict) -> str:
    ko = pd.Timestamp(m["kickoff"]).tz_convert(MSK)
    return f"watch/{ko:%Y-%m-%d}-{pages.slug(m['home'] + ' ' + m['away'], 60)}-{m['id']}.html"


def _pred_block(pr: dict, hh: str, aa: str, vs: str) -> str:
    """🎯 Прогноз по линии: ставка, шанс и кэф, шансы на исход матча, другие рынки и вероятные счета."""
    pct = lambda v: f"{100 * v:.0f}%"   # noqa: E731
    bar = "".join(f'<div style="width:{100 * v:.1f}%;background:{c};padding:6px 0;text-align:center;font-weight:800;font-size:12px">{pct(v)}</div>'
                  for v, c in zip(pr["bar"], ("#2ecc71", "#6b7799", "#4aa3ff")) if v > 0.04)
    more = "".join(f'<span style="padding:6px 10px;border-radius:10px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);font-size:13px">'
                   f'{H.escape(lb)} <b>{pct(p)}</b></span>' for lb, p in pr["more"])
    scores = " · ".join(f"{s} ({pct(p)})" for s, p in pr["scores"])
    return f"""<h2>🎯 Прогноз на матч {H.escape(vs)}</h2>
<div class="card" style="margin:10px 0">
<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
<div><div class="muted small">СТАВКА ПО РАСЧЁТУ БОТА</div><div style="font-size:22px;font-weight:900">{H.escape(pr['label'])}</div></div>
<div style="text-align:right"><div class="muted small">шанс · кэф</div><div style="font-size:22px;font-weight:900;color:#ffc400">{pct(pr['p'])} · {'≈' if pr['est'] else ''}{pr['odds']:.2f}</div></div></div>
<div style="display:flex;border-radius:12px;overflow:hidden;margin:14px 0 6px">{bar}</div>
<div class="muted small" style="display:flex;justify-content:space-between"><span>{H.escape(hh)}</span><span>ничья</span><span>{H.escape(aa)}</span></div>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">{more}</div>
<p class="muted small" style="margin-top:10px">Ожидаемые голы {pr['xg'][0]:.1f} : {pr['xg'][1]:.1f} · самые вероятные счета: {scores}.
Расчёт по линии букмекеров (DraftKings) математикой бота; кэф «≈» — расчётный. Прогноз — не гарантия. 18+</p></div>"""


def _page(m: dict, pred_url: str | None) -> str:
    ko = pd.Timestamp(m["kickoff"]).tz_convert(MSK)
    sport = m.get("sport", "football")
    hh, aa, lg = m["home"], m["away"], m.get("league") or SPORT_RU.get(sport, "")
    vs = f"{hh} — {aa}"
    day = f"{ko.day} {pages.MONTHS[ko.month - 1]}"
    pr = m.get("pred")
    pct = lambda v: f"{100 * v:.0f}%"   # noqa: E731
    if pr:   # есть линия — страница и под «прогноз на матч», и под «смотреть онлайн»
        title = f"{vs}: прогноз на матч и смотреть онлайн бесплатно {ko:%d.%m.%Y}"
        desc = (f"Прогноз на матч {vs} {day}: {pr['label']} — шанс {pct(pr['p'])}, кэф {'≈' if pr['est'] else ''}{pr['odds']:.2f}. "
                f"Смотреть онлайн бесплатно в {ko:%H:%M} МСК, {lg}. Шансы на победу, тоталы, счёт и прямая трансляция.")
    else:
        title = f"{vs} смотреть онлайн бесплатно {ko:%d.%m.%Y} — прямая трансляция матча"
        desc = (f"{vs}: смотреть онлайн бесплатно, {day} в {ko:%H:%M} МСК. {lg}. Прямая трансляция матча, счёт в реальном "
                f"времени, голы, составы, статистика и прогноз на матч {hh} — {aa}.")
    live = pages.SITE + m["url"]
    tip = ""
    if m.get("tip"):
        tip = (f'<div class="card" style="margin:14px 0"><b>🎯 Прогноз бота на матч {H.escape(vs)}:</b> {H.escape(m["tip"])}'
               + (f' · <a href="../{pred_url}">полный разбор и шансы →</a>' if pred_url else "") + "</div>")
    logo = lambda u: f'<img src="{H.escape(u)}" alt="" width="64" height="64" loading="lazy" style="object-fit:contain">' if u else ""  # noqa: E731
    faq = [(f"Где смотреть матч {vs} онлайн бесплатно?",
            f"Матч {vs} можно смотреть онлайн бесплатно на сайте АИ СТАВИТ: живой счёт, голы и события матча в реальном времени, "
            f"3D-трансляция, составы и статистика. Нажмите «Смотреть онлайн» на этой странице."),
           (f"Во сколько начинается матч {vs}?", f"Матч {vs} начнётся {day} {ko.year} года в {ko:%H:%M} по московскому времени. Турнир: {lg}."),
           (f"Какой прогноз на матч {vs}?",
            f"Прогноз бота: {m['tip']}." if m.get("tip") else
            f"Расчёт бота по линии букмекеров: {pr['label']} — шанс {pct(pr['p'])}, кэф {'≈' if pr['est'] else ''}{pr['odds']:.2f}. "
            f"Шансы: победа {hh} {pct(pr['bar'][0])}, ничья {pct(pr['bar'][1])}, победа {aa} {pct(pr['bar'][2])}." if pr else
            f"Прогноз на матч {vs} публикуем в Telegram-канале @aistavvit примерно за час до начала, если по матчу есть линия.")]
    ld = [{"@context": "https://schema.org", "@type": "SportsEvent", "name": vs, "startDate": ko.isoformat(),
           "eventStatus": "https://schema.org/EventScheduled", "sport": SPORT_RU.get(sport, ""),
           "eventAttendanceMode": "https://schema.org/MixedEventAttendanceMode",
           "location": {"@type": "Place", "name": m.get("venue") or lg},
           "homeTeam": {"@type": "SportsTeam", "name": hh}, "awayTeam": {"@type": "SportsTeam", "name": aa},
           "description": desc, "url": pages.SITE + _url(m), "organizer": {"@type": "Organization", "name": lg}},
          {"@context": "https://schema.org", "@type": "BroadcastEvent", "name": f"{vs} — прямая трансляция",
           "isLiveBroadcast": True, "startDate": ko.isoformat(), "url": live, "inLanguage": "ru",
           "publishedOn": {"@type": "BroadcastService", "name": "АИ СТАВИТ", "url": pages.SITE},
           "broadcastOfEvent": {"@type": "SportsEvent", "name": vs, "startDate": ko.isoformat()}},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Смотреть онлайн", "watch/"), (vs, None)])
    body = f"""{crumbs}
<article class="post">
<h1>{H.escape(vs)}: {"прогноз и " if pr else ""}смотреть онлайн бесплатно</h1>
<p class="muted">{H.escape(lg)} · {day} {ko.year}, {ko:%H:%M} МСК{(' · ' + H.escape(m['venue'])) if m.get('venue') else ''}</p>
<div class="card" style="display:flex;align-items:center;justify-content:space-around;gap:12px;text-align:center;margin:14px 0">
<div>{logo(m.get('hl'))}<br><b>{H.escape(hh)}</b></div><div style="font-size:22px;font-weight:900">{ko:%H:%M}</div><div>{logo(m.get('al'))}<br><b>{H.escape(aa)}</b></div></div>
<a class="btn gold" href="../{H.escape(m['url'])}" style="display:block;text-align:center;font-size:18px;padding:16px">▶ Смотреть {H.escape(vs)} онлайн</a>
{tip}{_pred_block(pr, hh, aa, vs) if pr and not m.get("tip") else ""}
<h2>Прямая трансляция {H.escape(vs)}</h2>
<p>Трансляция матча {H.escape(vs)} ({H.escape(lg)}) начнётся {day} в {ko:%H:%M} по Москве. На странице трансляции — счёт онлайн,
голы и важные моменты в реальном времени, 3D-поле с ходом игры, составы команд, статистика и чат болельщиков. Смотреть
матч {H.escape(hh)} — {H.escape(aa)} онлайн можно бесплатно и без регистрации, с телефона и компьютера.</p>
<h2>Вопросы о матче</h2>
{''.join(f'<h3>{H.escape(q)}</h3><p>{H.escape(a)}</p>' for q, a in faq)}
<p class="muted">Ещё: <a href="./">все матчи онлайн сегодня</a> · <a href="../predictions/">прогнозы на матчи</a> · <a href="https://t.me/aistavvit">Telegram-канал @aistavvit</a></p>
</article>"""
    return pages.page("../", title, desc, pages.SITE + _url(m), body, "live", m.get("hl") or None, ld + [bc], "website")


def _index(items: list[dict], now: pd.Timestamp) -> str:
    rows = "".join(
        f'<a class="card" href="../{_url(m)}" style="display:flex;justify-content:space-between;gap:10px;text-decoration:none;color:inherit;margin:6px 0">'
        f'<span><b>{H.escape(m["home"])} — {H.escape(m["away"])}</b><br><small class="muted">{H.escape(m.get("league") or "")}</small></span>'
        f'<span style="white-space:nowrap">{pd.Timestamp(m["kickoff"]).tz_convert(MSK):%d.%m %H:%M}</span></a>'
        for m in items)
    title = "Смотреть футбол онлайн бесплатно сегодня — прямые трансляции матчей"
    desc = (f"Прямые трансляции матчей сегодня и завтра: футбол, хоккей, баскетбол, теннис. Смотреть онлайн бесплатно — "
            f"{len(items)} матчей, счёт в реальном времени, составы и прогнозы.")
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Смотреть онлайн", None)])
    body = f"""{crumbs}<h1>Смотреть матчи онлайн бесплатно</h1>
<p class="muted">Все трансляции на сегодня и завтра — нажмите на матч. Обновлено {now.tz_convert(MSK):%d.%m.%Y %H:%M} МСК.</p>{rows}"""
    return pages.page("../", title, desc, pages.SITE + "watch/", body, "live", None, [bc])


def build(now: pd.Timestamp, preds: dict | None = None) -> list[str]:
    """Пишет страницы watch/*.html и watch/index.html; возвращает адреса для карты сайта."""
    preds = preds or {}
    try:
        ours = json.loads((DOCS / "matches.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ours = []
    cache, countries = _load(CACHE), _load(COUNTRIES)
    items = [m for m in ours if m.get("home") and m.get("away") and m.get("url")]
    items += _espn_football(now, {str(m["id"]) for m in items}, cache, countries)
    names.save()   # новые русские названия команд — в словарь бота
    OUT.mkdir(parents=True, exist_ok=True)
    keep = set()
    for m in items:
        u = _url(m)
        keep.add(u)
        pages._write(DOCS / u, _page(m, preds.get(str(m["id"]))))
    # старые страницы удаляем — и из карты сайта тоже
    old = now - pd.Timedelta(days=KEEP_DAYS)
    for f in OUT.glob("*.html"):
        if f.name == "index.html":
            continue
        try:
            if pd.Timestamp(f.name[:10]).tz_localize(MSK) < old:
                f.unlink()
        except ValueError:
            pass
    upcoming = sorted([m for m in items if pd.Timestamp(m["kickoff"]) > now - pd.Timedelta(hours=3)], key=lambda m: m["kickoff"])
    # прогнозы по линии на ближайшие матчи — для подборки «прогнозы на футбол сегодня» (betbot/hubs.py)
    preds = [{"url": _url(m), "home": m["home"], "away": m["away"], "league": m.get("league") or "", "kickoff": m["kickoff"],
              "label": m["pred"]["label"], "p": m["pred"]["p"], "odds": m["pred"]["odds"], "est": m["pred"]["est"]}
             for m in upcoming if m.get("pred") and pd.Timestamp(m["kickoff"]) > now]
    (ROOT / "data" / "watch_preds.json").write_text(json.dumps(preds, ensure_ascii=False), encoding="utf-8")
    pages._write(OUT / "index.html", _index(upcoming, now))
    cache = {k: v for k, v in cache.items() if pd.Timestamp(v["kickoff"]) > old}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    COUNTRIES.write_text(json.dumps(countries, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return ["watch/"] + sorted(f"watch/{f.name}" for f in OUT.glob("*.html") if f.name != "index.html")
