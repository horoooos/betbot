"""Публичная страница со статистикой бота (GitHub Pages, бесплатно): docs/index.html.

Каждый опубликованный прогноз и его итог — без фильтров и подчисток. Пересобирается раз в день.
"""
import json
import os
from html import escape
from pathlib import Path

import pandas as pd

from . import pro
from .sports import EMOJI, SPORT_RU

OUT = Path(__file__).resolve().parent.parent / "docs" / "index.html"
MATCHES = OUT.parent / "matches.json"  # матчи с прогнозом для страницы «Смотреть матчи онлайн»
CHANNEL = os.environ.get("TELEGRAM_CHAT_ID", "")
if not CHANNEL.startswith("@"):  # в секрете может быть числовой id — тогда берём публичное имя канала
    CHANNEL = "@aistavvit"
SITE = "https://horoooos.github.io/betbot/"


def _hits(col: pd.Series) -> pd.Series:
    return col.astype(str).str.lower().isin(["true", "1", "1.0"])


def _roi(df: pd.DataFrame) -> float:
    """ROI только по прогнозам с настоящим кэфом — расчётные «≈» в прибыль не идут."""
    real = df[~df["main_est"].astype(str).str.lower().isin(["true", "1", "1.0"])] if "main_est" in df else df
    if real.empty:
        return 0.0
    h = _hits(real["main_hit"])
    return float(100 * (h * (real["main_odds"].astype(float) - 1) - (~h)).sum() / len(real))


def _chart(curve: list[float]) -> str:
    """Виртуальный банк: линия с градиентной заливкой и отметкой старта (SVG)."""
    if len(curve) < 2:
        return ""
    w, h, pad = 720, 240, 30
    lo, hi = min(curve + [pro.BANK_START]), max(curve + [pro.BANK_START])
    if hi - lo < 1:
        hi, lo = hi + 1, lo - 1
    xs = [pad + i * (w - 2 * pad) / (len(curve) - 1) for i in range(len(curve))]
    ys = [h - pad - (v - lo) * (h - 2 * pad) / (hi - lo) for v in curve]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{xs[0]:.1f},{h - pad} {pts} {xs[-1]:.1f},{h - pad}"
    base = h - pad - (pro.BANK_START - lo) * (h - 2 * pad) / (hi - lo)
    up = curve[-1] >= pro.BANK_START
    c = "#2ecc71" if up else "#ff5a5a"
    money = lambda v: f"{v:,.0f}".replace(",", " ")
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Виртуальный банк">'
            f'<defs><linearGradient id="bk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></linearGradient></defs>'
            f'<line x1="{pad}" x2="{w - pad}" y1="{base:.1f}" y2="{base:.1f}" class="base"/>'
            f'<text x="{w - pad}" y="{base - 6:.1f}" class="lbl" text-anchor="end">старт {money(pro.BANK_START)} ₽</text>'
            f'<polygon points="{area}" fill="url(#bk)"/>'
            f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="6" fill="{c}" stroke="#0b1024" stroke-width="3"/>'
            f'<text x="{pad}" y="16" class="lbl">{money(hi)} ₽</text><text x="{pad}" y="{h - 8}" class="lbl">{money(lo)} ₽</text>'
            "</svg>")


