"""Дополнительные разделы сайта: страницы команд, калькуляторы и «Школа ставок».

Всё это — отдельные страницы для поисковиков: «Спартак прогнозы», «калькулятор экспресса», «что такое тотал».
"""
from __future__ import annotations

import html as H
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import directory
from .pages import DOCS, EMOJI, MONTHS, SITE, SPORT_RU, _crumbs, _match_card, _news_card, _write, page, slug


# ── страницы команд ───────────────────────────────────────────────────────────

def team_url(sport: str, name: str) -> str:
    return f"teams/{sport}-{slug(name, 50)}.html"


def build_teams(ms: list[dict], news: list[dict], now: pd.Timestamp) -> list[str]:
    """Страница на каждую команду, по которой у бота есть прогнозы. Возвращает адреса для sitemap."""
    upcoming = json.loads((DOCS / "matches.json").read_text(encoding="utf-8")) if (DOCS / "matches.json").exists() else []
    teams: dict[tuple[str, str], dict] = {}
    for m in ms:
        for side, logo in (("home", "hl"), ("away", "al")):
            t = teams.setdefault((m["sport"], m[side]), {"name": m[side], "sport": m["sport"], "logo": None, "leagues": set(), "preds": []})
            t["preds"].append(m)
            t["logo"] = t["logo"] or m.get(logo)
            if m.get("league"):
                t["leagues"].add(m["league"])
    for u in upcoming:
        for side, logo in (("home", "hl"), ("away", "al")):
            t = teams.get((u["sport"], u[side]))
            if t:
                t.setdefault("next", []).append(u)
                t["logo"] = t["logo"] or u.get(logo)
                t["leagues"].add(u["league"])
    urls = []
    for (sport, name), t in teams.items():
        url = team_url(sport, name)
        _write(DOCS / url, _team_page(t, news, url))
        urls.append(url)
    _write(DOCS / "teams" / "index.html", _teams_index(teams))
    urls.append("teams/")
    return urls


def _team_page(t: dict, news: list[dict], url: str) -> str:
    name, sport = t["name"], t["sport"]
    preds = sorted(t["preds"], key=lambda m: m["kickoff"], reverse=True)
    done = [m for m in preds if m.get("finished")]
    hits = sum(1 for m in done if m.get("hit"))
    nxt = sorted(t.get("next", []), key=lambda u: u["kickoff"])[:6]
    about = [n for n in news if name.lower() in n["title"].lower()][:6]
    league = ", ".join(sorted(t["leagues"]))[:120]
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Команды", "teams/"), (name, None)])

    def nxt_card(u: dict) -> str:
        k = pd.Timestamp(u["kickoff"]).tz_convert("Europe/Moscow")
        return (f'<a class="card mc" href="../{H.escape(u["url"])}"><div class="t"><span>{EMOJI.get(u["sport"], "")} {H.escape(u["league"])}</span>'
                f'<span>{k.day} {MONTHS[k.month - 1]}, {k:%H:%M}</span></div><b>{H.escape(u["home"])} — {H.escape(u["away"])}</b>'
                f'<span class="p">{"🎯 " + H.escape(u["tip"]) if u.get("tip") else "📺 Смотреть онлайн"}</span></a>')

    logo = f'<img src="{H.escape(t["logo"])}" alt="{H.escape(name)}" style="width:72px;height:72px;object-fit:contain;background:#fff;border-radius:50%;padding:6px">' if t["logo"] else ""
    stat = f"Бот давал прогнозы на {len(preds)} матчей с участием команды «{name}»" + (f": из {len(done)} рассчитанных зашло {hits} ({round(hits / len(done) * 100)}%)." if done else ".")
    link = directory.team_link(sport, name, "../")
    live_btn = (f'<a class="btn gold" href="{H.escape(link)}" style="margin-top:8px">📊 {"Профиль, рейтинг и матчи" if sport == "tennis" else "Расписание, состав, таблица и статистика"} →</a>'
                if link else "")
    body = f"""{crumbs}<div class="card" style="display:flex;gap:16px;align-items:center;margin-top:10px">{logo}<div>
<span class="tag">{EMOJI.get(sport, "")} {SPORT_RU.get(sport, "")}{" · " + H.escape(league) if league else ""}</span>
<h1 style="margin:4px 0">{H.escape(name)}: <span>прогнозы и матчи</span></h1><p class="muted small">{H.escape(stat)}</p>{live_btn}</div></div>
{('<h2>📅 Ближайшие матчи</h2><div class="grid">' + "".join(nxt_card(u) for u in nxt) + "</div>") if nxt else ""}
<h2>🎯 Прогнозы бота на матчи «{H.escape(name)}»</h2><div class="grid">{"".join(_match_card(m, "../") for m in preds[:24])}</div>
{('<h2>📰 Новости</h2><div class="grid">' + "".join(_news_card(n, "../") for n in about) + "</div>") if about else ""}
<div class="row" style="margin-top:16px"><a class="btn red" href="../matches.html">📺 Матчи онлайн</a><a class="btn gold" href="https://t.me/aistavvit">📲 Прогнозы в Telegram</a></div>"""
    ld = {"@context": "https://schema.org", "@type": "SportsTeam", "name": name, "sport": SPORT_RU.get(sport, ""), "url": SITE + url,
          **({"logo": t["logo"]} if t["logo"] else {})}
    desc = (f"{name}: прогнозы на ближайшие матчи, результаты и статистика прогнозов, новости. {SPORT_RU.get(sport, '')}"
            f"{', ' + league if league else ''}. Бесплатно от АИ СТАВИТ.")
    return page("../", f"{name} — прогнозы на матчи, результаты и новости · АИ СТАВИТ", desc, SITE + url, body, "teams", t["logo"], [ld, bc])


