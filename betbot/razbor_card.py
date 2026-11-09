"""Картинка «Полного разбора»: инфографика матча в фирменном стиле.

Данные берём из текста разбора (форма, шансы, рейтинг/xG, личные встречи, итоговый прогноз),
логотипы/флаги — из карточки прогноза на этот матч (если она есть).
"""
from __future__ import annotations

import io
import re
from html import unescape

from PIL import Image, ImageDraw, ImageFilter

from .card import ACCENT, H, MUTED, W, WHITE, _background, _fit, _png, font

GREEN, RED, DRAW, GOLD = (46, 204, 113), (255, 82, 82), (255, 196, 0), (255, 196, 0)
HOME_C, AWAY_C = (66, 133, 255), (255, 110, 64)


def _plain(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", html or "")))


def parse(html: str) -> dict:
    t = _plain(html)
    lines = [l.strip() for l in t.split("\n")]
    first = lines[0] if lines else ""
    teams = first.split(":", 1)[-1].strip()
    home, _, away = teams.partition(" — ")
    d = {"home": home.strip(), "away": away.strip(), "tour": "", "form": {}, "p": {}, "stat": [], "h2h": "", "tip": "", "odds": "", "tip_p": ""}
    for l in lines:
        if l.startswith("🏆"):
            d["tour"] = l.lstrip("🏆 ").strip()
        m = re.match(r"(.+?):\s*([🟢🔴🟡⚪]{2,})", l)
        if m:
            d["form"][m.group(1).strip()] = [{"🟢": "W", "🔴": "L"}.get(c, "D") for c in m.group(2)]
        m = re.match(r"Победа:\s*(.+?)\s{2,}(\d+)%", l)
        if m:
            d["p"][m.group(1).strip()] = int(m.group(2))
        m = re.match(r"(Ничья|Х|X)\s{2,}(\d+)%", l)
        if m:
            d["p"]["Ничья"] = int(m.group(2))
        m = re.search(r"Рейтинг Эло (\d+)\s*:\s*(\d+)", l)
        if m:
            d["stat"].append(("Рейтинг Эло", m.group(1), m.group(2)))
        m = re.search(r"xG\)?:\s*([\d.]+)\s*:\s*([\d.]+)", l)
        if m:
            d["stat"].append(("Ожидаемые голы xG", m.group(1), m.group(2)))
        m = re.search(r"Личные встречи:\s*(.+)", l)
        if m:
            d["h2h"] = m.group(1)
        m = re.search(r"Итог:\s*(.+?)\s+—\s+(\d+)%.*?кэф\s*([≈\d.]+)", l)
        if m:
            d["tip"], d["tip_p"], d["odds"] = m.group(1), m.group(2), m.group(3).rstrip(".")
    hp = re.search(r"(\d+)\s*—\s*(\d+)", d["h2h"])
    d["h2h_score"] = f"{hp.group(1)} : {hp.group(2)}" if hp else ("нет встреч" if "не встречал" in d["h2h"] else "")
    return d


def _circle(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return out


def logos_from_prediction(jpg: bytes) -> tuple[Image.Image, Image.Image] | None:
    """Вырезаем круглые логотипы/флаги из нашей карточки прогноза (они всегда в одних и тех же местах)."""
    try:
        im = Image.open(io.BytesIO(jpg)).convert("RGB")
        w, h = im.size
        r = int(0.084 * w)
        out = []
        for cx in (0.2325, 0.7675):
            x, y = int(cx * w), int(0.344 * h)
            out.append(im.crop((x - r, y - r, x + r, y + r)))
        return out[0], out[1]
    except Exception:
        return None


def _initials(name: str, color: tuple) -> Image.Image:
    im = Image.new("RGB", (300, 300), color)
    d = ImageDraw.Draw(im)
    ini = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    d.text((150, 150), ini, font=font(130, "ExtraBold"), fill=WHITE, anchor="mm")
    return im


def _glow_text(img: Image.Image, xy, text: str, size: int, color: tuple, glow: tuple, anchor="mm") -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font(size, "ExtraBold"), fill=glow + (255,), anchor=anchor)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(14)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(5)))
    ImageDraw.Draw(img).text(xy, text, font=font(size, "ExtraBold"), fill=color, anchor=anchor)


def _dots(d: ImageDraw.ImageDraw, form: list[str], cx: int, y: int) -> None:
    n = len(form[-5:])
    for i, r in enumerate(form[-5:]):
        x = cx + (i - (n - 1) / 2) * 46
        c = GREEN if r == "W" else RED if r == "L" else DRAW
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=c, outline=(255, 255, 255), width=3)
        d.text((x, y + 1), {"W": "В", "L": "П", "D": "Н"}[r], font=font(18, "ExtraBold"), fill=(15, 18, 35), anchor="mm")


