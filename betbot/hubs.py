"""Подборки под массовые поисковые запросы: «прогнозы на футбол сегодня», «прогнозы на РПЛ», «экспресс дня»,
«прогнозы на НХЛ / НБА / теннис / киберспорт». Постоянные адреса docs/prognozy/*.html — обновляются при каждой
сборке сайта, поэтому со временем растут в поиске (свежий контент на одном и том же адресе).

На каждой странице: ближайшие прогнозы бота по теме, честный итог за 30 дней, недавние результаты, FAQ
и разметка ItemList/FAQPage для поисковиков.
"""
from __future__ import annotations

import html as H
import json
from pathlib import Path

import pandas as pd

from . import pages

DOCS = Path(__file__).resolve().parent.parent / "docs"
OUT = DOCS / "prognozy"
MSK = "Europe/Moscow"

# slug: (заголовок H1, короткое имя для текста, фильтр матча)
HUBS = {
    "futbol-segodnya": ("Прогнозы на футбол сегодня", "футбол", lambda m: m["sport"] == "football"),
    "rpl": ("Прогнозы на РПЛ", "РПЛ", lambda m: "Россия · Премьер-лига" in (m.get("league") or "")),
    "apl": ("Прогнозы на АПЛ", "АПЛ", lambda m: "Англия · Премьер-лига" in (m.get("league") or "")),
    "liga-chempionov": ("Прогнозы на Лигу чемпионов", "Лигу чемпионов", lambda m: "Лига чемпионов" in (m.get("league") or "")),
    "la-liga": ("Прогнозы на Ла Лигу", "Ла Лигу", lambda m: "Ла Лига" in (m.get("league") or "")),
    "seriya-a": ("Прогнозы на Серию А", "Серию А", lambda m: "Италия · Серия A" in (m.get("league") or "")),
    "bundesliga": ("Прогнозы на Бундеслигу", "Бундеслигу", lambda m: "Германия · Бундеслига" in (m.get("league") or "")),
    "hokkej-nhl": ("Прогнозы на хоккей и НХЛ", "хоккей", lambda m: m["sport"] == "hockey"),
    "nba": ("Прогнозы на НБА", "НБА", lambda m: m["sport"] == "basketball"),
    "tennis": ("Прогнозы на теннис", "теннис", lambda m: m["sport"] == "tennis"),
    "kibersport": ("Прогнозы на киберспорт: CS2 и Dota 2", "киберспорт", lambda m: m["sport"] == "esports"),
}


def _stats(done: list[dict]) -> str:
    if not done:
        return ""
    w = sum(1 for m in done if m.get("hit"))
    return f"За последние 30 дней по этой теме бот дал {len(done)} прогнозов, зашло {w} ({100 * w / len(done):.0f}%) — все учтены, без подчисток."