CSS = """
:root{--bg:#070b1a;--card:#111936;--card2:#18224a;--line:rgba(255,255,255,.09);--ink:#fff;--muted:#9aa6cc;--gold:#ffc400;--good:#2ecc71;--bad:#ff5a5a;--live:#ff4646}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(1100px 600px at 85% -10%,#1d2a66 0%,transparent 60%),radial-gradient(900px 520px at -10% 5%,#3a1d5a 0%,transparent 55%),var(--bg);
 background-attachment:fixed;color:var(--ink);font:15px/1.5 Montserrat,system-ui,sans-serif;min-height:100vh}
a{color:inherit}
main{max-width:1080px;margin:0 auto;padding:18px 16px 96px}
.hero{margin:30px 0 8px;display:grid;grid-template-columns:1.25fr 1fr;gap:26px;align-items:center}
h1{font-size:clamp(28px,5vw,46px);line-height:1.08;font-weight:900}
h1 span{background:linear-gradient(90deg,#ffc400,#ff7a3d);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{color:var(--muted);margin:12px 0 18px;max-width:560px}
.btns{display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:8px;padding:13px 20px;border-radius:14px;font-weight:800;text-decoration:none;white-space:nowrap}
.btn.gold{background:linear-gradient(90deg,#ffc400,#ff9f1a);color:#1a1405;box-shadow:0 10px 30px rgba(255,170,0,.25)}
.btn.ghost{border:1px solid var(--line);background:rgba(255,255,255,.04)}
.ringbox{background:linear-gradient(160deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:26px;padding:22px;display:flex;align-items:center;gap:20px}
.ring{--p:50;width:150px;height:150px;border-radius:50%;flex:none;display:grid;place-items:center;
 background:conic-gradient(var(--good) calc(var(--p)*1%),rgba(255,255,255,.08) 0);position:relative}
.ring::before{content:"";position:absolute;inset:14px;border-radius:50%;background:var(--card)}
.ring b{position:relative;font-size:38px;font-weight:900}.ring small{position:relative;display:block;font-size:11px;color:var(--muted);font-weight:700;text-align:center;margin-top:-6px}
.ringtxt h3{font-size:18px;font-weight:900}.ringtxt p{color:var(--muted);font-size:13px;margin-top:6px}
.streak{display:inline-block;margin-top:10px;background:rgba(255,196,0,.14);color:var(--gold);font-weight:800;font-size:12px;border-radius:999px;padding:5px 11px}
.live{margin-top:26px;background:linear-gradient(160deg,rgba(255,70,70,.12),var(--card));border:1px solid rgba(255,70,70,.35);border-radius:22px;padding:16px}
.live h2{margin:0 0 12px}.live .row{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.lm{display:block;text-decoration:none;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 12px}
.lm .t{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.4px}
.lm .t .l{color:var(--live)}.lm .n{display:flex;justify-content:space-between;gap:8px;font-weight:800;margin-top:4px}
.lm .n span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lm .w{font-size:12px;color:var(--gold);font-weight:800;margin-top:6px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--live);box-shadow:0 0 10px var(--live);animation:p 1.2s infinite;margin-right:4px}
@keyframes p{50%{opacity:.35}}
h2{font-size:19px;font-weight:900;margin:34px 0 12px;display:flex;align-items:center;gap:8px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:26px}
.kpi{background:linear-gradient(160deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:18px;padding:15px}
.kpi .i{font-size:20px}.kpi .v{font-size:26px;font-weight:900;margin-top:4px}.kpi .l{color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.kpi .s{color:var(--muted);font-size:12px;margin-top:2px}.kpi .v.good{color:var(--good)}.kpi .v.bad{color:var(--bad)}
.card{background:linear-gradient(160deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:20px;padding:16px}
svg{width:100%;height:auto;display:block}svg .base{stroke:rgba(255,255,255,.25);stroke-dasharray:5 6}svg .lbl{fill:var(--muted);font-size:12px;font-family:Montserrat,sans-serif}
.muted{color:var(--muted)}.small{font-size:12px}
.heat{display:grid;grid-template-columns:repeat(14,1fr);gap:6px}
.heat i{aspect-ratio:1;border-radius:6px;background:rgba(255,255,255,.06);position:relative}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:12px;color:var(--muted)}.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:12px;height:12px;border-radius:3px;display:inline-block}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.sp{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.spc{background:linear-gradient(160deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:18px;padding:14px}
.spc .e{font-size:26px}.spc .n{font-weight:800;margin-top:2px}.spc .p{font-size:28px;font-weight:900;margin-top:6px}
.bar{height:8px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:8px}.bar b{display:block;height:100%;border-radius:4px}
.spc .s{color:var(--muted);font-size:12px;margin-top:6px}
.mk{display:grid;grid-template-columns:minmax(0,1fr) 120px 46px;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
.mk:last-child{border-bottom:0}.mk span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}.mk .c{color:var(--muted);font-size:12px}
.mk .pc{text-align:right;font-weight:800}
.best{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}.best:last-child{border-bottom:0}
.best .o{flex:none;background:rgba(46,204,113,.15);color:var(--good);font-weight:900;border-radius:10px;padding:6px 10px;min-width:62px;text-align:center}
.best .m{min-width:0}.best .m b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.best .m span{color:var(--muted);font-size:12px}
.feed{display:grid;gap:8px}
.fr{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.fr .ok{font-size:18px}.fr .m b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
.fr .m span{color:var(--muted);font-size:12px}.fr .r{text-align:right;font-size:12px;color:var(--muted)}.fr .r b{display:block;font-size:14px;color:var(--ink)}
.more{display:none}.showall .more{display:grid}
.mbtn{margin-top:10px;background:none;border:1px solid var(--line);color:var(--ink);font:700 13px Montserrat,sans-serif;border-radius:12px;padding:9px 14px;cursor:pointer}
.cta{margin-top:34px;display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;padding:20px;border-radius:22px;
 background:linear-gradient(120deg,rgba(255,196,0,.16),rgba(255,122,61,.08));border:1px solid rgba(255,196,0,.4)}
.cta b{font-size:18px}
.sticky{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);display:flex;gap:8px;z-index:5}
.sticky a{padding:11px 16px;border-radius:999px;font-weight:800;text-decoration:none;white-space:nowrap;box-shadow:0 10px 30px rgba(0,0,0,.45)}
.sticky .a{background:var(--live);color:#fff}.sticky .b{background:var(--gold);color:#1a1405}
@media (min-width:900px){.sticky{display:none}}
@media (max-width:760px){.hero{grid-template-columns:1fr}.ring{width:120px;height:120px}.ring b{font-size:30px}.mk{grid-template-columns:minmax(0,1fr) 80px 42px}}
footer{margin-top:34px;color:var(--muted);font-size:12px}
.online{display:inline-flex;align-items:center;gap:8px;background:rgba(46,204,113,.12);border:1px solid rgba(46,204,113,.35);color:#7dffb0;border-radius:999px;padding:5px 12px;font-size:12px;font-weight:800;margin:22px 0 0}
"""

