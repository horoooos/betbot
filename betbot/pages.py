"""Страницы сайта для поисковиков: новости и прогнозы на матчи из нашего Telegram-канала.

Источник — публичная страница канала t.me/s/aistavvit (посты, фото, ответы-разборы и live-ветки).
Каждая новость и каждый прогноз получает свою страницу с заголовком, описанием, разметкой schema.org
и попадает в sitemap.xml — так сайт находят в Яндексе и Google по запросам вида
«прогноз на матч Спартак — Зенит» и «новости футбола».
"""
from __future__ import annotations

import html as H
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DOCS, DATA = ROOT / "docs", ROOT / "data"
CHANNEL_FILE = DATA / "channel.json"      # все посты канала (копится, чтобы история не терялась)
EVENTS_FILE = DATA / "match_events.json"  # ход завершённых матчей с ESPN (голы, карточки), берём один раз
SITE = "https://horoooos.github.io/betbot/"
CH = "aistavvit"
NEWS_TAGS = {"#футбол": "football", "#хоккей": "hockey", "#баскетбол": "basketball", "#теннис": "tennis", "#киберспорт": "esports"}
SPORT_RU = {"football": "Футбол", "hockey": "Хоккей", "basketball": "Баскетбол", "tennis": "Теннис", "esports": "Киберспорт"}
EMOJI = {"football": "⚽", "hockey": "🏒", "basketball": "🏀", "tennis": "🎾", "esports": "🎮"}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; AISTAVVIT-site/1.0)"}


# ── канал ─────────────────────────────────────────────────────────────────────