def _teams_index(teams: dict) -> str:
    """Каталог команд плитками: логотип, название, сколько прогнозов; быстрый фильтр и вкладки по видам спорта."""
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Команды", None)])
    blocks, tabs = "", []
    for sp in ("football", "hockey", "basketball", "tennis"):
        by = defaultdict(list)
        for (s, name), t in teams.items():
            if s == sp:
                by[sorted(t["leagues"])[0] if t["leagues"] else "Другие"].append((name, t))
        if not by:
            continue
        n_sp = sum(len(v) for v in by.values())
        tabs.append(f'<a href="#{sp}">{EMOJI[sp]} {SPORT_RU[sp]} <b>{n_sp}</b></a>')
        blocks += f'<section class="tsec" id="{sp}"><h2>{EMOJI[sp]} {SPORT_RU[sp]}</h2>'
        # крупные турниры (где больше команд) — выше
        for lg in sorted(by, key=lambda x: (x == "Другие", -len(by[x]), x)):
            tiles = "".join(
                f'<a class="tt" href="../{team_url(sp, n)}" data-n="{H.escape(n.lower())}">'
                + (f'<img src="{H.escape(t["logo"])}" alt="" loading="lazy">' if t.get("logo") else f'<span class="ph">{EMOJI[sp]}</span>')
                + f'<span><b>{H.escape(n)}</b><small>{len(t["preds"])} прогн.</small></span></a>'
                for n, t in sorted(by[lg]))
            blocks += f'<div class="tlg"><h3>{H.escape(lg)} <span>{len(by[lg])}</span></h3><div class="tgrid">{tiles}</div></div>'
        blocks += "</section>"
    style = """<style>
.ttabs{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 4px}.ttabs a{padding:8px 14px;border-radius:999px;background:rgba(255,255,255,.05);border:1px solid var(--line);text-decoration:none;font-weight:800;font-size:13px}
.ttabs a b{color:var(--gold);margin-left:4px}.ttabs a:hover{background:rgba(255,255,255,.1)}
.tfind{position:relative;margin:12px 0}.tfind input{width:100%;padding:13px 16px 13px 44px;border-radius:16px;border:1px solid var(--line);background:rgba(255,255,255,.06);color:#fff;font:700 15px Montserrat,sans-serif;outline:none}
.tfind input:focus{border-color:var(--gold)}.tfind:before{content:"🔍";position:absolute;left:15px;top:50%;transform:translateY(-50%)}
.tlg{margin:14px 0 4px}.tlg h3{font-size:12px;letter-spacing:.8px;text-transform:uppercase;color:var(--muted);font-weight:800;margin:0 0 8px}.tlg h3 span{color:var(--gold);margin-left:4px}
.tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}
.tt{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card));border:1px solid var(--line);text-decoration:none;
  transition:transform .2s,border-color .2s,background .2s;min-width:0}
.tt:hover{transform:translateY(-2px);border-color:rgba(255,196,0,.4)}
.tt img,.tt .ph{width:34px;height:34px;flex:none;border-radius:10px;background:#fff;object-fit:contain;padding:3px;display:grid;place-items:center;font-size:18px}
.tt .ph{background:rgba(255,255,255,.08)}.tt span{min-width:0}.tt b{display:block;font-size:13.5px;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tt small{color:var(--muted);font-size:11px;font-weight:600}
@media(max-width:520px){.tgrid{grid-template-columns:1fr 1fr}.tt{padding:8px}.tt img,.tt .ph{width:28px;height:28px}}
</style>"""
    script = """<script>
document.getElementById("tq").oninput = e => { const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(".tt").forEach(a => a.style.display = !q || a.dataset.n.includes(q) ? "" : "none");
  document.querySelectorAll(".tlg").forEach(g => g.style.display = [...g.querySelectorAll(".tt")].some(a => a.style.display !== "none") ? "" : "none");
  document.querySelectorAll(".tsec").forEach(s => s.style.display = [...s.querySelectorAll(".tlg")].some(g => g.style.display !== "none") ? "" : "none"); };
</script>"""
    body = f"""{style}{crumbs}<h1>Команды и игроки: <span>прогнозы на матчи</span></h1>
<p class="lead">Команды и теннисисты, на которых бот давал прогнозы: ближайшие матчи, все прогнозы с результатами и новости. Любую другую команду или игрока ищите в <a href="../leagues.html" style="color:var(--gold)">поиске по всем турнирам</a>.</p>
<div class="tfind"><input id="tq" type="search" placeholder="Быстрый поиск по названию…" autocomplete="off"></div>
<div class="ttabs">{"".join(tabs)}<a href="../leagues.html">🏆 Все турниры и таблицы</a></div>{blocks}{script}"""
    return page("../", "Прогнозы на матчи команд: футбол, хоккей, НБА, теннис — АИ СТАВИТ",
                "Все команды и теннисисты с прогнозами АИ СТАВИТ: ближайшие матчи, результаты прогнозов и новости. Футбол, НХЛ, НБА, теннис.",
                SITE + "teams/", body, "teams", None, [bc])