LIVE_JS = """
(async () => {
  const box = document.getElementById("live"); if (!box) return;
  let all = []; try { all = await (await fetch("matches.json", { cache: "no-store" })).json(); } catch (e) { return; }
  const now = Date.now(), live = {};
  const paths = new Set(all.filter(m => { const k = new Date(m.kickoff).getTime(); return k - 15 * 60e3 < now && now - k < 4 * 3600e3; }).map(m => m.path));
  await Promise.all([...paths].map(async p => { try {
    const d = await (await fetch(`https://site.api.espn.com/apis/site/v2/sports/${p}/scoreboard`, { cache: "no-store" })).json();
    const put = c => { const cs = c.competitors || [], h = cs.find(x => x.homeAway === "home") || cs[0], a = cs.find(x => x.homeAway === "away") || cs[1];
      live[String(c.id)] = { state: c.status?.type?.state, clock: c.status?.displayClock || c.status?.type?.shortDetail, s: p.startsWith("tennis") ? "" : `${h?.score ?? ""}:${a?.score ?? ""}` }; };
    for (const e of d.events || []) { for (const c of e.competitions || []) put({ ...c, id: c.id || e.id }); for (const g of e.groupings || []) for (const c of g.competitions || []) put(c); }
  } catch (e) {} }));
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const EM = { football: "⚽", hockey: "🏒", basketball: "🏀", tennis: "🎾" };
  let on = all.filter(m => live[m.id]?.state === "in"), title = '<span class="dot"></span>Сейчас в эфире — смотрите онлайн';
  on.sort((a, b) => (b.tip ? 1 : 0) - (a.tip ? 1 : 0));
  if (!on.length) { on = all.filter(m => m.tip && new Date(m.kickoff).getTime() > now).slice(0, 4); title = "⏳ Ближайшие матчи с прогнозом бота"; }
  if (!on.length) { on = all.filter(m => new Date(m.kickoff).getTime() > now).slice(0, 4); title = "⏳ Ближайшие матчи онлайн"; }
  if (!on.length) return;
  const t = iso => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" });
  box.innerHTML = `<h2>${title}</h2><div class="row">${on.slice(0, 6).map(m => { const s = live[m.id];
    return `<a class="lm" href="${esc(m.url)}"><div class="t"><span>${EM[m.sport] || ""} ${esc(m.league)}</span><span class="${s?.state === "in" ? "l" : ""}">${s?.state === "in" ? "● " + esc(s.clock || "LIVE") : t(m.kickoff)}</span></div>
      <div class="n"><span>${esc(m.home)} — ${esc(m.away)}</span><span>${s?.state === "in" ? esc(s.s) : ""}</span></div>
      <div class="w">${m.tip ? "🎯 " + esc(m.tip) : "📺 Смотреть онлайн"}</div></a>`; }).join("")}</div>`;
  box.style.display = "block";
})();
"""


