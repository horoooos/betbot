"""Картинка для любого поста канала — для ВК и Дзена, где пост без картинки выглядит пусто.

Есть своя картинка у поста (прогноз, итог, новость) — берём её. Нет (полный разбор, «матч начался»,
текстовый итог) — рисуем фирменную карточку: рубрика, крупно матч, ниже турнир/результат.
"""
from __future__ import annotations

import re
from html import unescape

import requests

from . import card

# цвета фона по рубрике: (слева, справа)
COLORS = {"разбор": ((40, 60, 160), (120, 50, 170)), "итог": ((20, 120, 80), (30, 60, 140)),
          "начало": ((170, 30, 50), (60, 30, 120)), "новость": ((30, 80, 170), (20, 30, 90))}
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF☀-➿⬀-⯿️‍]")


def plain(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "")
    t = re.sub(r"<[^>]+>", "", t)
    return unescape(t)


def _clean(line: str) -> str:
    """Без эмодзи и лишних знаков — шрифт карточки их не рисует."""
    t = EMOJI_RE.sub("", line)
    t = re.sub(r"[✓✗✅❌·]+\s*$", "", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ·:-—")


def _lines(html: str) -> list[str]:
    return [x for x in (_clean(l) for l in plain(html).split("\n")) if x and not x.startswith("#")]


def _card(html: str, kind: str) -> bytes:
    ls = _lines(html)
    first = ls[0] if ls else "АИ СТАВИТ"
    if kind == "разбор":
        big = first.split(":", 1)[-1].strip() if ":" in first else first
        kicker, sub, rest = "Полный разбор матча", (ls[1] if len(ls) > 1 else ""), ls[2:5]
    elif kind == "начало":
        kicker, big, sub, rest = "Матч начался", (ls[1] if len(ls) > 1 else first), (ls[2] if len(ls) > 2 else ""), ["Смотрите онлайн на сайте АИ СТАВИТ"]
    elif kind == "итог":
        res = "Прогноз зашёл" if "ЗАШЛО" in html else "Прогноз не зашёл" if "МИМО" in html else ""
        kicker, big = "Итог матча", (ls[1] if len(ls) > 1 else first)
        sub = " · ".join(x for x in (first.replace("ИТОГ", "").strip(" ·"), res) if x)
        rest = ls[2:5]
    else:
        kicker, big, sub, rest = "Новости спорта", first, "", ls[1:3]
    big = big if len(big) <= 90 else big[:87] + "…"
    rest = [r if len(r) <= 70 else r[:67] + "…" for r in rest]
    return card.slide_card(kicker, big, sub, rest, COLORS.get(kind, COLORS["новость"]), brand="@aistavvit")


def as_jpeg(data: bytes | None) -> bytes | None:
    """Проверяем, что это действительно картинка, и пересохраняем в обычный JPEG (его принимают все соцсети)."""
    if not data:
        return None
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if im.width < 200 or im.height < 120:
            return None
        out = io.BytesIO()
        im.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return None


def _get(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        return as_jpeg(r.content) if r.ok else None
    except Exception:
        return None


def _ribbon(jpg: bytes, title: str = "ПОЛНЫЙ РАЗБОР МАТЧА", sub: str = "форма · личные встречи · рейтинг · шансы на все рынки") -> bytes:
    """Фирменная карточка матча + яркая лента сверху: так разбор выглядит как отдельная рубрика."""
    import io
    from PIL import Image, ImageDraw
    img = Image.open(io.BytesIO(jpg)).convert("RGB")
    w, h = img.size
    k = w / 1280
    band = int(108 * k)
    over = Image.new("RGBA", (w, band), (0, 0, 0, 0))
    g = Image.new("RGBA", (w, band))
    gd = ImageDraw.Draw(g)
    for x in range(w):   # градиент: фиолетовый → золотой
        t_ = x / w
        gd.line((x, 0, x, band), fill=(int(124 + (255 - 124) * t_), int(58 + (176 - 58) * t_), int(237 + (0 - 237) * t_), 255))
    over.alpha_composite(g)
    d = ImageDraw.Draw(over)
    cx, cy, r = int(64 * k), band // 2, int(22 * k)   # значок лупы
    d.ellipse((cx - r, cy - r - 4 * k, cx + r, cy + r - 4 * k), outline=(255, 255, 255, 255), width=max(3, int(6 * k)))
    d.line((cx + r * 0.7, cy + r * 0.6, cx + r * 1.5, cy + r * 1.5), fill=(255, 255, 255, 255), width=max(4, int(8 * k)))
    d.text((int(110 * k), cy - int(14 * k)), title, font=card.font(int(40 * k), "ExtraBold"), fill=(255, 255, 255, 255), anchor="lm")
    d.text((int(110 * k), cy + int(24 * k)), sub, font=card.font(int(22 * k), "Bold"), fill=(255, 255, 255, 215), anchor="lm")
    base = img.convert("RGBA")
    base.alpha_composite(over, (0, 0))
    out = io.BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


def _teams_of(html: str) -> str:
    """«ПОЛНЫЙ РАЗБОР: Арина Соболенко — Каролина Мухова» → «Арина Соболенко — Каролина Мухова»."""
    first = plain(html).strip().split(chr(10))[0]
    return first.split(":", 1)[-1].strip() if " — " in first else ""


def image_for(post: dict, kind: str, posts: dict | None = None) -> bytes | None:
    """Картинка поста: своя (скачиваем); у разбора — фирменная карточка его матча с лентой «ПОЛНЫЙ РАЗБОР»;
    иначе — нарисованная карточка."""
    if kind == "разбор" and posts and not post.get("photo"):
        teams, pid = _teams_of(post.get("html", "")), int(post.get("id", 0))
        for j in range(pid - 1, pid - 8, -1):           # прогноз на этот матч — один из предыдущих постов
            q = posts.get(str(j)) or {}
            if q.get("photo") and teams and teams in plain(q.get("html", "")) and "ПРОГНОЗ" in plain(q.get("html", "")):
                jpg = _get(q["photo"])
                break
        else:
            jpg = None
        try:   # инфографика разбора: логотипы, форма, рейтинг, личные встречи, шансы, прогноз бота
            from .razbor_card import razbor_card
            return as_jpeg(razbor_card(post.get("html", ""), jpg))
        except Exception as e:
            print(f"  ! картинка разбора не нарисовалась: {e}")
    if post.get("photo"):
        jpg = _get(post["photo"])   # своя картинка поста — только если это действительно картинка
        if jpg:
            return jpg
    try:
        return as_jpeg(_card(post.get("html", ""), kind))
    except Exception as e:
        print(f"  ! картинка поста не нарисовалась: {e}")
        return None