# ── калькуляторы ──────────────────────────────────────────────────────────────

TOOLS_JS = r"""
<script>
const $ = s => document.querySelector(s), num = v => parseFloat(String(v).replace(",", "."));
// экспресс
function exRow(v = "") { const d = document.createElement("div"); d.className = "row"; d.innerHTML = `<input class="inp ex" type="number" step="0.01" min="1.01" placeholder="Кэф, например 1.85" value="${v}" style="flex:1"><button class="btn ghost rm" type="button">✕</button>`; $("#exl").appendChild(d); d.querySelector(".rm").onclick = () => { d.remove(); ex(); }; d.querySelector("input").oninput = ex; }
function ex() { const ks = [...document.querySelectorAll(".ex")].map(i => num(i.value)).filter(k => k > 1), st = num($("#exs").value) || 0;
  const k = ks.reduce((a, b) => a * b, 1); $("#exr").innerHTML = ks.length ? `Итоговый кэф: <b>${k.toFixed(2)}</b> · выплата: <b>${(k * st).toFixed(0)} ₽</b> · чистая прибыль: <b>${(k * st - st).toFixed(0)} ₽</b><br><span class="muted">Шанс, что зайдут все ${ks.length} событий (по кэфам, с маржой): ${(100 / k).toFixed(1)}%</span>` : "Добавьте кэфы событий"; }
// кэф ↔ вероятность
function kp() { const k = num($("#kpk").value), p = num($("#kpp").value);
  $("#kpr").innerHTML = (k > 1 ? `Кэф ${k.toFixed(2)} → вероятность <b>${(100 / k).toFixed(1)}%</b>` : "") + (p > 0 && p < 100 ? `${k > 1 ? "<br>" : ""}Вероятность ${p}% → справедливый кэф <b>${(100 / p).toFixed(2)}</b>` : ""); }
// маржа
function mg() { const ks = [$("#m1").value, $("#m2").value, $("#m3").value].map(num).filter(k => k > 1);
  if (ks.length < 2) { $("#mgr").textContent = "Введите кэфы на все исходы (2 или 3)"; return; }
  const s = ks.reduce((a, k) => a + 1 / k, 0); $("#mgr").innerHTML = `Маржа букмекера: <b>${((s - 1) * 100).toFixed(1)}%</b><br>Честные вероятности: ${ks.map(k => (100 / k / s).toFixed(1) + "%").join(" · ")}`; }
// банк и Келли
function bk() { const b = num($("#bkb").value), pc = num($("#bkp").value), p = num($("#bkpr").value) / 100, k = num($("#bkk").value);
  let h = b > 0 && pc > 0 ? `Ставка ${pc}% банка = <b>${(b * pc / 100).toFixed(0)} ₽</b>` : "";
  if (p > 0 && p < 1 && k > 1) { const f = (p * k - 1) / (k - 1); h += `${h ? "<br>" : ""}${f > 0 ? `По Келли: <b>${(f * 100).toFixed(1)}%</b> банка, безопаснее — четверть: <b>${(f * 25).toFixed(1)}%</b>${b > 0 ? ` (${(b * f / 4).toFixed(0)} ₽)` : ""}` : "По Келли ставка не выгодна — пропустите"}`; }
  $("#bkr").innerHTML = h || "Введите банк и процент"; }
// value
function vl() { const p = num($("#vlp").value) / 100, k = num($("#vlk").value);
  if (!(p > 0 && p < 1 && k > 1)) { $("#vlr").textContent = "Введите вашу оценку шанса и кэф"; return; }
  const v = (p * k - 1) * 100; $("#vlr").innerHTML = v > 0 ? `✅ Value-ставка: перевес <b>+${v.toFixed(1)}%</b> — на дистанции в плюс` : `❌ Не value: ${v.toFixed(1)}% — букмекер оценивает исход выше вашего шанса`; }
document.querySelectorAll("input").forEach(i => i.addEventListener("input", () => { ex(); kp(); mg(); bk(); vl(); }));
$("#exa").onclick = () => exRow(); exRow("1.85"); exRow("1.70"); ex(); kp(); mg(); bk(); vl();
</script>"""