def build(res: pd.DataFrame, now: pd.Timestamp, blocks: dict | None = None) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if res is None or res.empty:
        res = pd.DataFrame(columns=["date", "sport", "home", "away", "score", "main_label", "main_odds", "main_hit"])
    res = res.copy()
    res["sport"] = res.get("sport", pd.Series(dtype=str)).fillna("football")
    hit = _hits(res["main_hit"]) if len(res) else pd.Series(dtype=bool)
    curve = pro.bank_curve(res)
    clv = res["main_clv"].dropna().astype(float) if "main_clv" in res else pd.Series(dtype=float)
    vn = pro.value_numbers()
    money = lambda v: f"{v:,.0f}".replace(",", " ")
    pct = 100 * hit.mean() if len(res) else 0
    roi = _roi(res) if len(res) else 0.0
    # серии заходов: текущая и лучшая
    cur = best_s = run_s = 0
    for h in hit.tolist():
        run_s = run_s + 1 if h else 0
        best_s = max(best_s, run_s)
    for h in reversed(hit.tolist()):
        if not h:
            break
        cur += 1
    week = res.assign(h=hit)[pd.to_datetime(res["date"]) >= (now.tz_localize(None).normalize() - pd.Timedelta(days=6))] if len(res) else res
    wk = f"{100 * week['h'].mean():.0f}%" if len(week) else "—"

    def kpi(icon, label, value, sub="", cls=""):
        return (f'<div class="kpi"><div class="i">{icon}</div><div class="v {cls}">{value}</div>'
                f'<div class="l">{label}</div><div class="s">{sub}</div></div>')

    kpis = "".join([
        kpi("📊", "прогнозов", f"{len(res)}", f"за последние 7 дней — {len(week)}"),
        kpi("📈", "ROI", f"{roi:+.1f}%" if len(res) else "—", "только настоящие кэфы", "good" if roi >= 0 else "bad"),
        kpi("💰", "виртуальный банк", f"{money(curve[-1])} ₽", f"старт {money(pro.BANK_START)} ₽", "good" if curve[-1] >= pro.BANK_START else "bad"),
        kpi("🗓", "заходит за неделю", wk, "последние 7 дней"),
        kpi("🧭", "CLV", f"{100 * clv.mean():+.1f}%" if len(clv) else "—",
            f"линия за ботом в {100 * (clv > 0).mean():.0f}%" if len(clv) else "копится"),
        kpi("💎", "value-ставки", f"{vn[2]:+.1f}%" if vn else "—", f"ROI · {vn[1]} из {vn[0]} зашли" if vn else "копятся"),
    ])

    # тепловая карта: 28 последних дней, цвет — доля заходов за день
    heat = ""
    if len(res):
        by_day = res.assign(h=hit, d=pd.to_datetime(res["date"]).dt.date).groupby("d")["h"].agg(["size", "sum"])
        end = now.tz_localize(None).date()
        for i in range(27, -1, -1):
            d = end - pd.Timedelta(days=i)
            if d in by_day.index:
                n, k = int(by_day.loc[d, "size"]), int(by_day.loc[d, "sum"])
                p = k / n
                col = "#2ecc71" if p >= .6 else "#9be15d" if p >= .5 else "#ffc400" if p >= .4 else "#ff5a5a"
                heat += f'<i style="background:{col};opacity:{.45 + .55 * min(n, 10) / 10:.2f}" title="{d:%d.%m}: {k} из {n} ({100 * p:.0f}%)"></i>'
            else:
                heat += f'<i title="{d:%d.%m}: прогнозов не было"></i>'

    sport_cards = ""
    for sp, g in sorted(res.groupby("sport"), key=lambda x: -len(x[1])):
        h = _hits(g["main_hit"])
        p, r = 100 * h.mean(), _roi(g)
        col = "#2ecc71" if p >= 60 else "#ffc400" if p >= 50 else "#ff5a5a"
        sport_cards += (f'<div class="spc"><div class="e">{EMOJI.get(sp, "🎯")}</div><div class="n">{SPORT_RU.get(sp, sp)}</div>'
                        f'<div class="p" style="color:{col}">{p:.0f}%</div><div class="bar"><b style="width:{p:.0f}%;background:{col}"></b></div>'
                        f'<div class="s">{len(g)} прогнозов · ROI {r:+.1f}%</div></div>')

    markets = ""
    if len(res):
        by = res.assign(h=hit).groupby("main_label")["h"].agg(["size", "mean"]).sort_values("size", ascending=False).head(10)
        for name, r in by.iterrows():
            p = 100 * r["mean"]
            col = "#2ecc71" if p >= 60 else "#ffc400" if p >= 50 else "#ff5a5a"
            markets += (f'<div class="mk"><span>{escape(str(name))} <span class="c">· {int(r["size"])}</span></span>'
                        f'<div class="bar" style="margin:0"><b style="width:{p:.0f}%;background:{col}"></b></div><span class="pc">{p:.0f}%</span></div>')

    best_rows = ""
    if len(res):
        won = res[hit].copy()
        won["o"] = won["main_odds"].astype(float)
        for _, r in won.sort_values("o", ascending=False).head(5).iterrows():
            best_rows += (f'<div class="best"><span class="o">{r["o"]:.2f}</span><div class="m"><b>{escape(str(r["home"]))} — {escape(str(r["away"]))}</b>'
                          f'<span>{EMOJI.get(r["sport"], "")} {escape(str(r["main_label"]))} · {escape(str(r["score"]))} · {escape(str(r["date"]))[5:].replace("-", ".")}</span></div></div>')

    feed = ""
    for i, (_, r) in enumerate(res.tail(60).iloc[::-1].iterrows()):
        ok = str(r["main_hit"]).lower() in ("true", "1", "1.0")
        d = escape(str(r["date"]))[5:].split("-")
        feed += (f'<div class="fr{" more" if i >= 15 else ""}"><span class="ok">{"✅" if ok else "❌"}</span>'
                 f'<div class="m"><b>{escape(str(r["home"]))} — {escape(str(r["away"]))}</b><span>{EMOJI.get(r["sport"], "")} '
                 f'{escape(str(r["main_label"]))} · кэф {float(r["main_odds"]):.2f}</span></div>'
                 f'<div class="r"><b>{escape(str(r["score"]))}</b>{d[1] + "." + d[0] if len(d) == 2 else ""}</div></div>')

    tg = f"https://t.me/{escape(CHANNEL.lstrip('@'))}"
    hit_pct = f"{pct:.0f}%" if len(res) else "—"
    seo_desc = (f"Бесплатные прогнозы на спорт от бота АИ СТАВИТ: футбол, хоккей НХЛ, баскетбол НБА, теннис, CS2 и Dota 2. "
                f"Честная статистика всех {len(res)} прогнозов: заходит {hit_pct}, ROI и виртуальный банк. Матчи онлайн.")
    streak = f'<span class="streak">🔥 Серия: {cur} подряд · рекорд {best_s}</span>' if cur >= 2 else f'<span class="streak">🏆 Рекордная серия: {best_s} подряд</span>' if best_s else ""
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>АИ СТАВИТ — бесплатные прогнозы на спорт и честная статистика</title>
<meta name="description" content="{escape(seo_desc)}">
<meta name="keywords" content="прогнозы на спорт, прогнозы на футбол, бесплатные прогнозы, ставки на спорт, прогнозы НХЛ, прогнозы НБА, прогнозы на теннис, прогнозы CS2, экспресс дня, статистика прогнозов, матчи онлайн, смотреть матч онлайн">
<meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}">
<meta property="og:type" content="website"><meta property="og:url" content="{SITE}">
<meta property="og:title" content="АИ СТАВИТ — прогнозы на спорт с честной статистикой">
<meta property="og:description" content="{escape(seo_desc)}"><meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary"><meta name="theme-color" content="#070b1a">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="site.css?v=4">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebSite","name":"АИ СТАВИТ","url":"{SITE}","description":"{escape(seo_desc)}","sameAs":["{tg}"]}}</script>
<style>{CSS}</style></head><body><main>
<nav class="topnav"><a class="logo" href="./">АИ СТАВИТ</a><div class="links"><a href="matches.html">📺 Матчи онлайн</a><a href="predictions/">🎯 Прогнозы</a><a href="news/">📰 Новости</a><a href="feed.html">💬 Лента</a><a class="me" id="navUser" href="profile.html">Войти</a></div></nav>
<section class="hero"><div>
<h1>Прогнозы на спорт <span>с честной статистикой</span></h1>
<p class="lead">Бот публикует прогноз за час до матча и сам считает итог — без удалений и подчисток. Футбол, НХЛ, НБА, теннис и киберспорт. А любой матч можно смотреть онлайн.</p>
<div class="btns"><a class="btn gold" href="matches.html">📺 Смотреть матчи онлайн</a><a class="btn ghost" href="{tg}">📲 Подписаться на {escape(CHANNEL)}</a></div>
</div><div class="ringbox"><div class="ring" style="--p:{pct:.0f}"><div><b>{hit_pct}</b><small>заходит</small></div></div>
<div class="ringtxt"><h3>{int(hit.sum()) if len(res) else 0} из {len(res)}</h3><p>основных прогнозов зашли — все до одного учтены. Обновлено {now:%d.%m.%Y %H:%M} МСК.</p>{streak}</div></div></section>
<section class="live" id="live" style="display:none"></section>
<p class="online" id="online" style="display:none"></p>
{f'<h2>🎯 Прогнозы на сегодня <a href="predictions/" class="small muted" style="font-weight:700;margin-left:auto">все прогнозы →</a></h2><div class="grid">{blocks["preds"]}</div>' if blocks and blocks.get("preds") else ""}
<div class="kpis" id="stats">{kpis}</div>
<h2>💰 Виртуальный банк</h2><div class="card">{_chart(curve) or '<span class="muted">Пока мало данных</span>'}
<p class="muted small" style="margin-top:8px">Если ставить ровно по рекомендациям бота (1–3% банка на основной прогноз), начиная с {money(pro.BANK_START)} ₽.</p></div>
<h2>🗓 Последние 4 недели</h2><div class="card"><div class="heat">{heat}</div>
<div class="legend"><span><i style="background:#2ecc71"></i>60%+ заходов</span><span><i style="background:#9be15d"></i>50–60%</span><span><i style="background:#ffc400"></i>40–50%</span><span><i style="background:#ff5a5a"></i>меньше 40%</span><span><i style="background:rgba(255,255,255,.08)"></i>без прогнозов</span></div></div>
<h2>🏅 По видам спорта</h2><div class="sp">{sport_cards}</div>
<div class="grid2"><div><h2>🎯 По типам прогнозов</h2><div class="card">{markets}</div></div>
<div><h2>🚀 Самые крупные заходы</h2><div class="card">{best_rows or '<span class="muted">Пока пусто</span>'}</div></div></div>
{f'<h2>📰 Свежие новости спорта <a href="news/" class="small muted" style="font-weight:700;margin-left:auto">все новости →</a></h2><div class="grid">{blocks["news"]}</div>' if blocks and blocks.get("news") else ""}
<h2>🧾 Последние прогнозы</h2><div class="feed" id="feed">{feed}</div>
<button class="mbtn" onclick="document.getElementById('feed').classList.toggle('showall');this.textContent=this.textContent.startsWith('Показать')?'Свернуть':'Показать ещё 45'">Показать ещё 45</button>
<div class="cta"><div><b>Прогнозы каждый день — в Telegram</b><br><span class="muted">Прогноз за час до матча, live-голы, экспрессы, разборы и честные итоги.</span></div>
<a class="btn gold" href="{tg}">📲 Подписаться</a></div>
<footer>CLV — насколько выросла вероятность нашего исхода по линии букмекеров к началу матча: плюс значит, что бот нашёл ценность раньше рынка. 18+. Прогноз — не гарантия выигрыша.</footer>
</main><div class="sticky"><a class="a" href="matches.html">📺 Онлайн</a><a class="b" href="{tg}">📲 Подписаться</a></div>
<script>{LIVE_JS}</script>
<script type="module">import("./fb.js?v=4").then(fb => {{ fb.track("index"); fb.navUser(document.getElementById("navUser")); fb.watchOnline(n => {{ const el = document.getElementById("online");
  el.style.display = "inline-flex"; el.innerHTML = `<span class="dot" style="background:#2ecc71;box-shadow:0 0 10px #2ecc71"></span>Сейчас на сайте: ${{n}}`; }}); }}).catch(() => {{}});</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"Страница статистики обновлена: {len(res)} прогнозов")


