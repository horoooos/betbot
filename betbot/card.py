"""Картинка-превью матча: логотипы, цвета клубов, время, вероятности и прогноз (Pillow, бесплатно)."""
import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1280, 720
BG_TOP, BG_BOTTOM = (10, 14, 32), (22, 30, 60)
WHITE, MUTED, ACCENT = (255, 255, 255), (160, 172, 205), (255, 196, 0)
C_HOME, C_DRAW, C_AWAY = (46, 204, 113), (149, 165, 166), (52, 152, 219)


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Montserrat-{weight}.ttf"), size)


def _rgb(hex_color: str, fallback=(60, 80, 140)) -> tuple:
    try:
        h = hex_color.strip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _logo(url: str | None, size: int, initials: str, color: tuple) -> Image.Image:
    if url:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            return img
        except Exception:
            pass
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    light = sum(c * k for c, k in zip(color, (0.299, 0.587, 0.114))) > 160
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,), outline=MUTED if light else WHITE, width=6)
    f = font(size // 3, "ExtraBold")
    d.text((size / 2, size / 2), initials, font=f, fill=(20, 20, 30) if light else WHITE, anchor="mm")
    return img


def _centered_lines(d: ImageDraw.ImageDraw, text: str, cx: int, y: int, max_w: int, size: int) -> None:
    """Название команды в 1–2 строки, уменьшая шрифт, если не влезает."""
    words = text.split()
    for s in (size, size - 6, size - 12):
        f = font(s)
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if d.textlength(test, font=f) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= 2 and all(d.textlength(l, font=f) <= max_w for l in lines):
            break
    for i, line in enumerate(lines[:2]):
        d.text((cx, y + i * (s + 6)), line, font=f, fill=WHITE, anchor="ma")


def match_card(league: str, when: str, home: dict, away: dict, probs: tuple[float, float, float],
               tip: str, xg: tuple[float, float], brand: str = "") -> bytes:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):  # вертикальный градиент
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))

    # мягкое свечение цветами клубов слева и справа
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    hc, ac = _rgb(home["color"]), _rgb(away["color"], (180, 40, 40))
    g.ellipse((-260, 40, 520, 640), fill=hc)
    g.ellipse((760, 40, 1540, 640), fill=ac)
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.blend(img, glow, 0.38)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 46), league.upper(), font=font(30), fill=MUTED, anchor="mm")
    half = d.textlength(league.upper(), font=font(30)) / 2
    d.line([(W / 2 - half, 76), (W / 2 + half, 76)], fill=ACCENT, width=3)

    for team, cx, col in ((home, 300, hc), (away, 980, ac)):
        ini = "".join(w[0] for w in team["ru"].split()[:2]).upper()
        logo = _logo(team.get("logo"), 230, ini, col)
        img.paste(logo, (cx - logo.width // 2, 130 + (230 - logo.height) // 2), logo)
        _centered_lines(d, team["ru"], cx, 380, 400, 40)

    time_part, _, date_part = when.partition(" · ")
    d.text((W / 2, 210), time_part, font=font(76, "ExtraBold"), fill=WHITE, anchor="mm")
    d.text((W / 2, 272), date_part.upper(), font=font(26, "Medium"), fill=MUTED, anchor="mm")
    d.text((W / 2, 330), f"xG {xg[0]:.1f} : {xg[1]:.1f}", font=font(30), fill=ACCENT, anchor="mm")

    # полоса вероятностей П1 / Х / П2
    x0, x1, y0, bh = 120, W - 120, 500, 46
    total = x1 - x0
    xs = x0
    for p, c, name in zip(probs, (C_HOME, C_DRAW, C_AWAY), ("П1", "Х", "П2")):
        w = max(int(total * p), 2)
        d.rounded_rectangle((xs, y0, xs + w, y0 + bh), radius=10, fill=c)
        if w > 110:
            d.text((xs + w / 2, y0 + bh / 2), f"{name} {p * 100:.0f}%", font=font(24), fill=WHITE, anchor="mm")
        elif w > 46:
            d.text((xs + w / 2, y0 + bh / 2), f"{p * 100:.0f}%", font=font(18), fill=WHITE, anchor="mm")
        xs += w

    # плашка с прогнозом
    d.rounded_rectangle((180, 585, W - 180, 670), radius=22, fill=(255, 196, 0))
    size = 36
    while size > 22 and d.textlength(f"ПРОГНОЗ: {tip}", font=font(size, "ExtraBold")) > W - 420:
        size -= 2
    d.text((W / 2, 627), f"ПРОГНОЗ: {tip}", font=font(size, "ExtraBold"), fill=(20, 20, 30), anchor="mm")
    if brand:
        d.text((W - 24, H - 14), brand, font=font(20, "Medium"), fill=MUTED, anchor="rd")

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