def build_tools() -> str:
    crumbs, bc = _crumbs("", [("Главная", ""), ("Калькуляторы", None)])
    card = lambda h, inner, rid: f'<div class="card"><h2 style="margin-top:0">{h}</h2>{inner}<div id="{rid}" style="margin-top:10px;font-size:15px"></div></div>'
    inp = lambda i, ph, v="", step="0.01": f'<input class="inp" id="{i}" type="number" step="{step}" placeholder="{ph}" value="{v}" style="flex:1;min-width:120px">'
    body = f"""{crumbs}<h1>Калькуляторы <span>для ставок</span></h1>
<p class="lead">Посчитайте экспресс, переведите коэффициент в вероятность, узнайте маржу букмекера, размер ставки и есть ли в ставке ценность.</p>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-top:16px">
{card("🧮 Калькулятор экспресса", f'<div id="exl"></div><div class="row"><button class="btn ghost" id="exa" type="button">+ событие</button>{inp("exs", "Сумма ставки, ₽", "1000", "1")}</div>', "exr")}
{card("🔁 Кэф ↔ вероятность", f'<div class="row">{inp("kpk", "Кэф", "1.85")}{inp("kpp", "Вероятность, %", "", "0.1")}</div>', "kpr")}
{card("📉 Маржа букмекера", f'<div class="row">{inp("m1", "П1", "2.10")}{inp("m2", "Х", "3.40")}{inp("m3", "П2", "3.60")}</div>', "mgr")}
{card("💰 Банк и критерий Келли", f'<div class="row">{inp("bkb", "Банк, ₽", "10000", "1")}{inp("bkp", "Ставка, % банка", "2", "0.1")}</div><div class="row">{inp("bkpr", "Ваш шанс, %", "55", "0.1")}{inp("bkk", "Кэф", "2.00")}</div>', "bkr")}
{card("💎 Есть ли value?", f'<div class="row">{inp("vlp", "Ваш шанс, %", "55", "0.1")}{inp("vlk", "Кэф", "1.95")}</div>', "vlr")}
</div>
<p class="muted small" style="margin-top:14px">Как пользоваться этими цифрами — в <a href="school/">Школе ставок</a>. Ставки — это риск, играйте только на то, что готовы потерять. 18+.</p>{TOOLS_JS}"""
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": "Калькуляторы для ставок АИ СТАВИТ", "applicationCategory": "UtilitiesApplication",
          "operatingSystem": "Any", "url": SITE + "tools.html", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"}}
    return page("", "Калькулятор ставок: экспресс, маржа, вероятность, Келли — АИ СТАВИТ",
                "Бесплатные калькуляторы для ставок на спорт: калькулятор экспресса, перевод коэффициента в вероятность, маржа букмекера, размер ставки по Келли и проверка value.",
                SITE + "tools.html", body, "tools", None, [ld, bc])