def razbor_card(html: str, prediction_jpg: bytes | None = None, brand: str = "@aistavvit") -> bytes:
    p = parse(html)
    img, d = _background((40, 30, 110), (10, 60, 120), style="rays")
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)

    # шапка: золотая плашка рубрики + турнир
    pill = Image.new("RGBA", (420, 64), (0, 0, 0, 0))
    pd_ = ImageDraw.Draw(pill)
    for x in range(420):
        t = x / 420
        pd_.line((x, 0, x, 64), fill=(255, int(196 - 70 * t), int(0 + 40 * t), 255))
    mask = Image.new("L", (420, 64), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 419, 63), 32, fill=255)
    img.paste(pill, (60, 44), mask)
    d.ellipse((84, 58, 112, 86), outline=(20, 16, 40), width=5)
    d.line((108, 82, 122, 96), fill=(20, 16, 40), width=7)
    d.text((136, 76), "ПОЛНЫЙ РАЗБОР", font=font(32, "ExtraBold"), fill=(20, 16, 40), anchor="lm")
    if p["tour"]:
        d.text((W - 64, 76), p["tour"], font=_fit(d, p["tour"], 26, 640, "Bold"), fill=(215, 222, 250), anchor="rm")

    # команды: логотипы со светящимся кольцом, имена, форма
    logos = logos_from_prediction(prediction_jpg) if prediction_jpg else None
    if not logos:
        logos = (_initials(p["home"], HOME_C), _initials(p["away"], AWAY_C))
    for (cx, name, logo, col) in ((300, p["home"], logos[0], HOME_C), (W - 300, p["away"], logos[1], AWAY_C)):
        ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((cx - 112, 250 - 112, cx + 112, 250 + 112), fill=col + (200,))
        img.alpha_composite(ring.filter(ImageFilter.GaussianBlur(26)))
        d = ImageDraw.Draw(img)
        d.ellipse((cx - 100, 150, cx + 100, 350), fill=(255, 255, 255))
        img.alpha_composite(_circle(logo, 186), (cx - 93, 157))
        d = ImageDraw.Draw(img)
        d.ellipse((cx - 100, 150, cx + 100, 350), outline=col, width=6)
        d.text((cx, 392), name, font=_fit(d, name, 38, 440, "ExtraBold"), fill=WHITE, anchor="mm")
        form = p["form"].get(name) or next((v for k, v in p["form"].items() if k.split()[-1] in name), None)
        if form:
            d.text((cx, 432), "ФОРМА · 5 МАТЧЕЙ", font=font(15, "Bold"), fill=MUTED, anchor="mm")
            _dots(d, form, cx, 464)

    _glow_text(img, (W // 2, 250), "VS", 120, WHITE, GOLD)
    d = ImageDraw.Draw(img)

    # центр под VS: ключевые цифры
    y = 335
    for label, a, b in p["stat"][:1]:
        d.text((W // 2, y), label.upper(), font=font(16, "Bold"), fill=MUTED, anchor="mm")
        d.text((W // 2, y + 34), f"{a} : {b}", font=font(36, "ExtraBold"), fill=WHITE, anchor="mm")
        y += 76
    if p["h2h_score"]:
        d.text((W // 2, y), "ЛИЧНЫЕ ВСТРЕЧИ", font=font(16, "Bold"), fill=MUTED, anchor="mm")
        d.text((W // 2, y + 32), p["h2h_score"], font=font(30 if ":" in p["h2h_score"] else 22, "ExtraBold"), fill=WHITE, anchor="mm")

    # шанс на победу: полоса в цветах сторон
    ph = p["p"].get(p["home"]) or next((v for k, v in p["p"].items() if k != "Ничья" and k.split()[-1] in p["home"]), None)
    pa = p["p"].get(p["away"]) or next((v for k, v in p["p"].items() if k != "Ничья" and k.split()[-1] in p["away"]), None)
    if ph and pa:
        px = p["p"].get("Ничья", 0)
        x0, x1, yb = 120, W - 120, 520
        tot = ph + pa + px
        d.text((W // 2, yb - 26), "ШАНС НА ПОБЕДУ", font=font(16, "Bold"), fill=MUTED, anchor="mm")
        xa = x0 + (x1 - x0) * ph / tot
        xb = xa + (x1 - x0) * px / tot
        d.rounded_rectangle((x0, yb, x1, yb + 40), 20, fill=AWAY_C)
        d.rounded_rectangle((x0, yb, max(xa, x0 + 40), yb + 40), 20, fill=HOME_C)
        if px:
            d.rectangle((xa, yb, xb, yb + 40), fill=(120, 130, 170))
        d.text((x0 + 22, yb + 20), f"{ph}%", font=font(26, "ExtraBold"), fill=WHITE, anchor="lm")
        d.text((x1 - 22, yb + 20), f"{pa}%", font=font(26, "ExtraBold"), fill=WHITE, anchor="rm")
        if px >= 12:
            d.text(((xa + xb) / 2, yb + 20), f"{px}%", font=font(20, "ExtraBold"), fill=WHITE, anchor="mm")

    # прогноз бота: золотая плашка
    if p["tip"]:
        box = Image.new("RGBA", (W - 240, 86), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        for x in range(W - 240):
            t = x / (W - 240)
            bd.line((x, 0, x, 86), fill=(255, int(200 - 40 * t), int(40 * (1 - t)), 255))
        m = Image.new("L", box.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, W - 241, 85), 22, fill=255)
        img.paste(box, (120, 586), m)
        d = ImageDraw.Draw(img)
        d.text((150, 610), "ПРОГНОЗ БОТА", font=font(16, "ExtraBold"), fill=(80, 50, 0), anchor="lm")
        tip = p["tip"] + (f" · шанс {p['tip_p']}%" if p["tip_p"] else "")
        d.text((150, 644), tip, font=_fit(d, tip, 34, 760, "ExtraBold"), fill=(20, 14, 0), anchor="lm")
        if p["odds"]:
            d.text((W - 150, 610), "КЭФ", font=font(16, "ExtraBold"), fill=(80, 50, 0), anchor="rm")
            d.text((W - 150, 644), p["odds"], font=font(44, "ExtraBold"), fill=(20, 14, 0), anchor="rm")

    rgb = img.convert("RGB")
    return _png(rgb, ImageDraw.Draw(rgb), brand)