def _bot_block(m: dict) -> dict | None:
    """Прогноз бота для страницы матча: главный и смелый прогноз, шансы исходов, рынки, вероятные счета."""
    from . import markets as mk
    if not m.get("msg_id") or not m.get("main"):
        return None
    probs = m.get("probs") or {}
    tip = lambda x: {"label": x["label"], "p": round(float(x["p"]), 3), "odds": x.get("odds"), "est": bool(x.get("est"))} if x and x.get("label") else None
    out = {"main": tip(m["main"]), "bold": tip(m.get("bold")), "markets": []}
    if m.get("sport", "football") == "football":
        o = m.get("odds") or {}
        real = {"H": o.get("H"), "D": o.get("D"), "A": o.get("A")}
        if o.get("line") is not None:
            ln = str(o["line"]).replace(".", "")
            real["O" + ln], real["U" + ln] = o.get("over"), o.get("under")
        out["bar"] = [probs.get("H"), probs.get("D"), probs.get("A")]
        lam = m.get("lam")
        out["center"] = f"Ожидаемые голы (xG) {lam[0]:.1f} : {lam[1]:.1f}" if lam else ""
        for k in ("H", "D", "A", "1X", "X2", "O15", "O25", "U25", "O35", "BTTS_Y", "BTTS_N", "H_O15", "A_O15", "H-1.5", "A+1.5"):
            if k in probs:
                try:
                    out["markets"].append([mk.label(k), round(float(probs[k]), 3), real.get(k)])
                except Exception:
                    pass
        out["scores"] = [[sc, round(float(pr), 3)] for sc, pr in (m.get("scores") or [])][:5]
        ex = m.get("extra") or {}
        if ex.get("corners"):
            out["corners"] = round(float(ex["corners"].get("total", 0)), 1)
        if ex.get("cards"):
            out["cards"] = round(float(ex["cards"].get("total", 0)), 1)
    else:
        labels, real = m.get("labels") or {}, m.get("real") or {}
        out["bar"], out["center"] = m.get("bar"), m.get("center", "")
        for k, lab in list(labels.items())[:16]:
            if k in probs:
                out["markets"].append([lab, round(float(probs[k]), 3), real.get(k)])
    return out


