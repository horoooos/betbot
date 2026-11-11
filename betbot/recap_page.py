"""«Итоги дня» на сайте: честный отчёт «вчера зашло 7 из 10» с картинкой для соцсетей и кнопками «поделиться».

docs/itogi/YYYY-MM-DD.html + .png (картинка уходит в og:image — её показывают Telegram, ВК, WhatsApp при репосте),
docs/itogi/index.html — всегда последний день (постоянный адрес «итоги вчера»). Хранятся последние 30 дней.
"""
from __future__ import annotations

import html as H
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from . import pages

DOCS = Path(__file__).resolve().parent.parent / "docs"
OUT = DOCS / "itogi"
KEEP_DAYS = 30
EMOJI = {"football": "⚽", "hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "esports": "🎮"}


def _hit(v) -> bool:
    return str(v).lower() in ("true", "1", "1.0")


def _image(day: pd.Timestamp, rows: pd.DataFrame, path: Path) -> None:
    """Картинка для соцсетей: «ИТОГИ ДНЯ · 11 ноября», крупно «7 из 10» и три лучших захода."""
    from . import card
    hits = rows[rows["main_hit"].map(_hit)]
    best = hits.sort_values("main_odds", ascending=False).head(3)
    lines = [f"✓ {r['home']} — {r['away']}: {r['main_label']} · {float(r['main_odds']):.2f}" for _, r in best.iterrows()]
    roi = 100 * sum((float(r["main_odds"]) - 1) if _hit(r["main_hit"]) else -1 for _, r in rows.iterrows()) / max(len(rows), 1)
    good = len(hits) * 2 >= len(rows)
    png = card.slide_card("Итоги дня", f"{len(hits)} из {len(rows)}",
                          f"{day.day} {pages.MONTHS[day.month - 1]} · зашло {100 * len(hits) / max(len(rows), 1):.0f}%"
                          + (f" · ROI {roi:+.1f}%" if roi > 0 else ""),   # на картинке для репостов — ROI только в плюсе
                          lines, ((46, 204, 113), (40, 80, 170)) if good else ((255, 160, 40), (90, 60, 200)), brand="@aistavvit")
    path.write_bytes(png)


def _page(day: pd.Timestamp, rows: pd.DataFrame, prev: str | None, nxt: str | None, canon: str, img: str) -> str:
    hits = int(rows["main_hit"].map(_hit).sum())
    n = len(rows)
    roi = 100 * sum((float(r["main_odds"]) - 1) if _hit(r["main_hit"]) else -1 for _, r in rows.iterrows()) / max(n, 1)
    d = f"{day.day} {pages.MONTHS[day.month - 1]} {day.year}"
    title = f"Итоги дня {d}: зашло {hits} из {n} — прогнозы АИ СТАВИТ"
    desc = f"Честные итоги прогнозов бота за {d}: зашло {hits} из {n} ({100 * hits / max(n, 1):.0f}%), ROI {roi:+.1f}%. Все матчи и результаты — без подчисток."
    trs = "".join(
        f'<div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin:6px 0;padding:10px 14px">'
        f'<span>{EMOJI.get(r.get("sport") if isinstance(r.get("sport"), str) else "football", "⚽")} <b>{H.escape(str(r["home"]))} — {H.escape(str(r["away"]))}</b>'
        f'<br><small class="muted">{H.escape(str(r["main_label"]))} · {float(r["main_odds"]):.2f}</small></span>'
        f'<span style="white-space:nowrap;font-weight:900">{H.escape(str(r["score"]))} {"✅" if _hit(r["main_hit"]) else "❌"}</span></div>'
        for _, r in rows.sort_values("main_hit", key=lambda c: c.map(_hit), ascending=False).iterrows())
    text = quote(f"Итоги дня {d}: бот АИ СТАВИТ — зашло {hits} из {n}")
    url = quote(canon)
    share = (f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:14px 0">'
             f'<a class="btn gold" href="https://t.me/share/url?url={url}&text={text}" target="_blank" rel="noopener">📲 Поделиться в Telegram</a>'
             f'<a class="btn ghost" href="https://vk.com/share.php?url={url}&title={text}" target="_blank" rel="noopener">ВКонтакте</a>'
             f'<a class="btn ghost" href="https://wa.me/?text={text}%20{url}" target="_blank" rel="noopener">WhatsApp</a></div>')
    nav = " · ".join(x for x in (f'<a href="{prev}">← предыдущий день</a>' if prev else "",
                                 f'<a href="{nxt}">следующий день →</a>' if nxt else "") if x)
    crumbs, bc = pages._crumbs("../", [("Главная", ""), ("Итоги дня", "itogi/"), (d, None)])
    body = f"""{crumbs}<h1>Итоги дня <span>— {d}</span></h1>
<p class="lead">Зашло <b>{hits} из {n}</b> основных прогнозов ({100 * hits / max(n, 1):.0f}%), ROI дня {roi:+.1f}%. Каждый прогноз учтён — и заходы, и промахи.</p>
<img src="{H.escape(img)}" alt="Итоги дня {d}: зашло {hits} из {n}" style="width:100%;border-radius:18px;margin:10px 0" loading="lazy">
{share}<h2>Все прогнозы дня</h2>{trs}
<p class="muted" style="margin-top:12px">{nav}{' · ' if nav else ''}<a href="../">статистика бота</a> · <a href="../prognozy/futbol-segodnya.html">прогнозы на сегодня</a> · <a href="https://t.me/aistavvit">Telegram-канал</a></p>"""
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": title, "datePublished": (day + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
          "image": pages.SITE + img.lstrip("./").replace("../", ""), "author": {"@type": "Organization", "name": "АИ СТАВИТ"},
          "publisher": {"@type": "Organization", "name": "АИ СТАВИТ", "url": pages.SITE}}
    return pages.page("../", title, desc, canon, body, "pred", pages.SITE + "itogi/" + Path(img).name, [ld, bc], "article")


