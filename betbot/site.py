"""Публичная страница со статистикой бота (GitHub Pages, бесплатно): docs/index.html.

Каждый опубликованный прогноз и его итог — без фильтров и подчисток. Пересобирается раз в день.
"""
import os
from html import escape
from pathlib import Path

import pandas as pd

from . import pro
from .sports import EMOJI, SPORT_RU

OUT = Path(__file__).resolve().parent.parent / "docs" / "index.html"
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
    """Линия виртуального банка (SVG)."""
    if len(curve) < 2:
        return ""
    w, h, pad = 640, 220, 28
    lo, hi = min(curve), max(curve)
    if hi - lo < 1:
        hi, lo = hi + 1, lo - 1
    xs = [pad + i * (w - 2 * pad) / (len(curve) - 1) for i in range(len(curve))]
    ys = [h - pad - (v - lo) * (h - 2 * pad) / (hi - lo) for v in curve]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    base = h - pad - (pro.BANK_START - lo) * (h - 2 * pad) / (hi - lo)
    color = "var(--good)" if curve[-1] >= pro.BANK_START else "var(--bad)"
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Виртуальный банк">'
            f'<line x1="{pad}" x2="{w - pad}" y1="{base:.1f}" y2="{base:.1f}" class="base"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
            f'<text x="{pad}" y="16" class="lbl">{hi:,.0f} ₽</text><text x="{pad}" y="{h - 6}" class="lbl">{lo:,.0f} ₽</text>'
            "</svg>").replace(",", " ")