# ── школа ставок ──────────────────────────────────────────────────────────────

ARTICLES = [
    ("iskhody-p1-x-p2", "Исходы П1, Х, П2 и двойной шанс: как читать линию",
     "Что означают П1, Х, П2, 1Х, Х2 и 12 в ставках на спорт — простыми словами с примерами.",
     """<p><b>П1</b> — победа первой команды (хозяев), <b>Х</b> — ничья, <b>П2</b> — победа второй команды (гостей). Это основной рынок футбола, его ещё называют «1Х2».</p>
<p><b>Двойной шанс</b> страхует ставку: <b>1Х</b> — хозяева не проиграют (победа или ничья), <b>Х2</b> — гости не проиграют, <b>12</b> — не будет ничьей. Кэф на двойной шанс ниже, зато ставка заходит чаще.</p>
<h2>Пример</h2><p>«Галатасарай — Амедспор»: П1 1.41, Х 5.00, П2 6.50. Если поставить П1 и Галатасарай победит — выплата 1.41 × сумма. При ничьей ставка проигрывает, а вот 1Х (≈1.10) зашла бы.</p>
<h2>Что учесть</h2><p>В хоккее и баскетболе П1/П2 часто считаются <b>с учётом овертайма</b> — смотрите пометку «с ОТ». В футболе ставки считаются по основному времени, без дополнительного.</p>"""),
    ("chto-takoe-total", "Что такое тотал (ТБ и ТМ) в ставках",
     "Тотал больше и тотал меньше: что значит ТБ 2.5 и ТМ 2.5, как считается возврат и где тоталы выгоднее.",
     """<p><b>Тотал</b> — общее количество голов (шайб, очков) в матче. <b>ТБ</b> — тотал больше, <b>ТМ</b> — тотал меньше. Ставка «ТБ 2.5» зайдёт, если забьют 3 мяча и больше, «ТМ 2.5» — если 2 и меньше.</p>
<h2>Целый тотал и возврат</h2><p>Если линия целая (ТБ 2), а забили ровно 2 — это <b>возврат</b>: деньги вернут. Поэтому половинки (.5) не бывают «в ноль».</p>
<h2>Индивидуальный тотал</h2><p><b>ИТ1 больше 1.5</b> — первая команда забьёт минимум 2. Удобно, когда фаворит атакует, а соперник надёжно обороняется.</p>
<h2>Откуда брать тотал</h2><p>Бот считает ожидаемые голы (xG) обеих команд: например, «xG 2.4 : 1.0» значит, что в среднем ждём около 3.4 гола — ТБ 2.5 выглядит логично. Шансы по всем тоталам есть на странице каждого <a href="../predictions/">прогноза</a>.</p>"""),
    ("chto-takoe-fora", "Что такое фора в ставках: Ф1 (−1.5), Ф2 (+1.5)",
     "Фора — гандикап в ставках на спорт: как считать отрицательную и положительную фору, примеры для футбола и хоккея.",
     """<p><b>Фора</b> — это виртуальная прибавка или вычет голов команде. <b>Ф1 (−1.5)</b>: из голов первой команды вычитаем 1.5 — ставка зайдёт, если она победит с разницей 2+. <b>Ф2 (+1.5)</b>: ко второй команде прибавляем 1.5 — она может проиграть в 1 гол, и ставка всё равно зайдёт.</p>
<h2>Пример</h2><p>Счёт 2:1. Ф1 (−1.5): 2 − 1.5 = 0.5 &lt; 1 — не зашла. Ф2 (+1.5): 1 + 1.5 = 2.5 &gt; 2 — зашла.</p>
<h2>Целая фора</h2><p>Ф1 (−1) при победе ровно в 1 гол — возврат. При победе в 2 — выигрыш.</p>
<h2>Когда фора полезна</h2><p>Против явного фаворита кэф на П1 бывает 1.15 — играть его невыгодно. Ф1 (−1.5) даёт кэф около 2.0, если уверены в крупной победе.</p>"""),
    ("ekspress", "Что такое экспресс и почему он рискованный",
     "Экспресс в ставках: как считается коэффициент, почему проходимость падает с каждым событием и как играть экспрессы разумно.",
     """<p><b>Экспресс</b> — одна ставка на несколько событий сразу. Коэффициенты перемножаются: 1.85 × 1.70 × 1.60 ≈ 5.03. Но зайти должны <b>все</b> события — одна ошибка, и проигран весь экспресс.</p>
<h2>Почему это риск</h2><p>Если каждое событие заходит с шансом 55%, то два подряд — 30%, три — 17%, пять — всего 5%. А маржа букмекера тоже перемножается, поэтому на дистанции экспрессы обычно проигрывают одиночным ставкам.</p>
<h2>Как играть разумно</h2><p>Держите экспрессы из 2–3 событий, ставьте на них меньшую часть банка, а основную игру ведите ординарами. Посчитать итоговый кэф и шанс можно в <a href="../tools.html">калькуляторе экспресса</a>.</p>"""),
    ("koefficient-i-veroyatnost", "Как перевести коэффициент в вероятность",
     "Формула: вероятность = 1 / коэффициент. Как считать маржу букмекера и «честные» шансы.",
     """<p>Коэффициент — это обратная вероятность: <b>шанс = 1 / кэф</b>. Кэф 2.00 — это 50%, кэф 1.50 — 66.7%, кэф 4.00 — 25%.</p>
<h2>Маржа</h2><p>Сложите обратные кэфы всех исходов: 1/2.10 + 1/3.40 + 1/3.60 ≈ 1.05. Лишние 5% — это <b>маржа</b>, заработок букмекера. Чтобы получить честные шансы, разделите каждую вероятность на эту сумму.</p>
<h2>Зачем это нужно</h2><p>Если вы считаете, что шанс исхода выше, чем «зашит» в кэф, — ставка выгодна. Бот на каждой странице прогноза показывает свой шанс рядом с кэфом. Проверить любые цифры можно в <a href="../tools.html">калькуляторе</a>.</p>"""),
    ("value-stavki", "Что такое value-ставка (ставка с перевесом)",
     "Value-ставка — когда реальный шанс исхода выше, чем предполагает коэффициент. Формула, примеры и как бот ищет value.",
     """<p><b>Value</b> — ставка, где ваш шанс × кэф больше 1. Например, вы оцениваете победу в 55%, а кэф 1.95: 0.55 × 1.95 = 1.07 — перевес <b>+7%</b>. На дистанции такие ставки приносят прибыль, даже если отдельные проигрывают.</p>
<h2>Главное — честная оценка</h2><p>Value имеет смысл, только если ваша оценка точнее линии букмекера. Бот считает шансы по модели (форма, сила команд, ожидаемые голы) и сравнивает с рынком — такие ставки он публикует как «💎 Value дня».</p>
<h2>CLV</h2><p>Хороший признак — когда кэф на ваш исход к началу матча <b>падает</b>: рынок «догоняет» вашу оценку. Это называется CLV, бот считает его в <a href="../">статистике</a>.</p>"""),
    ("bank-menedzhment", "Банк-менеджмент: сколько ставить, чтобы не проиграть всё",
     "Как управлять банком в ставках: фиксированный процент, критерий Келли и правила, которые спасают от минуса.",
     """<p><b>Банк</b> — сумма, которую вы готовы выделить на ставки и потерять без последствий. Главное правило — ставить <b>1–3% банка</b> на одну ставку. Тогда даже серия из 10 проигрышей не обнулит счёт.</p>
<h2>Критерий Келли</h2><p>Формула подбирает размер ставки по вашему перевесу: f = (шанс × кэф − 1) / (кэф − 1). Полный Келли слишком агрессивен, поэтому опытные игроки ставят его четверть. Посчитать можно в <a href="../tools.html">калькуляторе</a>.</p>
<h2>Правила</h2><p>Не отыгрывайтесь после проигрыша, не повышайте ставки на эмоциях и ведите учёт. Бот сам рекомендует размер ставки в каждом прогнозе (1–3% банка) и ведёт виртуальный банк на <a href="../">главной</a>. Ставки — только 18+ и только на свободные деньги.</p>"""),
]