def build(res: pd.DataFrame, now: pd.Timestamp) -> list[str]:
    """Страницы итогов за последние дни (новые — с картинкой); index.html — последний полный день."""
    if res is None or not len(res):
        return []
    OUT.mkdir(parents=True, exist_ok=True)
    res = res[pd.to_numeric(res["main_odds"], errors="coerce") > 1].copy()
    res["d"] = pd.to_datetime(res["date"]).dt.normalize()
    today = now.tz_convert("Europe/Moscow").tz_localize(None).normalize()
    days = sorted(d for d in res["d"].unique() if today - pd.Timedelta(days=KEEP_DAYS) <= d < today)
    urls = []
    for i, d in enumerate(days):
        d = pd.Timestamp(d)
        rows = res[res["d"] == d]
        if len(rows) < 3:
            continue
        name = f"{d:%Y-%m-%d}"
        png = OUT / f"{name}.png"
        if not png.exists() or d >= today - pd.Timedelta(days=2):   # последние дни — перерисовываем (итоги дозаполняются)
            try:
                _image(d, rows, png)
            except Exception as e:
                print(f"  ! картинка итогов {name} не нарисовалась: {e}")
        prev = f"{pd.Timestamp(days[i - 1]):%Y-%m-%d}.html" if i > 0 else None
        nxt = f"{pd.Timestamp(days[i + 1]):%Y-%m-%d}.html" if i + 1 < len(days) else None
        html_ = _page(d, rows, prev, nxt, pages.SITE + f"itogi/{name}.html", f"{name}.png")
        pages._write(OUT / f"{name}.html", html_)
        urls.append(f"itogi/{name}.html")
        if i == len(days) - 1:   # постоянный адрес «итоги вчера»
            pages._write(OUT / "index.html", html_.replace(f'href="{pages.SITE}itogi/{name}.html"', f'href="{pages.SITE}itogi/"'))
    for f in OUT.glob("20*.*"):   # старше 30 дней — удаляем
        try:
            if pd.Timestamp(f.name[:10]) < today - pd.Timedelta(days=KEEP_DAYS):
                f.unlink()
        except ValueError:
            pass
    return (["itogi/"] if urls else []) + urls