def matches_json(events: list[dict], stored: dict, now: pd.Timestamp) -> None:
    """docs/matches.json — все матчи бота на ближайшие сутки (−4 ч … +30 ч) с параметрами 3D-трекера.

    events — свежее расписание (футбол + хоккей/баскетбол/теннис), stored — опубликованные прогнозы
    (ключ id или «div|id»): у таких матчей показываем наш прогноз. Живой счёт страница берёт прямо у ESPN,
    поэтому файл меняется, только когда меняется список или выходят новые прогнозы.
    """
    from . import live  # здесь, чтобы не тянуть live при импорте site
    out = []
    for e in events:
        sport = e.get("sport", "football")
        if sport == "esports" or "ru" not in e.get("home", {}) or "ru" not in e.get("away", {}):
            continue
        try:
            ko = pd.Timestamp(e["kickoff"])
        except (KeyError, ValueError):
            continue
        if not (now - pd.Timedelta(hours=4) <= ko <= now + pd.Timedelta(hours=30)):
            continue
        h, a = e["home"]["ru"], e["away"]["ru"]
        btn = live._tracker(e, sport, h, a)
        if not btn:
            continue
        m = stored.get(str(e["id"])) or stored.get(f"{e['div']}|{e['id']}") or {}
        tip = (m.get("main") or {}) if m.get("msg_id") else {}
        logo = lambda t: (t.get("logo") or [None, None])[1] if isinstance(t.get("logo"), list) else t.get("logo")
        out.append({"sport": sport, "id": str(e["id"]), "league": live._league(e), "kickoff": ko.isoformat(),
                    "home": h, "away": a, "hl": logo(e["home"]), "al": logo(e["away"]),
                    "path": btn[1].split("p=")[1].split("&")[0].replace("%2F", "/"), "url": btn[1].replace(live.TRACKER, "live.html"),
                    "tip": f"{tip['label']} · {'≈' if tip.get('est') else ''}{tip['odds']:.2f}" if tip.get("label") and tip.get("odds") else "",
                    "top": bool(m.get("top")), "bot": _bot_block(m)})
    out.sort(key=lambda x: (x["kickoff"], x["league"]))
    text = json.dumps(out, ensure_ascii=False, indent=0)
    if not MATCHES.exists() or MATCHES.read_text(encoding="utf-8") != text:
        MATCHES.write_text(text, encoding="utf-8")
        print(f"Список матчей для 3D обновлён: {len(out)}")