def _clean(raw: str) -> str:
    """HTML поста из t.me → безопасный HTML для нашего сайта (жирный, курсив, код, ссылки, переносы)."""
    s = re.sub(r'<i class="emoji"[^>]*><b>(.*?)</b></i>', r"\1", raw, flags=re.S)
    s = re.sub(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", r"\1", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    out, pos = [], 0
    for m in re.finditer(r"<(/?)(\w+)([^>]*)>", s):
        out.append(s[pos:m.start()])
        close, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag in ("b", "strong", "i", "em", "u", "s", "code"):
            t = {"strong": "b", "em": "i"}.get(tag, tag)
            out.append(f"</{t}>" if close else f"<{t}>")
        elif tag == "a":
            href = re.search(r'href="([^"]+)"', attrs)
            if close:
                out.append("</a>")
            elif href and href.group(1).startswith("?q="):   # хештег канала
                out.append(f'<a href="https://t.me/s/{CH}{H.escape(href.group(1))}" rel="nofollow">')
            elif href and href.group(1).startswith("http"):
                out.append(f'<a href="{H.escape(href.group(1))}" rel="nofollow noopener" target="_blank">')
            else:
                out.append("<a>")
        pos = m.end()
    out.append(s[pos:])
    return "".join(out).strip()


def _plain(cleaned: str) -> str:
    return H.unescape(re.sub(r"<[^>]+>", "", cleaned))


def _parse(page: str) -> dict[int, dict]:
    posts = {}
    for chunk in page.split('data-post="' + CH + "/")[1:]:
        m = re.match(r"(\d+)", chunk)
        if not m:
            continue
        pid = int(m.group(1))
        text = re.search(r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>', chunk, re.S)
        photo = re.search(r"tgme_widget_message_photo_wrap[^>]+background-image:url\('([^']+)'\)", chunk)
        when = re.search(r'<time datetime="([^"]+)"', chunk)
        reply = re.search(r'class="tgme_widget_message_reply"[^>]*href="https://t\.me/' + CH + r'/(\d+)"', chunk)
        if not when:
            continue
        posts[pid] = {"id": pid, "t": when.group(1), "html": _clean(text.group(1)) if text else "",
                      "photo": photo.group(1) if photo else None, "reply": int(reply.group(1)) if reply else None}
    return posts


def _fetch(before: int | None) -> dict[int, dict]:
    url = f"https://t.me/s/{CH}" + (f"?before={before}" if before else "")
    try:
        r = requests.get(url, headers=UA, timeout=20)
        return _parse(r.text) if r.ok else {}
    except requests.RequestException:
        return {}


def sync_channel(max_pages: int = 25) -> dict[int, dict]:
    """Подтягивает новые посты канала, а старую историю докачивает понемногу (max_pages страниц за запуск)."""
    raw = json.loads(CHANNEL_FILE.read_text(encoding="utf-8")) if CHANNEL_FILE.exists() else {}
    store = {int(k): v for k, v in raw.get("posts", {}).items()}
    complete = raw.get("complete", False)
    known, pages, before = (max(store) if store else 0), 0, None
    while pages < max_pages:                      # 1) свежие посты — пока не дойдём до уже известных
        got = _fetch(before); pages += 1
        if not got:
            break
        store.update(got)
        if min(got) <= known or min(got) <= 1:
            break
        before = min(got); time.sleep(0.6)
    while not complete and pages < max_pages:     # 2) история канала — от самого старого известного поста назад
        got = _fetch(min(store) if store else None); pages += 1
        if not got or min(got) >= min(store):
            complete = True
            break
        store.update(got)
        if min(got) <= 1:
            complete = True
        time.sleep(0.6)
    CHANNEL_FILE.write_text(json.dumps({"complete": complete, "posts": {str(k): v for k, v in sorted(store.items())}}, ensure_ascii=False), encoding="utf-8")
    return store


# ── вспомогательное ───────────────────────────────────────────────────────────

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                                                    "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slug(text: str, n: int = 70) -> str:
    s = "".join(_TR.get(c, c) for c in text.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-") or "post"


def _date_ru(t: pd.Timestamp) -> str:
    return f"{t.day} {MONTHS[t.month - 1]} {t.year}"


def _write(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def nav(prefix: str, on: str = "") -> str:
    items = [("matches.html", "📺 Матчи онлайн", "live"), ("predictions/", "🎯 Прогнозы", "pred"), ("news/", "📰 Новости", "news"), ("feed.html", "💬 Лента", "feed")]
    links = "".join(f'<a href="{prefix}{u}"{" class=on" if k == on else ""}>{t}</a>' for u, t, k in items)
    return (f'<nav class="topnav"><a class="logo" href="{prefix}./">АИ СТАВИТ</a><div class="links">{links}'
            f'<a class="me" id="navUser" href="{prefix}profile.html">Войти</a></div></nav>')


def page(prefix: str, title: str, desc: str, canon: str, body: str, on: str = "", og_image: str | None = None,
         ld: list[dict] | None = None, og_type: str = "website") -> str:
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in (ld or []))
    img = f'<meta property="og:image" content="{H.escape(og_image or SITE + "og.png")}"><meta name="twitter:card" content="summary_large_image">'
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(title)}</title><meta name="description" content="{H.escape(desc[:300])}">
<link rel="canonical" href="{canon}"><meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="{og_type}"><meta property="og:title" content="{H.escape(title)}"><meta property="og:description" content="{H.escape(desc[:300])}">
<meta property="og:url" content="{canon}"><meta property="og:site_name" content="АИ СТАВИТ"><meta property="og:locale" content="ru_RU">{img}
<meta name="theme-color" content="#070b1a">
<link rel="icon" href="{prefix}favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="{prefix}favicon-32.png"><link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png"><link rel="manifest" href="{prefix}site.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}site.css?v=4">{lds}
</head><body><main>
{nav(prefix, on)}
{body}
<footer>АИ СТАВИТ — бесплатные прогнозы на спорт от искусственного интеллекта и честная статистика. Прогноз — не гарантия выигрыша. 18+.
<br><a href="https://t.me/{CH}">Telegram-канал @{CH}</a> · <a href="{prefix}./">Статистика бота</a> · <a href="{prefix}matches.html">Матчи онлайн</a> · <a href="{prefix}news/">Новости спорта</a> · <a href="{prefix}predictions/">Прогнозы на матчи</a></footer>
</main><div class="sticky"><a class="a" href="{prefix}matches.html">📺 Онлайн</a><a class="b" href="https://t.me/{CH}">📲 Канал</a></div>
<script type="module">import("{prefix}fb.js?v=6").then(fb => {{ fb.navUser(document.getElementById("navUser")); fb.track("{on or 'page'}"); }}).catch(() => {{}});</script>
</body></html>"""


def _crumbs(prefix: str, items: list[tuple[str, str | None]]) -> tuple[str, dict]:
    """items: (название, путь от корня сайта или None). prefix — как дойти до корня с текущей страницы."""
    html_ = " › ".join(f'<a href="{prefix}{u}">{H.escape(t)}</a>' if u is not None else H.escape(t) for t, u in items)
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": t, **({"item": SITE + u} if u is not None else {})}
        for i, (t, u) in enumerate(items)]}
    return f'<div class="crumbs">{html_}</div>', ld


# ── новости ───────────────────────────────────────────────────────────────────

def _news(store: dict[int, dict]) -> list[dict]:
    out = []
    for p in store.values():
        plain = _plain(p["html"]).strip()
        tail = plain.rsplit("\n", 1)[-1].strip()
        if tail not in NEWS_TAGS or p.get("reply"):
            continue
        lines = [x for x in plain.split("\n") if x.strip()]
        if len(lines) < 3:
            continue
        title = re.sub(r"^[^\wА-Яа-яЁё«\"]+", "", lines[0]).strip()
        body_html = p["html"].split("\n", 1)[1] if "\n" in p["html"] else ""
        body_html = re.sub(r"\s*<a[^>]*>#[^<]+</a>\s*$", "", body_html.strip())
        t = pd.Timestamp(p["t"]).tz_convert("Europe/Moscow")
        out.append({"id": p["id"], "title": title, "sport": NEWS_TAGS[tail], "t": t, "photo": p.get("photo"),
                    "body": body_html.strip(), "desc": " ".join(lines[1:3])[:240],
                    "url": f"news/{p['id']}-{slug(title)}.html"})
    return sorted(out, key=lambda x: x["t"], reverse=True)


def _news_page(n: dict, all_news: list[dict]) -> str:
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Новости", "news/"), (SPORT_RU[n["sport"]], None)])
    paras = "".join(f"<p>{x}</p>" for x in n["body"].split("\n\n") if x.strip()).replace("\n", "<br>")
    more = [x for x in all_news if x["id"] != n["id"] and x["sport"] == n["sport"]][:4]
    cards = "".join(_news_card(x, "../") for x in more)
    canon = SITE + n["url"]
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": n["title"][:110], "datePublished": n["t"].isoformat(),
          "dateModified": n["t"].isoformat(), "inLanguage": "ru", "mainEntityOfPage": canon, "articleSection": SPORT_RU[n["sport"]],
          "publisher": {"@type": "Organization", "name": "АИ СТАВИТ", "url": SITE}, "author": {"@type": "Organization", "name": "АИ СТАВИТ"},
          **({"image": [n["photo"]]} if n["photo"] else {})}
    body = f"""{crumbs}<article class="post">
<span class="tag">{EMOJI[n['sport']]} {SPORT_RU[n['sport']]} · {_date_ru(n['t'])}, {n['t']:%H:%M} МСК</span>
<h1>{H.escape(n['title'])}</h1>
{f'<img class="cover" src="{H.escape(n["photo"])}" alt="{H.escape(n["title"])}" loading="eager">' if n['photo'] else ''}
<div class="body">{paras}</div>
<p class="muted small">Новость опубликована в Telegram-канале <a href="https://t.me/{CH}/{n['id']}">@{CH}</a>.</p>
<div class="row" style="margin-top:14px"><a class="btn gold" href="https://t.me/{CH}">📲 Все новости и прогнозы в Telegram</a><a class="btn ghost" href="../matches.html">📺 Матчи онлайн</a></div>
</article>
{f'<h2>Ещё новости: {SPORT_RU[n["sport"]].lower()}</h2><div class="grid">{cards}</div>' if cards else ''}"""
    return page("../", f"{n['title']} — новости спорта · АИ СТАВИТ", n["desc"] or n["title"], canon, body, "news", n["photo"], [ld, bc], "article")


def _news_card(n: dict, prefix: str) -> str:
    img = f'<img src="{H.escape(n["photo"])}" alt="{H.escape(n["title"])}" loading="lazy">' if n["photo"] else '<div class="ph"></div>'
    return (f'<a class="card nc" href="{prefix}{n["url"]}">{img}<div class="b"><span class="tag">{EMOJI[n["sport"]]} {SPORT_RU[n["sport"]]} · '
            f'{n["t"].day} {MONTHS[n["t"].month - 1]}</span><b>{H.escape(n["title"])}</b><p>{H.escape(n["desc"][:150])}…</p></div></a>')


def _news_index(news: list[dict]) -> str:
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Новости спорта", None)])
    blocks = ""
    for sp in ("football", "hockey", "basketball", "tennis", "esports"):
        items = [n for n in news if n["sport"] == sp][:6]
        if items:
            blocks += f'<h2 id="{sp}">{EMOJI[sp]} {SPORT_RU[sp]}</h2><div class="grid">{"".join(_news_card(n, "../") for n in items)}</div>'
    body = f"""{crumbs}<h1>Новости спорта <span>сегодня</span></h1>
<p class="lead">Главные новости футбола, хоккея, НБА, тенниса и киберспорта — коротко и по делу, каждый час. Из нашего Telegram-канала @{CH}.</p>
<h2>🆕 Свежие новости</h2><div class="grid">{"".join(_news_card(n, "../") for n in news[:12])}</div>{blocks}
<h2>📚 Архив новостей</h2><div class="card">{"".join(f'<div><a href="../{n["url"]}">{H.escape(n["title"])}</a> <span class="muted small">· {n["t"]:%d.%m}</span></div>' for n in news[12:150])}</div>"""
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Новости спорта", "url": SITE + "news/"}
    return page("../", "Новости спорта сегодня: футбол, хоккей, НБА, теннис — АИ СТАВИТ",
                "Свежие новости спорта каждый час: футбол, хоккей НХЛ и КХЛ, баскетбол НБА, теннис и киберспорт. Коротко, с фото и без воды.",
                SITE + "news/", body, "news", news[0]["photo"] if news else None, [ld, bc])


# ── прогнозы на матчи ─────────────────────────────────────────────────────────

def _pred_posts(store: dict[int, dict]) -> list[tuple[int, str, pd.Timestamp]]:
    return [(p["id"], _plain(p["html"]), pd.Timestamp(p["t"]).tz_convert("Europe/Moscow").normalize().tz_localize(None))
            for p in store.values() if not p.get("reply") and "ПРОГНОЗ" in p["html"][:200]]


def _find_post(cands: list, home: str, away: str, day: str) -> int | None:
    """Пост с прогнозом старого матча — по названиям команд (для матчей, которых уже нет в памяти бота)."""
    pat, d = f"{home} — {away}", pd.Timestamp(day)
    best = None
    for pid, text, t in cands:
        if pat in text and abs((t - d).days) <= 1:
            best = pid
    return best


def _events(m: dict) -> list[str]:
    """Ход завершённого матча с ESPN: голы, карточки, удаления (берём один раз и храним)."""
    cache = json.loads(EVENTS_FILE.read_text(encoding="utf-8")) if EVENTS_FILE.exists() else {}
    key = f"{m.get('sport', 'football')}|{m['id']}"
    if key in cache:
        return cache[key]
    return []


def fetch_events(items: list[dict], limit: int = 10) -> None:
    cache = json.loads(EVENTS_FILE.read_text(encoding="utf-8")) if EVENTS_FILE.exists() else {}
    done = 0
    for m in items:
        key = f"{m.get('sport', 'football')}|{m['id']}"
        if key in cache or not m.get("finished") or not m.get("path") or m.get("sport") == "tennis":
            continue
        if done >= limit:
            break
        done += 1
        try:
            d = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{m['path']}/summary?event={m['id']}", timeout=20).json()
        except Exception:
            continue
        out = []
        if m.get("sport", "football") == "football":
            ru = {"goal": "⚽ Гол", "goal---header": "⚽ Гол головой", "goal---volley": "⚽ Гол с лёта", "goal---free-kick": "⚽ Гол со штрафного",
                  "penalty---scored": "⚽ Гол с пенальти", "own-goal": "⚽ Автогол", "yellow-card": "🟨 Жёлтая", "red-card": "🟥 Красная",
                  "penalty---missed": "❌ Незабитый пенальти", "penalty---saved": "🧤 Сейв на пенальти"}
            for e in d.get("keyEvents", []):
                k = (e.get("type") or {}).get("type", "")
                if k not in ru:
                    continue
                who = ", ".join(x["athlete"]["displayName"] for x in e.get("participants", [])[:1] if x.get("athlete"))
                team = (e.get("team") or {}).get("displayName", "")
                out.append(f"{(e.get('clock') or {}).get('displayValue', '')} {ru[k]}: {who}{' (' + team + ')' if team else ''}".strip())
        else:
            for p in d.get("plays", []):
                if p.get("scoringPlay") and (m.get("sport") == "hockey" or (p.get("scoreValue") or 0) >= 3):
                    out.append(f"{(p.get('period') or {}).get('displayValue', '')} {(p.get('clock') or {}).get('displayValue', '')} · "
                               f"{p.get('text', '')} ({p.get('awayScore')}:{p.get('homeScore')})")
            out = out[-25:]
        cache[key] = out[:40]
        time.sleep(0.3)
    EVENTS_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _matches(stores: dict, results: pd.DataFrame, store: dict[int, dict], now: pd.Timestamp) -> list[dict]:
    """Все матчи с прогнозом: свежие из памяти бота + завершённые из results.csv за 60 дней."""
    from . import live, sports
    from .site import _bot_block
    out = {}
    for m in stores.values():
        if not m.get("msg_id") or "ru" not in m.get("home", {}) or not m.get("main"):
            continue
        sport = m.get("sport", "football")
        path = f"soccer/{m['slug']}" if sport == "football" and m.get("slug") else (sports.LEAGUES.get(m.get("div"), ("",) * 5)[3] or "")
        btn = live._tracker(m, sport, m["home"]["ru"], m["away"]["ru"]) if sport != "esports" else None
        out[(sport, str(m["id"]))] = {"id": str(m["id"]), "sport": sport, "home": m["home"]["ru"], "away": m["away"]["ru"],
            "hl": (m["home"].get("logo") or [None, None])[1] if isinstance(m["home"].get("logo"), list) else m["home"].get("logo"),
            "al": (m["away"].get("logo") or [None, None])[1] if isinstance(m["away"].get("logo"), list) else m["away"].get("logo"),
            "kickoff": pd.Timestamp(m["kickoff"]).tz_convert("Europe/Moscow"), "league": live._league(m), "msg": m["msg_id"],
            "tip": m["main"]["label"], "odds": m["main"].get("odds"), "p": m["main"].get("p"), "bot": _bot_block(m),
            "path": path, "live": btn[1] if btn else None, "venue": m.get("venue")}
    if results is not None and len(results):
        recent = results[pd.to_datetime(results["date"]) >= (now.tz_localize(None).normalize() - pd.Timedelta(days=60))]
        cands = _pred_posts(store)
        for _, r in recent.iterrows():
            sport = r["sport"] if isinstance(r.get("sport"), str) else "football"
            key = (sport, str(r["id"]))
            hit = str(r["main_hit"]).lower() in ("true", "1", "1.0")
            if key in out:
                out[key].update(score=str(r["score"]), hit=hit, finished=True)
                continue
            msg = _find_post(cands, str(r["home"]), str(r["away"]), str(r["date"]))
            if not msg:
                continue
            out[key] = {"id": str(r["id"]), "sport": sport, "home": str(r["home"]), "away": str(r["away"]), "hl": None, "al": None,
                        "kickoff": pd.Timestamp(store[msg]["t"]).tz_convert("Europe/Moscow") + pd.Timedelta(hours=1), "league": "",
                        "msg": msg, "tip": str(r["main_label"]), "odds": float(r["main_odds"]) if pd.notna(r["main_odds"]) else None,
                        "p": None, "bot": None, "path": "", "live": None, "venue": None, "score": str(r["score"]), "hit": hit, "finished": True}
    for m in out.values():
        m["url"] = f"predictions/{m['kickoff']:%Y-%m-%d}-{slug(m['home'] + ' ' + m['away'], 60)}-{m['id']}.html"
        m.setdefault("finished", False)
    return sorted(out.values(), key=lambda m: m["kickoff"], reverse=True)


def _match_page(m: dict, store: dict[int, dict], all_m: list[dict]) -> str:
    title_teams = f"{m['home']} — {m['away']}"
    day = _date_ru(m["kickoff"])
    pred = store.get(m["msg"], {})
    thread = sorted([p for p in store.values() if p.get("reply") == m["msg"]], key=lambda p: p["id"])
    analysis = [p for p in thread if "#live" not in p["html"][-60:] and "#итог" not in p["html"][-60:]]
    livep = [p for p in thread if p not in analysis]
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Прогнозы", "predictions/"), (title_teams, None)])
    logo = lambda u: f'<img src="{H.escape(u)}" alt="" loading="lazy">' if u else ""
    sc = m.get("score", "").replace(":", " : ") if m.get("finished") else "vs"
    res = ""
    if m.get("finished"):
        res = f'<span class="badge {"ok" if m.get("hit") else "no"}">{"✅ Прогноз зашёл" if m.get("hit") else "❌ Прогноз не зашёл"}</span>'
    else:
        res = '<span class="badge wait">⏳ Матч ещё не сыгран</span>'
    chances = ""
    b = m.get("bot")
    if b and b.get("markets"):
        rows = "".join(f'<div class="mr"><span>{H.escape(l)}</span><div class="mb"><i style="width:{p * 100:.0f}%;background:{"#2ecc71" if p >= .6 else "#ffc400" if p >= .45 else "#ff7a3d"}"></i></div>'
                       f'<span class="pc">{p * 100:.0f}%</span><span class="o">{f"{o:.2f}" if o else "—"}</span></div>' for l, p, o in b["markets"])
        sc_ = "".join(f'<span class="badge wait" style="margin:2px">{H.escape(s)} · {p * 100:.0f}%</span>' for s, p in (b.get("scores") or []))
        chances = (f'<h2>📊 Шансы по всем рынкам</h2><div class="card">{rows}'
                   f'{f"<p class=small style=margin-top:10px>Самые вероятные счета: {sc_}</p>" if sc_ else ""}'
                   f'{f"<p class=muted small>{H.escape(b["center"])}</p>" if b.get("center") else ""}</div>')
    ev = _events(m)
    game = ""
    if livep or ev:
        game = '<h2>🏟 Как прошёл матч</h2><div class="card tl">' + "".join(f'<div class="pre">{p["html"]}</div>' for p in livep) + \
               "".join(f"<div>{H.escape(e)}</div>" for e in ev) + "</div>"
    watch = (f'<a class="btn red" href="../{H.escape(m["live"].split("/betbot/")[-1])}">{"▶ Повтор матча" if m.get("finished") else "📺 Смотреть онлайн"}</a>'
             if m.get("live") else "")
    others = [x for x in all_m if x is not m and x["kickoff"].date() == m["kickoff"].date()][:8]
    pct = f" — шанс {m['p'] * 100:.0f}%" if m.get("p") else ""
    desc = (f"Прогноз на матч {title_teams} {day}: {m['tip']}{pct}, кэф {m['odds']:.2f}. " if m.get("odds") else f"Прогноз на матч {title_teams} {day}: {m['tip']}. ") + \
           (f"{m.get('league', '')}. Шансы команд, разбор, составы и ход игры онлайн." if not m.get("finished") else f"Итог {m.get('score', '')}. Разбор матча и ход игры.")
    ld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": title_teams, "startDate": m["kickoff"].isoformat(),
          "sport": SPORT_RU.get(m["sport"], ""), "eventStatus": "https://schema.org/EventScheduled",
          "competitor": [{"@type": "SportsTeam", "name": m["home"]}, {"@type": "SportsTeam", "name": m["away"]}],
          "homeTeam": {"@type": "SportsTeam", "name": m["home"]}, "awayTeam": {"@type": "SportsTeam", "name": m["away"]},
          "description": desc, "url": SITE + m["url"], **({"location": {"@type": "Place", "name": m["venue"]}} if m.get("venue") else {})}
    body = f"""{crumbs}<span class="tag">{EMOJI.get(m['sport'], '')} {H.escape(m.get('league') or SPORT_RU.get(m['sport'], ''))} · {day}, {m['kickoff']:%H:%M} МСК</span>
<h1>Прогноз на матч {H.escape(title_teams)}: <span>{H.escape(m['tip'])}</span></h1>
<div class="card"><div class="teams">{logo(m.get('hl'))}<b>{H.escape(m['home'])}</b><span class="sc">{H.escape(sc)}</span><b>{H.escape(m['away'])}</b>{logo(m.get('al'))}</div>
<div style="text-align:center">{res}</div>
<div class="row" style="justify-content:center;margin-top:12px">{watch}<a class="btn gold" href="https://t.me/{CH}/{m['msg']}">📲 Прогноз в Telegram</a></div></div>
<h2>🎯 Прогноз бота</h2><div class="card pre">{pred.get('html') or H.escape(m['tip'])}</div>
{chances}
{''.join(f'<h2>🔎 Полный разбор матча</h2><div class="card pre">{p["html"]}</div>' for p in analysis[:2])}
{game}
{f'<h2>Другие прогнозы на {day}</h2><div class="grid">' + "".join(_match_card(x, "../") for x in others) + "</div>" if others else ""}"""
    img = pred.get("photo")
    return page("../", f"Прогноз на матч {title_teams} {m['kickoff']:%d.%m.%Y}: {m['tip']} — АИ СТАВИТ", desc, SITE + m["url"], body, "pred", img, [ld, bc], "article")


def _match_card(m: dict, prefix: str) -> str:
    st = (f'<span class="badge {"ok" if m.get("hit") else "no"}">{H.escape(m.get("score", ""))} {"✅" if m.get("hit") else "❌"}</span>' if m.get("finished")
          else f'<span>{m["kickoff"]:%d.%m %H:%M}</span>')
    return (f'<a class="card mc" href="{prefix}{m["url"]}"><div class="t"><span>{EMOJI.get(m["sport"], "")} {H.escape(m.get("league") or SPORT_RU.get(m["sport"], ""))}</span>{st}</div>'
            f'<b>{H.escape(m["home"])} — {H.escape(m["away"])}</b><span class="p">🎯 {H.escape(m["tip"])}{f" · {m["odds"]:.2f}" if m.get("odds") else ""}'
            f'{f" · шанс {m["p"] * 100:.0f}%" if m.get("p") else ""}</span></a>')


def _pred_index(ms: list[dict], now: pd.Timestamp) -> str:
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Прогнозы на матчи", None)])
    upcoming = sorted([m for m in ms if not m.get("finished") and m["kickoff"] > now - pd.Timedelta(hours=3)], key=lambda m: m["kickoff"])
    done = [m for m in ms if m.get("finished")][:60]
    hits = sum(1 for m in done if m.get("hit"))
    body = f"""{crumbs}<h1>Прогнозы на спорт <span>на сегодня и завтра</span></h1>
<p class="lead">Бесплатные прогнозы на футбол, хоккей, баскетбол и теннис от искусственного интеллекта: шансы по всем рынкам, разбор каждого матча и честный итог. Из последних {len(done)} прогнозов зашло {hits}.</p>
<h2>⏳ Ближайшие матчи</h2><div class="grid">{"".join(_match_card(m, "../") for m in upcoming) or '<div class="card muted">Новые прогнозы появляются за час до начала матча.</div>'}</div>
<h2>✅ Последние результаты</h2><div class="grid">{"".join(_match_card(m, "../") for m in done)}</div>"""
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Прогнозы на спорт", "url": SITE + "predictions/"}
    return page("../", "Прогнозы на спорт сегодня бесплатно: футбол, хоккей, НБА, теннис — АИ СТАВИТ",
                "Бесплатные прогнозы на сегодня от ИИ: футбол, хоккей НХЛ, баскетбол НБА, теннис. Шансы, коэффициенты, разбор матча и честная статистика.",
                SITE + "predictions/", body, "pred", None, [ld, bc])


# ── сборка ────────────────────────────────────────────────────────────────────

def build(stores: dict, results: pd.DataFrame, now: pd.Timestamp, max_pages: int = 25) -> dict:
    """Синхронизирует канал, пишет страницы новостей и прогнозов, sitemap.xml и robots.txt.
    Возвращает блоки для главной (свежие новости и ближайшие прогнозы)."""
    store = sync_channel(max_pages)
    news = _news(store)
    ms = _matches(stores, results, store, now)
    fetch_events(ms)
    changed = 0
    for n in news[:400]:
        changed += _write(DOCS / n["url"], _news_page(n, news))
    changed += _write(DOCS / "news" / "index.html", _news_index(news))
    for m in ms:
        changed += _write(DOCS / m["url"], _match_page(m, store, ms))
    changed += _write(DOCS / "predictions" / "index.html", _pred_index(ms, now))
    urls = [("", "hourly", "1.0"), ("matches.html", "hourly", "0.9"), ("predictions/", "hourly", "0.9"), ("news/", "hourly", "0.9"), ("feed.html", "hourly", "0.6")]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, f, pr in urls:
        sm.append(f"<url><loc>{SITE}{u}</loc><changefreq>{f}</changefreq><priority>{pr}</priority></url>")
    for n in news[:400]:
        sm.append(f"<url><loc>{SITE}{n['url']}</loc><lastmod>{n['t']:%Y-%m-%d}</lastmod><priority>0.6</priority></url>")
    for m in ms:
        sm.append(f"<url><loc>{SITE}{m['url']}</loc><lastmod>{m['kickoff']:%Y-%m-%d}</lastmod><priority>{'0.8' if not m.get('finished') else '0.5'}</priority></url>")
    sm.append("</urlset>")
    _write(DOCS / "sitemap.xml", "\n".join(sm))
    _write(DOCS / "robots.txt", f"User-agent: *\nAllow: /\nDisallow: /betbot/admin.html\nDisallow: /betbot/profile.html\n\nSitemap: {SITE}sitemap.xml\n")
    print(f"Страницы сайта: новостей {len(news)}, прогнозов {len(ms)}, изменено {changed}")
    upcoming = sorted([m for m in ms if not m.get("finished") and m["kickoff"] > now - pd.Timedelta(hours=2)], key=lambda m: m["kickoff"])[:6]
    return {"news": "".join(_news_card(n, "") for n in news[:6]), "preds": "".join(_match_card(m, "") for m in upcoming)}