def build_school() -> list[str]:
    urls = []
    cards = ""
    for sl, title, desc, html_ in ARTICLES:
        url = f"school/{sl}.html"
        crumbs, bc = _crumbs("../", [("Главная", ""), ("Школа ставок", "school/"), (title, None)])
        others = "".join(f'<li><a href="{s2}.html">{H.escape(t2)}</a></li>' for s2, t2, _, _ in ARTICLES if s2 != sl)
        body = (f'{crumbs}<article class="post"><span class="tag">📚 Школа ставок</span><h1>{H.escape(title)}</h1>'
                f'<p class="lead">{H.escape(desc)}</p><div class="body" style="margin-top:14px">{html_}</div></article>'
                f'<div class="row" style="margin-top:18px"><a class="btn gold" href="../predictions/">🎯 Прогнозы на сегодня</a><a class="btn ghost" href="../tools.html">🧮 Калькуляторы</a></div>'
                f'<h2>Ещё в школе ставок</h2><div class="card"><ul style="margin-left:18px;line-height:2">{others}</ul></div>')
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": title, "description": desc, "inLanguage": "ru",
              "author": {"@type": "Organization", "name": "АИ СТАВИТ"}, "publisher": {"@type": "Organization", "name": "АИ СТАВИТ", "url": SITE},
              "mainEntityOfPage": SITE + url}
        _write(DOCS / url, page("../", f"{title} — Школа ставок АИ СТАВИТ", desc, SITE + url, body, "school", None, [ld, bc], "article"))
        urls.append(url)
        cards += f'<a class="card nc" href="{sl}.html"><div class="b"><span class="tag">📚 Урок</span><b>{H.escape(title)}</b><p>{H.escape(desc)}</p></div></a>'
    crumbs, bc = _crumbs("../", [("Главная", ""), ("Школа ставок", None)])
    body = (f'{crumbs}<h1>Школа ставок: <span>просто о сложном</span></h1><p class="lead">Короткие уроки для новичков: исходы, тоталы, форы, экспрессы, '
            f'value и управление банком — с примерами из реальных матчей.</p><div class="grid" style="margin-top:16px">{cards}</div>')
    _write(DOCS / "school" / "index.html", page("../", "Школа ставок на спорт для новичков — АИ СТАВИТ",
           "Как делать ставки на спорт: что такое тотал, фора, экспресс, value-ставки, как считать вероятность и управлять банком. Простые уроки с примерами.",
           SITE + "school/", body, "school", None, [bc]))
    urls.append("school/")
    return urls