def _line_preds(now: pd.Timestamp) -> str:
    """Футбол сегодня по линии: сборные, молодёжные, мелкие лиги — со страниц «смотреть онлайн» (betbot/watch.py)."""
    try:
        ps = json.loads((Path(__file__).resolve().parent.parent / "data" / "watch_preds.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    ps = [p for p in ps if pd.Timestamp(p["kickoff"]) < now + pd.Timedelta(hours=30)][:24]
    if not ps:
        return ""
    cards = "".join(
        f'<a class="card mc" href="../{H.escape(p["url"])}"><div class="t"><span>⚽ {H.escape(p["league"])}</span>'
        f'<span>{pd.Timestamp(p["kickoff"]).tz_convert(MSK):%d.%m %H:%M}</span></div><b>{H.escape(p["home"])} — {H.escape(p["away"])}</b>'
        f'<span class="p">🎯 {H.escape(p["label"])} · {"≈" if p["est"] else ""}{p["odds"]:.2f} · шанс {100 * p["p"]:.0f}%</span></a>' for p in ps)
    return f'<h2>📊 Ещё матчи сегодня — прогноз по линии</h2><div class="grid">{cards}</div>'


def _page(slug: str, title: str, short: str, items: list[dict], done: list[dict], now: pd.Timestamp) -> str:
    line = _line_preds(now) if slug == "futbol-segodnya" else ""
    day = f"{now.day} {pages.MONTHS[now.month - 1]} {now.year}"
    h1 = f"{title} — {day}"
    desc = (f"{title} на {day}: бесплатные прогнозы от ИИ с шансами и коэффициентами"
            + (f", {len(items)} матчей" if items else "") + ". Честная статистика: все прогнозы учтены. Смотреть матчи онлайн.")
    stats = _stats(done)
    cards = "".join(pages._match_card(m, "../") for m in items) or \
        f'<div class="card muted">Новые прогнозы на {short} появляются примерно за час до начала матча — загляните позже или подпишитесь на <a href="https://t.me/aistavvit">@aistavvit</a>.</div>'
    recent = "".join(pages._match_card(m, "../") for m in done[:12])
    faq = [(f"Где найти бесплатные прогнозы на {short}?",
            f"На этой странице — все актуальные прогнозы бота АИ СТАВИТ на {short}: ставка, шанс и коэффициент. "
            f"Страница обновляется автоматически, новые прогнозы выходят примерно за час до матча."),
           (f"Насколько точны прогнозы на {short}?", stats or "Бот учитывает каждый прогноз в открытой статистике на главной странице сайта."),
           ("Как бот делает прогноз?", "Модель считает шансы по силе команд, форме и линии букмекеров, сравнивает их с коэффициентами "
                                       "и выбирает ставку с лучшим соотношением шанса и кэфа. Прогноз — не гарантия. 18+")]
    other = " · ".join(f'<a href="{s}.html">{H.escape(t)}</a>' for s, (t, _, _) in HUBS.items() if s != slug)
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Прогнозы", "predictions/"), (title, None)])
    body = f"""{crumbs}<h1>{H.escape(title)} <span>— {day}</span></h1>
<p class="lead">Бесплатные прогнозы на {H.escape(short)} от искусственного интеллекта: ставка, шанс и коэффициент на каждый матч. {H.escape(stats)}</p>
<h2>⏳ Ближайшие прогнозы</h2><div class="grid">{cards}</div>{line}
{f'<h2>✅ Последние результаты</h2><div class="grid">{recent}</div>' if recent else ''}
<h2>Вопросы</h2>{''.join(f'<h3>{H.escape(q)}</h3><p>{H.escape(a)}</p>' for q, a in faq)}
<p class="muted">Ещё подборки: {other} · <a href="ekspress-dnya.html">Экспресс дня</a> · <a href="../watch/">Смотреть матчи онлайн</a></p>"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": h1, "url": pages.SITE + f"prognozy/{slug}.html",
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": pages.SITE + m["url"],
                                "name": f"Прогноз на матч {m['home']} — {m['away']}"} for i, m in enumerate(items[:30])]},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    tt = f"{title} бесплатно" if "сегодня" in title else f"{title} на сегодня бесплатно"
    return pages.page("../", f"{tt} — {day} · АИ СТАВИТ", desc, pages.SITE + f"prognozy/{slug}.html",
                      body, "pred", None, ld + [bc])


def _express(now: pd.Timestamp) -> str:
    """«Экспресс дня на сегодня»: оба экспресса бота с событиями, кэфом и итогом."""
    try:
        ex = json.loads((DOCS / "express.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ex = []
    day = f"{now.day} {pages.MONTHS[now.month - 1]} {now.year}"
    st = {"won": "✅ Зашёл", "lost": "❌ Не зашёл", "live": "🔴 Идёт"}
    blocks = ""
    for e in ex:
        legs = "".join(
            f'<div style="display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.07)">'
            f'<span><b>{H.escape(g["home"])} — {H.escape(g["away"])}</b><br><small class="muted">{H.escape(g.get("league") or "")} · '
            f'{pd.Timestamp(g["kickoff"]).tz_convert(MSK):%d.%m %H:%M}</small></span>'
            f'<span style="text-align:right;white-space:nowrap">{H.escape(g["label"])} · {g["odds"]:.2f}'
            f'{"<br>✅ " + H.escape(g.get("score", "")) if g.get("win") is True else "<br>❌ " + H.escape(g.get("score", "")) if g.get("win") is False else ""}</span></div>'
            for g in e.get("legs", []))
        blocks += (f'<div class="card" style="margin:12px 0"><div style="display:flex;justify-content:space-between;align-items:center">'
                   f'<b style="font-size:18px">🧩 {H.escape(e.get("title", "Экспресс"))}</b><span style="font-size:20px;font-weight:900;color:#ffc400">кэф {e["odds"]:.2f}</span></div>'
                   f'<p class="muted small">{len(e.get("legs", []))} событий · шанс ~{100 * e.get("p", 0):.0f}% · {st.get(e.get("status"), "⏳ Ждёт начала")}</p>{legs}'
                   + (f'<p style="margin-top:8px"><a href="{H.escape(e["post"])}">Пост в Telegram →</a></p>' if e.get("post") else "") + "</div>")
    title = "Экспресс дня на сегодня"
    faq = [("Когда выходит экспресс дня?", "«Экспресс дня» бот публикует каждый день в 10:00 МСК, «Экспресс на яйцах» с кэфом от 10 — в 20:00."),
           ("Как бот собирает экспресс?", "Берёт события с самым высоким шансом по модели из разных матчей, чтобы они не зависели друг от друга. "
                                          "Каждый экспресс учитывается в балансе бота. Прогноз — не гарантия. 18+")]
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Прогнозы", "predictions/"), (title, None)])
    body = f"""{crumbs}<h1>{title} <span>— {day}</span></h1>
<p class="lead">Экспресс дня от ИИ: события, общий коэффициент и шанс — бесплатно. Итог каждого экспресса учитывается в статистике бота.</p>
{blocks or '<div class="card muted">Новый экспресс выходит в 10:00 МСК.</div>'}
<h2>Вопросы</h2>{''.join(f'<h3>{H.escape(q)}</h3><p>{H.escape(a)}</p>' for q, a in faq)}
<p class="muted">Подборки: {" · ".join(f'<a href="{s}.html">{H.escape(t)}</a>' for s, (t, _, _) in HUBS.items())}</p>"""
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    return pages.page("../", f"Экспресс дня на сегодня {day} — бесплатный экспресс от ИИ · АИ СТАВИТ",
                      f"Экспресс дня на сегодня, {day}: события, общий кэф и шанс от ИИ. Бесплатно, с честной статистикой.",
                      pages.SITE + "prognozy/ekspress-dnya.html", body, "pred", None, [ld, bc])


def _index(counts: dict) -> str:
    rows = "".join(f'<a class="card" href="{s}.html" style="display:flex;justify-content:space-between;text-decoration:none;color:inherit">'
                   f'<b>{H.escape(t)}</b><span class="muted">{counts.get(s, 0)} матчей</span></a>' for s, (t, _, _) in HUBS.items())
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Подборки прогнозов", None)])
    body = f"""{crumbs}<h1>Прогнозы на спорт <span>по темам</span></h1>
<div class="grid">{rows}<a class="card" href="ekspress-dnya.html" style="text-decoration:none;color:inherit"><b>Экспресс дня на сегодня</b></a></div>"""
    return pages.page("../", "Прогнозы на спорт по темам: футбол, РПЛ, АПЛ, НХЛ, НБА, теннис — АИ СТАВИТ",
                      "Подборки бесплатных прогнозов от ИИ: футбол сегодня, РПЛ, АПЛ, Лига чемпионов, НХЛ, НБА, теннис, киберспорт и экспресс дня.",
                      pages.SITE + "prognozy/", body, "pred", None, [bc])


def build(ms: list[dict], now: pd.Timestamp) -> list[str]:
    """Пишет docs/prognozy/*.html; возвращает адреса для карты сайта."""
    now = now.tz_convert(MSK)
    old = now - pd.Timedelta(days=30)
    urls, counts = [], {}
    for slug, (title, short, keep) in HUBS.items():
        mine = [m for m in ms if keep(m)]
        items = sorted([m for m in mine if not m.get("finished") and m["kickoff"] > now - pd.Timedelta(hours=3)], key=lambda m: m["kickoff"])
        done = [m for m in mine if m.get("finished") and m["kickoff"] > old]
        counts[slug] = len(items)
        pages._write(OUT / f"{slug}.html", _page(slug, title, short, items, done, now))
        urls.append(f"prognozy/{slug}.html")
    pages._write(OUT / "ekspress-dnya.html", _express(now))
    pages._write(OUT / "index.html", _index(counts))
    return ["prognozy/", "prognozy/ekspress-dnya.html"] + urls