def build(res: pd.DataFrame, now: pd.Timestamp) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if res is None or res.empty:
        res = pd.DataFrame(columns=["date", "sport", "home", "away", "score", "main_label", "main_odds", "main_hit"])
    res = res.copy()
    res["sport"] = res.get("sport", pd.Series(dtype=str)).fillna("football")
    hit = _hits(res["main_hit"]) if len(res) else pd.Series(dtype=bool)
    curve = pro.bank_curve(res)
    clv = res["main_clv"].dropna().astype(float) if "main_clv" in res else pd.Series(dtype=float)
    vn = pro.value_numbers()

    def kpi(label, value, sub=""):
        return f'<div class="kpi"><div class="v">{value}</div><div class="l">{label}</div><div class="s">{sub}</div></div>'

    kpis = "".join([
        kpi("прогнозов", f"{len(res)}"),
        kpi("основной зашёл", f"{100 * hit.mean():.0f}%" if len(res) else "—", f"{int(hit.sum())} из {len(res)}"),
        kpi("ROI", f"{_roi(res):+.1f}%" if len(res) else "—", "только настоящие кэфы"),
        kpi("виртуальный банк", f"{curve[-1]:,.0f} ₽".replace(",", " "), f"старт {pro.BANK_START:,} ₽".replace(",", " ")),
        kpi("CLV", f"{100 * clv.mean():+.1f}%" if len(clv) else "—",
            f"линия за ботом в {100 * (clv > 0).mean():.0f}%" if len(clv) else "копится"),
        kpi("value-ставки", f"{vn[2]:+.1f}%" if vn else "—",
            f"ROI · {vn[1]} из {vn[0]} зашли" if vn else "копятся"),
    ])

    rows_sport = ""
    for sp, g in res.groupby("sport"):
        h = _hits(g["main_hit"])
        rows_sport += (f"<tr><td>{EMOJI.get(sp, '')} {SPORT_RU.get(sp, sp)}</td><td>{len(g)}</td>"
                       f"<td>{100 * h.mean():.0f}%</td><td>{_roi(g):+.1f}%</td></tr>")
    rows_market = ""
    if len(res):
        by = res.assign(h=hit).groupby("main_label")["h"].agg(["size", "mean"]).sort_values("size", ascending=False).head(12)
        for name, r in by.iterrows():
            rows_market += f"<tr><td>{escape(str(name))}</td><td>{int(r['size'])}</td><td>{100 * r['mean']:.0f}%</td></tr>"
    rows_last = ""
    for _, r in res.tail(60).iloc[::-1].iterrows():
        ok = str(r["main_hit"]).lower() in ("true", "1", "1.0")
        c = r.get("main_clv")
        rows_last += (f"<tr><td>{escape(str(r['date']))[5:]}</td><td>{EMOJI.get(r['sport'], '')}</td>"
                      f"<td>{escape(str(r['home']))} — {escape(str(r['away']))}</td><td>{escape(str(r['score']))}</td>"
                      f"<td>{escape(str(r['main_label']))}</td><td>{float(r['main_odds']):.2f}</td>"
                      f"<td class=\"{'good' if ok else 'bad'}\">{'✅' if ok else '❌'}</td>"
                      f"<td>{'' if pd.isna(c) else f'{100 * float(c):+.1f}%'}</td></tr>")
    tg = f"https://t.me/{escape(CHANNEL.lstrip('@'))}"
    channel = (f'<div class="cta"><div><b>Прогнозы каждый день — в Telegram</b><br>'
               f'<span class="muted">Футбол, хоккей, NBA, теннис, CS2 и Dota 2: прогноз за час до матча, live, '
               f'экспрессы и честные итоги.</span></div><a class="btn big" href="{tg}">📲 Подписаться на канал</a></div>')
    sticky = f'<a class="sticky" href="{tg}">📲 Подписаться на {escape(CHANNEL)}</a>'
    hit_pct = f"{100 * hit.mean():.0f}%" if len(res) else "—"
    seo_desc = (f"Бесплатные прогнозы на спорт от бота АИ СТАВИТ: футбол, хоккей НХЛ, баскетбол НБА, теннис, CS2 и Dota 2. "
                f"Честная статистика всех {len(res)} прогнозов: заходит {hit_pct}, ROI и виртуальный банк.")
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>АИ СТАВИТ — бесплатные прогнозы на спорт и честная статистика</title>
<meta name="description" content="{escape(seo_desc)}">
<meta name="keywords" content="прогнозы на спорт, прогнозы на футбол, бесплатные прогнозы, ставки на спорт, прогнозы НХЛ, прогнозы НБА, прогнозы на теннис, прогнозы CS2, экспресс дня, статистика прогнозов">
<meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}">
<meta property="og:type" content="website"><meta property="og:url" content="{SITE}">
<meta property="og:title" content="АИ СТАВИТ — прогнозы на спорт с честной статистикой">
<meta property="og:description" content="{escape(seo_desc)}"><meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebSite","name":"АИ СТАВИТ","url":"{SITE}","description":"{escape(seo_desc)}","sameAs":["{tg}"]}}</script>
<style>
:root{{--bg:#f6f7fb;--card:#fff;--ink:#141826;--muted:#667085;--line:#e4e7ef;--good:#1f9d55;--bad:#d64545;--accent:#f2b400}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0b0f1e;--card:#151b30;--ink:#eef1fb;--muted:#9aa3bd;--line:#26304d}}}}
:root[data-theme=dark]{{--bg:#0b0f1e;--card:#151b30;--ink:#eef1fb;--muted:#9aa3bd;--line:#26304d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:28px;margin:0 0 4px}}h2{{font-size:18px;margin:28px 0 10px}}
.muted{{color:var(--muted)}}.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:18px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}.kpi .v{{font-size:24px;font-weight:700}}
.kpi .l{{color:var(--muted);font-size:13px}}.kpi .s{{color:var(--muted);font-size:12px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
th{{color:var(--muted);font-weight:600}}.good{{color:var(--good)}}.bad{{color:var(--bad)}}
svg{{width:100%;height:auto}}svg .base{{stroke:var(--line);stroke-dasharray:4 4}}svg .lbl{{fill:var(--muted);font-size:12px}}
.btn{{display:inline-block;margin-top:12px;padding:8px 14px;border-radius:10px;background:var(--accent);color:#141826;text-decoration:none;font-weight:600}}
.btn.big{{margin:0;padding:12px 20px;font-size:16px;white-space:nowrap}}
.cta{{display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:16px;padding:16px;border-radius:14px;background:var(--card);border:2px solid var(--accent)}}
.sticky{{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);padding:10px 18px;border-radius:999px;background:var(--accent);color:#141826;font-weight:700;text-decoration:none;box-shadow:0 6px 20px rgba(0,0,0,.25);white-space:nowrap}}
@media (min-width:900px){{.sticky{{display:none}}}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
</style></head><body><main>
<h1>АИ СТАВИТ — бесплатные прогнозы на спорт и честная статистика</h1>
<div class="muted">Все прогнозы бота без исключений. Обновлено {now:%d.%m.%Y %H:%M} МСК.</div>{channel}
<div class="kpis">{kpis}</div>
<h2>Виртуальный банк</h2><div class="card">{_chart(curve) or '<span class="muted">Пока мало данных</span>'}
<div class="muted">Если ставить ровно по рекомендациям бота (1–3% банка на основной прогноз), начиная с {pro.BANK_START:,} ₽.</div></div>
<div class="grid2"><div><h2>По видам спорта</h2><div class="card"><table><tr><th>Спорт</th><th>Прогнозов</th><th>Зашло</th><th>ROI</th></tr>{rows_sport}</table></div></div>
<div><h2>По типам прогнозов</h2><div class="card"><table><tr><th>Прогноз</th><th>Сколько</th><th>Зашло</th></tr>{rows_market}</table></div></div></div>
<h2>Последние прогнозы</h2><div class="card"><table><tr><th>Дата</th><th></th><th>Матч</th><th>Счёт</th><th>Прогноз</th><th>Кэф</th><th></th><th>CLV</th></tr>{rows_last}</table></div>
<p class="muted">CLV — насколько выросла вероятность нашего исхода по линии букмекеров к началу матча. Плюс значит, что
бот нашёл ценность раньше рынка. 18+. Прогноз — не гарантия.</p>
</main></body></html>"""
    OUT.write_text(html.replace(f"{pro.BANK_START:,}", f"{pro.BANK_START:,}".replace(",", " ")), encoding="utf-8")
    print(f"Страница статистики обновлена: {len(res)} прогнозов")
