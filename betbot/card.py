"""Картинка-превью матча: логотипы, цвета клубов, время, вероятности и прогноз (Pillow, бесплатно)."""
import io
import math
import random
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1280, 720
BG_TOP, BG_BOTTOM = (10, 14, 32), (22, 30, 60)
WHITE, MUTED, ACCENT = (255, 255, 255), (160, 172, 205), (255, 196, 0)
C_HOME, C_DRAW, C_AWAY = (46, 204, 113), (149, 165, 166), (52, 152, 219)
GOLD_TOP, GOLD_BOTTOM = (255, 222, 110), (214, 152, 20)


KEEP = set("—–·«»…₽≈−№")  # эти знаки шрифт рисует; эмодзи (🔥 ✅ флаги) — нет, вместо них были бы квадраты
DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", " ": " ", " ": " ", " ": " "})


def safe(text: str) -> str:
    """Убираем из текста для картинки всё, чего нет в шрифте Montserrat (эмодзи, флаги, значки)."""
    text = str(text).translate(DASHES)
    out = "".join(c for c in text if ord(c) < 0x2000 or c in KEEP)
    return " ".join(out.split())


# Вся отрисовка текста на картинках идёт через safe() — так эмодзи не превратятся в квадраты нигде.
_text, _textlength = ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.textlength
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: _text(self, xy, safe(text), *a, **k)
ImageDraw.ImageDraw.textlength = lambda self, text, *a, **k: _textlength(self, safe(text), *a, **k)


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Montserrat-{weight}.ttf"), size)


def _rgb(hex_color: str, fallback=(60, 80, 140)) -> tuple:
    try:
        h = hex_color.strip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _avatar(photo: Image.Image, size: int, color: tuple, top: float = 0.04, left: bool = False) -> Image.Image:
    """Фото игрока в круге с цветной подложкой и белой обводкой."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,))
    ph = photo.copy()
    # подгоняем по высоте круга: голова и плечи целиком, лишнее по бокам обрежет круг
    ph = ph.resize((int(ph.width * size / ph.height), size), Image.LANCZOS)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = int(-size * 0.08) if left else (size - ph.width) // 2  # у флагов символ обычно слева (звёзды, крест)
    layer.paste(ph, (x, int(size * top)), ph)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    canvas.paste(layer, (0, 0), Image.composite(layer, Image.new("RGBA", (size, size)), mask).split()[3])
    ImageDraw.Draw(canvas).ellipse((0, 0, size - 1, size - 1), outline=WHITE, width=6)
    return canvas


def _logo(url: str | list | None, size: int, initials: str, color: tuple) -> Image.Image:
    """Логотип или фото: url может быть списком (фото игрока → флаг страны → инициалы)."""
    for u in (url if isinstance(url, list) else [url]):
        if not u:
            continue
        try:
            r = requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            if "headshots" in u:  # фото игрока — в круглую рамку, как аватар
                img = _avatar(img, size, color)
            elif "countries" in u:  # флаг страны — тоже в круг, растянутый на весь круг
                if img.getbbox():  # у ESPN флаг лежит посередине квадрата с прозрачными полями — обрезаем их
                    img = img.crop(img.getbbox())
                flag = img.resize((int(size * img.width / img.height), size), Image.LANCZOS)
                img = _avatar(flag, size, color, top=0, left=True)
            img.thumbnail((size, size), Image.LANCZOS)
            return img
        except Exception:
            continue
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


# ── дизайн-система: фон в нескольких стилях, зерно, виньетка, уголки ────────
# Стиль фона выбирается случайно — картинки в канале не повторяются, но остаются в одной гамме.
STYLES = ("glow", "diagonal", "halftone", "rays", "pitch", "blobs")
PALETTES = [((10, 14, 32), (22, 30, 60)), ((12, 10, 30), (34, 18, 58)), ((6, 18, 28), (14, 40, 52)),
            ((16, 12, 20), (44, 22, 30)), ((8, 12, 22), (20, 26, 44))]
_style_override: str | None = None  # для тестов: принудительно один стиль


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return lay, ImageDraw.Draw(lay)


def _background(left: tuple, right: tuple, style: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Тёмный градиент + свечение цветами команд + один из декоративных стилей (общий стиль канала)."""
    style = style or _style_override or random.choice(STYLES)
    top, bottom = random.choice(PALETTES)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_mix(top, bottom, y / H))
    img = img.convert("RGBA")
    # свечение цветами команд — есть во всех стилях
    glow, g = _layer()
    g.ellipse((-300, 20, 520, 700), fill=left + (120,))
    g.ellipse((760, 20, 1580, 700), fill=right + (120,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(150)))
    lay, l = _layer()
    if style == "diagonal":  # широкая диагональная полоса и тонкие штрихи — «спортивный» динамичный фон
        l.polygon([(W * 0.42, 0), (W * 0.78, 0), (W * 0.52, H), (W * 0.16, H)], fill=left + (78,))
        l.polygon([(W * 0.80, 0), (W * 0.86, 0), (W * 0.60, H), (W * 0.54, H)], fill=ACCENT + (60,))
        for x in range(-H, W, 26):
            l.line([(x, H), (x + H * 0.55, 0)], fill=(255, 255, 255, 14), width=2)
        lay = lay.filter(ImageFilter.GaussianBlur(1))
    elif style == "halftone":  # полутоновые точки, растущие к углу
        for y in range(0, H, 22):
            for x in range(0, W, 22):
                t = max(0.0, 1 - ((W - x) ** 2 + y ** 2) ** 0.5 / 900)
                if t > 0.02:
                    r = 1 + 7 * t
                    l.ellipse((x - r, y - r, x + r, y + r), fill=_mix(right, (255, 255, 255), 0.3) + (int(110 * t),))
                t2 = max(0.0, 1 - (x ** 2 + (H - y) ** 2) ** 0.5 / 800)
                if t2 > 0.02:
                    r = 1 + 6 * t2
                    l.ellipse((x - r, y - r, x + r, y + r), fill=_mix(left, (255, 255, 255), 0.3) + (int(90 * t2),))
    elif style == "rays":  # лучи прожекторов сверху, как на стадионе
        for cx in (W * 0.18, W * 0.82):
            for k in range(-3, 4):
                l.polygon([(cx, -40), (cx + k * 150 - 40, H + 40), (cx + k * 150 + 40, H + 40)],
                          fill=(255, 255, 255, 24))
        lay = lay.filter(ImageFilter.GaussianBlur(16))
    elif style == "pitch":  # разметка поля тонкими линиями
        c = (255, 255, 255, 34)
        l.line([(W / 2, 0), (W / 2, H)], fill=c, width=3)
        l.ellipse((W / 2 - 170, H / 2 - 170, W / 2 + 170, H / 2 + 170), outline=c, width=3)
        l.rectangle((-4, H / 2 - 220, 200, H / 2 + 220), outline=c, width=3)
        l.rectangle((W - 200, H / 2 - 220, W + 4, H / 2 + 220), outline=c, width=3)
        l.rectangle((-4, H / 2 - 100, 70, H / 2 + 100), outline=c, width=3)
        l.rectangle((W - 70, H / 2 - 100, W + 4, H / 2 + 100), outline=c, width=3)
    elif style == "blobs":  # мягкие цветные пятна — «меш-градиент»
        for _ in range(5):
            col = random.choice([left, right, ACCENT, (120, 80, 255), (0, 200, 200)])
            x, y, r = random.randint(0, W), random.randint(0, H), random.randint(160, 340)
            l.ellipse((x - r, y - r, x + r, y + r), fill=col + (85,))
        lay = lay.filter(ImageFilter.GaussianBlur(90))
    else:  # glow — мягкий ореол по центру
        l.ellipse((W / 2 - 420, H / 2 - 300, W / 2 + 420, H / 2 + 300), fill=(255, 255, 255, 18))
        lay = lay.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img, lay).convert("RGB")
    return img, ImageDraw.Draw(img)


def _finish(img: Image.Image) -> Image.Image:
    """Общая «отделка» всех картинок: виньетка по краям, лёгкое плёночное зерно и золотые уголки."""
    img = img.convert("RGB")
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse((-W * 0.25, -H * 0.35, W * 1.25, H * 1.35), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(img, Image.new("RGB", (W, H), (0, 0, 0)), vig.point(lambda v: 90 + v * 165 // 255))
    noise = Image.effect_noise((W, H), 28).convert("RGB")
    img = Image.blend(img, noise, 0.035)
    d = ImageDraw.Draw(img)
    L, m = 34, 18  # уголки-«видоискатель»
    for (x, y, sx, sy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        d.line([(x, y), (x + sx * L, y)], fill=ACCENT, width=3)
        d.line([(x, y), (x, y + sy * L)], fill=ACCENT, width=3)
    return img


def _sport_icon(img: Image.Image, sport: str, cx: int = W // 2, cy: int = H // 2 - 20, r: int = 250,
                alpha: int = 34) -> Image.Image:
    """Большая полупрозрачная иконка вида спорта на заднем фоне: мяч, шайба, джойстик…"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = (255, 255, 255, alpha)
    w = max(6, r // 28)
    box = (cx - r, cy - r, cx + r, cy + r)
    if sport == "football":
        d.ellipse(box, outline=c, width=w)
        pent = [(cx + r * 0.32 * math.cos(math.radians(-90 + 72 * i)), cy + r * 0.32 * math.sin(math.radians(-90 + 72 * i)))
                for i in range(5)]
        d.polygon(pent, fill=c)
        for i, (x, y) in enumerate(pent):  # швы от центрального пятиугольника к краю
            ang = math.radians(-90 + 72 * i)
            d.line([(x, y), (cx + r * 0.72 * math.cos(ang), cy + r * 0.72 * math.sin(ang))], fill=c, width=w)
            ex, ey = cx + r * 0.72 * math.cos(ang), cy + r * 0.72 * math.sin(ang)
            for side in (-1, 1):
                a2 = ang + side * math.radians(28)
                d.line([(ex, ey), (cx + r * 0.97 * math.cos(a2), cy + r * 0.97 * math.sin(a2))], fill=c, width=w)
    elif sport == "basketball":
        d.ellipse(box, outline=c, width=w)
        d.line([(cx, cy - r), (cx, cy + r)], fill=c, width=w)
        d.line([(cx - r, cy), (cx + r, cy)], fill=c, width=w)
        d.arc((cx - r * 1.55, cy - r, cx - r * 0.35, cy + r), -60, 60, fill=c, width=w)
        d.arc((cx + r * 0.35, cy - r, cx + r * 1.55, cy + r), 120, 240, fill=c, width=w)
    elif sport == "tennis":
        d.ellipse(box, outline=c, width=w)
        d.arc((cx - r * 1.7, cy - r * 0.9, cx - r * 0.2, cy + r * 0.9), -50, 50, fill=c, width=w)
        d.arc((cx + r * 0.2, cy - r * 0.9, cx + r * 1.7, cy + r * 0.9), 130, 230, fill=c, width=w)
    elif sport == "hockey":
        for sgn in (-1, 1):  # две скрещённые клюшки
            x0, y0 = cx - sgn * r * 0.8, cy - r * 0.9
            x1, y1 = cx + sgn * r * 0.55, cy + r * 0.55
            d.line([(x0, y0), (x1, y1)], fill=c, width=w * 2)
            d.line([(x1, y1), (x1 + sgn * r * 0.35, y1 + r * 0.05)], fill=c, width=w * 3)
        d.ellipse((cx - r * 0.42, cy + r * 0.55, cx + r * 0.42, cy + r * 0.85), fill=c)
    elif sport == "esports":  # геймпад
        d.rounded_rectangle((cx - r, cy - r * 0.45, cx + r, cy + r * 0.35), radius=int(r * 0.3), outline=c, width=w)
        d.ellipse((cx - r * 1.05, cy - r * 0.1, cx - r * 0.45, cy + r * 0.75), outline=c, width=w)
        d.ellipse((cx + r * 0.45, cy - r * 0.1, cx + r * 1.05, cy + r * 0.75), outline=c, width=w)
        k = r * 0.11
        d.rectangle((cx - r * 0.6 - k, cy - r * 0.08 - k * 3, cx - r * 0.6 + k, cy - r * 0.08 + k * 3), fill=c)
        d.rectangle((cx - r * 0.6 - k * 3, cy - r * 0.08 - k, cx - r * 0.6 + k * 3, cy - r * 0.08 + k), fill=c)
        for bx, by in ((0.55, -0.2), (0.72, -0.05), (0.55, 0.1), (0.38, -0.05)):
            d.ellipse((cx + r * bx - k, cy + r * by - k, cx + r * bx + k, cy + r * by + k), fill=c)
    else:
        return img
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _title(d: ImageDraw.ImageDraw, text: str, y: int = 46, size: int = 30) -> None:
    d.text((W / 2, y), text.upper(), font=font(size), fill=MUTED, anchor="mm")
    half = d.textlength(text.upper(), font=font(size)) / 2
    d.line([(W / 2 - half, y + 30), (W / 2 + half, y + 30)], fill=ACCENT, width=3)


def _png(img: Image.Image, d: ImageDraw.ImageDraw, brand: str) -> bytes:
    img = _finish(img)
    if brand:
        ImageDraw.Draw(img).text((W - 30, H - 22), brand, font=font(20, "Medium"), fill=MUTED, anchor="rd")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _teams(img, d, home: dict, away: dict, hc: tuple, ac: tuple, top: int = 130) -> None:
    for team, cx, col in ((home, 300, hc), (away, 980, ac)):
        ini = "".join(w[0] for w in team["ru"].split()[:2]).upper()
        logo = _logo(team.get("logo"), 230, ini, col)
        img.paste(logo, (cx - logo.width // 2, top + (230 - logo.height) // 2), logo)
        _centered_lines(d, team["ru"], cx, top + 250, 400, 40)


def _pill(d, cx: int, y: int, text: str, fill: tuple, color=WHITE, size: int = 28) -> None:
    w = d.textlength(text, font=font(size, "ExtraBold")) + 44
    d.rounded_rectangle((cx - w / 2, y, cx + w / 2, y + size + 22), radius=(size + 22) // 2, fill=fill)
    d.text((cx, y + (size + 22) / 2), text, font=font(size, "ExtraBold"), fill=color, anchor="mm")


def match_card(league: str, when: str, home: dict, away: dict, probs: tuple[float, float, float],
               tip: str, center: str, brand: str = "", sport: str = "football") -> bytes:
    """Превью матча. probs — П1/Х/П2 (в видах спорта без ничьей Х = 0), center — строка под временем."""
    hc, ac = _rgb(home["color"]), _rgb(away["color"], (180, 40, 40))
    img, d = _background(hc, ac)
    img = _sport_icon(img, sport)
    d = ImageDraw.Draw(img)
    _title(d, league)

    for team, cx, col in ((home, 300, hc), (away, 980, ac)):
        ini = "".join(w[0] for w in team["ru"].split()[:2]).upper()
        logo = _logo(team.get("logo"), 230, ini, col)
        img.paste(logo, (cx - logo.width // 2, 130 + (230 - logo.height) // 2), logo)
        _centered_lines(d, team["ru"], cx, 380, 400, 40)

    time_part, _, date_part = when.partition(" · ")
    d.text((W / 2, 210), time_part, font=font(76, "ExtraBold"), fill=WHITE, anchor="mm")
    d.text((W / 2, 272), date_part.upper(), font=font(26, "Medium"), fill=MUTED, anchor="mm")
    d.text((W / 2, 330), center, font=font(30), fill=ACCENT, anchor="mm")

    # полоса вероятностей П1 / Х / П2
    x0, x1, y0, bh = 120, W - 120, 500, 46
    total = x1 - x0
    xs = x0
    for p, c, name in zip(probs, (C_HOME, C_DRAW, C_AWAY), ("П1", "Х", "П2")):
        if p <= 0:
            continue
        w = max(int(total * p), 2)
        d.rounded_rectangle((xs, y0, xs + w, y0 + bh), radius=10, fill=c)
        if w > 110:
            d.text((xs + w / 2, y0 + bh / 2), f"{name} {p * 100:.0f}%", font=font(24), fill=WHITE, anchor="mm")
        elif w > 46:
            d.text((xs + w / 2, y0 + bh / 2), f"{p * 100:.0f}%", font=font(18), fill=WHITE, anchor="mm")
        xs += w

    # плашка с прогнозом
    _gold_box(img, (180, 585, W - 180, 670), radius=24)  # золотая плашка с градиентом — как в «Прогнозах дня»
    d = ImageDraw.Draw(img)
    size = 36
    while size > 22 and d.textlength(f"ПРОГНОЗ: {tip}", font=font(size, "ExtraBold")) > W - 420:
        size -= 2
    d.text((W / 2, 627), f"ПРОГНОЗ: {tip}", font=font(size, "ExtraBold"), fill=(20, 20, 30), anchor="mm")
    return _png(img, d, brand)


GREEN, RED = (39, 174, 96), (214, 48, 49)
AI_URL = "https://image.pollinations.ai/prompt/{prompt}?width=1280&height=780&nologo=true&seed={seed}"


def ai_card(prompt: str, title: str, subtitle: str = "", brand: str = "", sport: str = "") -> bytes:
    """Картинка от бесплатной нейросети Pollinations + наш заголовок поверх.

    Две попытки; если нейросеть так и не ответила — рисуем фон с иконкой вида спорта, пост всё равно выйдет.
    """
    img = None
    for _ in range(2):
        try:
            r = requests.get(AI_URL.format(prompt=quote(prompt), seed=random.randint(1, 10 ** 6)), timeout=90)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((W, 780)).crop((0, 0, W, H))  # без водяного знака
                break
        except Exception:
            continue
    if img is None:
        img, _ = _background((40, 80, 170), (180, 60, 40))
        if sport:
            img = _sport_icon(img, sport, cy=H // 2 - 90, r=230, alpha=60)
    # затемнение снизу, чтобы текст читался на любой картинке
    shade = Image.new("L", (1, H))
    for y in range(H):
        shade.putpixel((0, y), int(230 * max(0, (y - H * 0.35) / (H * 0.65)) ** 1.2))
    img = Image.composite(Image.new("RGB", (W, H), (8, 10, 24)), img, shade.resize((W, H)))
    d = ImageDraw.Draw(img)
    text = title.upper()
    lines, size = [text], 64
    while size > 30:  # короткий заголовок — крупно в одну строку, длинный — до трёх строк
        f = font(size, "ExtraBold")
        lines, cur = [], ""
        for word in text.split():
            test = f"{cur} {word}".strip()
            if d.textlength(test, font=f) <= W - 120 or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        if len(lines) <= (1 if size > 52 else 3) and all(d.textlength(x, font=f) <= W - 120 for x in lines):
            break
        size -= 4
    step = size + 10
    top = H - 140 - step * (len(lines) - 1)
    for k, line in enumerate(lines[:3]):
        d.text((W / 2, top + k * step), line, font=font(size, "ExtraBold"), fill=WHITE, anchor="mm")
    bar = top - size / 2 - 22  # золотая черта над заголовком, а не поперёк букв
    d.line([(W / 2 - 60, bar), (W / 2 + 60, bar)], fill=ACCENT, width=5)
    if subtitle:
        d.text((W / 2, H - 70), subtitle, font=font(30, "Medium"), fill=(220, 226, 245), anchor="mm")
    return _png(img, d, brand)


def result_card(league: str, home: dict, away: dict, hs: int, as_: int,
                verdicts: list[tuple[str, bool]], brand: str = "", sport: str = "football") -> bytes:
    """Итог матча: логотипы, счёт и плашки ЗАШЁЛ / МИМО по каждому прогнозу."""
    hc, ac = _rgb(home["color"]), _rgb(away["color"], (180, 40, 40))
    img, d = _background(hc, ac)
    img = _sport_icon(img, sport)
    d = ImageDraw.Draw(img)
    _title(d, f"Итог матча · {league}")
    _teams(img, d, home, away, hc, ac, top=110)
    d.text((W / 2, 210), f"{hs} : {as_}", font=font(110, "ExtraBold"), fill=WHITE, anchor="mm")
    d.text((W / 2, 290), "ФИНАЛ", font=font(26, "Medium"), fill=MUTED, anchor="mm")
    y = 470
    for name, hit in verdicts[:3]:
        text = f"{name} — {'ЗАШЁЛ' if hit else 'МИМО'}"
        size = 30
        while size > 20 and d.textlength(text, font=font(size, "ExtraBold")) > W - 300:
            size -= 2
        _pill(d, W // 2, y, text, GREEN if hit else RED, size=size)
        y += size + 40
    return _png(img, d, brand)


def live_card(league: str, home: dict, away: dict, hs, as_, headline: str, sub: str = "", brand: str = "",
              sport: str = "football", color: tuple = RED) -> bytes:
    """Live-событие: «МАТЧ НАЧАЛСЯ», «ГОЛ!», «ШАЙБА!», «КАРТА!» — логотипы, текущий счёт и плашка."""
    hc, ac = _rgb(home["color"]), _rgb(away["color"], (180, 40, 40))
    img, d = _background(hc, ac)
    img = _sport_icon(img, sport)
    d = ImageDraw.Draw(img)
    _title(d, f"LIVE · {league}")
    half = d.textlength(f"LIVE · {league}".upper(), font=font(30)) / 2
    d.ellipse((W / 2 - half - 32, 38, W / 2 - half - 14, 56), fill=RED)  # «красная точка» прямого эфира
    _teams(img, d, home, away, hc, ac, top=110)
    d.text((W / 2, 210), f"{hs} : {as_}", font=font(110, "ExtraBold"), fill=WHITE, anchor="mm")
    _pill(d, W // 2, 490, headline, color, size=40)
    if sub:
        size = 30
        while size > 20 and d.textlength(sub, font=font(size, "Medium")) > W - 200:
            size -= 2
        d.text((W / 2, 600), sub, font=font(size, "Medium"), fill=WHITE, anchor="mm")
    return _png(img, d, brand)


def table_card(title: str, subtitle: str, header: tuple, rows: list[tuple], brand: str = "",
               sport: str = "football") -> bytes:
    """Турнирная таблица / рейтинг: до 10 строк (место, команда, и 2–3 числовые колонки)."""
    img, d = _background((40, 90, 160), (30, 120, 90))
    img = _sport_icon(img, sport, cx=W - 150, cy=130, r=110, alpha=28)
    d = ImageDraw.Draw(img)
    _title(d, title, y=40, size=32)
    d.text((W / 2, 105), subtitle.upper(), font=font(30, "ExtraBold"), fill=WHITE, anchor="mm")
    cols = [150, 230, 880, 1000, 1120]
    y = 150
    for i, h in enumerate(header):
        d.text((cols[i], y), h, font=font(20, "Medium"), fill=MUTED, anchor="lm" if i < 2 else "mm")
    y += 28
    for k, row in enumerate(rows[:10]):
        d.rounded_rectangle((110, y, W - 110, y + 46), radius=12, fill=(28, 36, 70) if k % 2 == 0 else (22, 29, 58))
        for i, val in enumerate(row):
            txt = str(val)
            f = font(24, "ExtraBold" if i in (0, len(row) - 1) else "Bold")
            if i == 1:
                while d.textlength(txt, font=f) > 600 and len(txt) > 4:
                    txt = txt[:-2]
            d.text((cols[i], y + 23), txt, font=f, fill=ACCENT if i == 0 else WHITE, anchor="lm" if i < 2 else "mm")
        y += 52
    return _png(img, d, brand)




def _gold_box(img: Image.Image, box: tuple, radius: int = 26, top: tuple = None, bottom: tuple = None,
              edge: tuple = (255, 240, 180)) -> None:
    """Плашка с вертикальным градиентом и светлой обводкой (по умолчанию — золотая)."""
    top, bottom = top or GOLD_TOP, bottom or GOLD_BOTTOM
    x0, y0, x1, y1 = box
    grad = Image.new("RGB", (x1 - x0, y1 - y0))
    gd = ImageDraw.Draw(grad)
    for y in range(y1 - y0):
        t = y / max(y1 - y0 - 1, 1)
        gd.line([(0, y), (x1 - x0, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    mask = Image.new("L", grad.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, grad.width - 1, grad.height - 1), radius=radius, fill=255)
    img.paste(grad, (x0, y0), mask)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, outline=edge, width=3)


def express_card(legs: list[dict], total: float, p_all: float, day: str, brand: str = "",
                 title: str = "Экспресс дня", colors: tuple = ((150, 110, 20), (40, 60, 150))) -> bytes:
    """Экспресс: все события с логотипами, прогнозом и кэфом + золотая плашка с итоговым кэфом (до 6 событий)."""
    img, d = _background(*colors)
    _title(d, title, y=40, size=34)
    d.text((W / 2, 98), day.upper(), font=font(26, "Medium"), fill=MUTED, anchor="mm")
    n = min(len(legs), 6)
    row_h = {1: 92, 2: 92, 3: 92, 4: 78, 5: 64, 6: 56}[max(n, 1)]
    y = 128
    for leg in legs[:n]:
        d.rounded_rectangle((70, y, W - 70, y + row_h - 8), radius=16, fill=(22, 28, 56), outline=(60, 72, 110), width=2)
        cy = y + (row_h - 8) // 2
        tight = row_h < 70  # 5–6 событий: строки плотнее, одна строка текста
        d.text((100, cy - (0 if tight else 14)), pd_time(leg["kickoff"]), font=font(24 if tight else 26, "ExtraBold"),
               fill=ACCENT, anchor="lm")
        # только название турнира, без флага-эмодзи (шрифт их не рисует)
        league = "".join(c for c in leg.get("league", "").split("·")[-1] if ord(c) < 0x2000).strip()
        size = 17
        while size > 12 and d.textlength(league, font=font(size, "Medium")) > 200:
            size -= 1
        if not tight:
            d.text((100, cy + 16), league, font=font(size, "Medium"), fill=MUTED, anchor="lm")
        lx = 330
        for k, side in enumerate(("home", "away")):  # два маленьких логотипа
            logo = _logo((leg.get("logos") or [None, None])[k], 40 if tight else 52, "".join(w[0] for w in leg[side].split()[:2]).upper(),
                         _rgb((leg.get("colors") or ["3b4a7a", "3b4a7a"])[k]))
            img.paste(logo, (lx + k * 60, cy - logo.height // 2), logo)
        match = f"{leg['home']} — {leg['away']}"
        size = 26
        while size > 16 and d.textlength(match, font=font(size)) > 430:
            size -= 2
        d.text((470, cy - (12 if tight else 14)), match, font=font(size - (4 if tight else 0)), fill=WHITE, anchor="lm")
        pick = leg["label"]
        size = 22
        while size > 14 and d.textlength(pick, font=font(size, "Medium")) > 430:
            size -= 2
        d.text((470, cy + (13 if tight else 16)), pick, font=font(size - (4 if tight else 0), "Medium"),
               fill=(130, 220, 160), anchor="lm")
        _pill(d, W - 160, cy - (20 if tight else 25), f"{leg['odds']:.2f}", (46, 60, 110), size=22 if tight else 26)
        y += row_h
    # золотая плашка с итоговым кэфом
    box = (150, max(470, y + 6), W - 150, max(470, y + 6) + 180) if n <= 4 else (150, y + 6, W - 150, y + 156)
    _gold_box(img, box)
    d = ImageDraw.Draw(img)
    dark = (40, 28, 6)
    bh = box[3] - box[1]
    d.text((box[0] + 50, box[1] + bh * 0.25), "ИТОГОВЫЙ КЭФ", font=font(28, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[0] + 50, box[1] + bh * 0.66), f"{total:.2f}", font=font(84 if bh > 160 else 70, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[2] - 50, box[1] + bh * 0.33), "ШАНС, ЧТО ЗАЙДЁТ", font=font(22, "Bold"), fill=dark, anchor="rm")
    d.text((box[2] - 50, box[1] + bh * 0.66), f"{p_all * 100:.0f}%", font=font(64 if bh > 160 else 54, "ExtraBold"), fill=dark, anchor="rm")
    if box[3] < 670:
        d.text((W / 2, 680), f"{len(legs[:n])} событий в одной ставке" if n >= 5 else f"{len(legs[:n])} события в одной ставке",
               font=font(22, "Medium"), fill=MUTED, anchor="mm")
    return _png(img, d, brand)


TEAL_TOP, TEAL_BOTTOM = (110, 235, 220), (20, 150, 160)


def _fit(d: ImageDraw.ImageDraw, text: str, size: int, max_w: int, weight: str = "Bold", min_size: int = 14):
    """Подбираем размер шрифта, чтобы строка влезла в max_w."""
    while size > min_size and d.textlength(text, font=font(size, weight)) > max_w:
        size -= 1
    return font(size, weight)


def _check(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 20) -> None:
    """Зелёный кружок с белой галочкой (рисуем сами — эмодзи шрифт не умеет)."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN)
    d.line([(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
           fill=WHITE, width=max(3, r // 5), joint="curve")


def value_card(picks: list[dict], day: str, brand: str = "") -> bytes:
    """Value дня: ставки, где лучший кэф выше справедливой цены — с логотипами и перевесом каждой."""
    img, d = _background((20, 140, 150), (40, 60, 150))
    img = _sport_icon(img, "football", cx=W - 120, cy=110, r=90, alpha=22)
    d = ImageDraw.Draw(img)
    _title(d, "Value дня", y=40, size=34)
    d.text((W / 2, 98), f"{day} · ставки дороже справедливой цены".upper(), font=font(22, "Medium"), fill=MUTED,
           anchor="mm")
    n = min(len(picks), 4)
    row_h = 92 if n <= 3 else 80
    y = 128
    for x in picks[:n]:
        d.rounded_rectangle((60, y, W - 60, y + row_h - 10), radius=18, fill=(18, 34, 58), outline=(50, 110, 120), width=2)
        cy = y + (row_h - 10) // 2
        d.text((90, cy - 14), pd_time(x["kickoff"]), font=font(26, "ExtraBold"), fill=ACCENT, anchor="lm")
        league = "".join(c for c in str(x.get("league", "")).split("·")[-1] if ord(c) < 0x2000).strip()
        d.text((90, cy + 16), league, font=_fit(d, league, 17, 190, "Medium", 12), fill=MUTED, anchor="lm")
        for k, side in enumerate(("home", "away")):
            logo = _logo((x.get("logos") or [None, None])[k], 50, "".join(w[0] for w in x[side].split()[:2]).upper(),
                         _rgb((x.get("colors") or ["3b4a7a", "8a2b2b"])[k]))
            img.paste(logo, (300 + k * 58, cy - logo.height // 2), logo)
        match = f"{x['home']} — {x['away']}"
        d.text((430, cy - 14), match, font=_fit(d, match, 26, 400), fill=WHITE, anchor="lm")
        d.text((430, cy + 16), x["label"], font=_fit(d, x["label"], 22, 400, "Medium"), fill=TEAL_TOP, anchor="lm")
        # кэф против справедливой цены и перевес
        d.text((W - 330, cy - 14), f"{x['odds']:.2f}", font=font(30, "ExtraBold"), fill=WHITE, anchor="mm")
        d.text((W - 330, cy + 17), f"справ. {1 / x['p']:.2f}", font=font(16, "Medium"), fill=MUTED, anchor="mm")
        _pill(d, W - 160, cy - 24, f"+{100 * x['edge']:.1f}%", (30, 140, 90), size=24)
        y += row_h
    best = max(picks[:n], key=lambda x: x["edge"])
    box = (150, 480, W - 150, 650)
    _gold_box(img, box, top=TEAL_TOP, bottom=TEAL_BOTTOM, edge=(200, 255, 245))
    d = ImageDraw.Draw(img)
    dark = (6, 40, 44)
    d.text((box[0] + 50, 522), "ЛУЧШИЙ ПЕРЕВЕС ДНЯ", font=font(26, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[0] + 50, 595), f"+{100 * best['edge']:.1f}%", font=font(80, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[2] - 50, 535), "СТАВОК С ПЕРЕВЕСОМ", font=font(22, "Bold"), fill=dark, anchor="rm")
    d.text((box[2] - 50, 595), str(len(picks)), font=font(64, "ExtraBold"), fill=dark, anchor="rm")
    d.text((W / 2, 682), "перевес = насколько кэф выше честного", font=font(20, "Medium"), fill=MUTED, anchor="mm")
    return _png(img, d, brand)


def streak_card(rows: list[dict], n: int, total: float, brand: str = "", sport: str = "football") -> bytes:
    """Серия заходов: огромная цифра серии, матчи с зелёными галочками и «кэф, если бы это был экспресс»."""
    img, d = _background((30, 140, 70), (170, 110, 20))
    img = _sport_icon(img, sport, cx=W - 150, cy=150, r=120, alpha=24)
    d = ImageDraw.Draw(img)
    _title(d, "Серия заходов", y=40, size=32)
    word = "заход" if n % 10 == 1 and n % 100 != 11 else "захода" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "заходов"
    num_w = d.textlength(str(n), font=font(96, "ExtraBold"))
    text_w = d.textlength(f"{word} подряд".upper(), font=font(40, "ExtraBold"))
    x0 = (W - num_w - 24 - text_w) / 2  # цифра и подпись вместе — по центру
    d.text((x0, 128), str(n), font=font(96, "ExtraBold"), fill=ACCENT, anchor="lm")
    d.text((x0 + num_w + 24, 128), f"{word} подряд".upper(), font=font(40, "ExtraBold"), fill=WHITE, anchor="lm")
    shown = rows[:5]
    row_h = 58
    y = 190
    for r in shown:
        d.rounded_rectangle((70, y, W - 70, y + row_h - 8), radius=14, fill=(20, 32, 40), outline=(50, 110, 70), width=2)
        cy = y + (row_h - 8) // 2
        _check(d, 108, cy, 17)
        d.text((145, cy), r["score"], font=font(24, "ExtraBold"), fill=ACCENT, anchor="lm")
        match = f"{r['home']} — {r['away']}"
        d.text((235, cy), match, font=_fit(d, match, 23, 470), fill=WHITE, anchor="lm")
        d.text((725, cy), r["label"], font=_fit(d, r["label"], 20, 300, "Medium"), fill=(140, 230, 160), anchor="lm")
        d.text((W - 100, cy), f"{r['odds']:.2f}", font=font(24, "ExtraBold"), fill=WHITE, anchor="rm")
        y += row_h
    if len(rows) > len(shown):
        d.text((W / 2, y + 6), f"…и ещё {len(rows) - len(shown)}", font=font(20, "Medium"), fill=MUTED, anchor="mm")
    box = (150, 500, W - 150, 655)
    _gold_box(img, box)
    d = ImageDraw.Draw(img)
    dark = (40, 28, 6)
    d.text((box[0] + 50, 540), "ЕСЛИ БЫ ЭТО БЫЛ ЭКСПРЕСС", font=font(26, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[0] + 50, 607), f"кэф {total:,.2f}".replace(",", " "), font=font(66, "ExtraBold"), fill=dark, anchor="lm")
    d.text((box[2] - 50, 545), "ЗАШЛО ПОДРЯД", font=font(22, "Bold"), fill=dark, anchor="rm")
    d.text((box[2] - 50, 607), f"{n} из {n}", font=font(52, "ExtraBold"), fill=dark, anchor="rm")
    d.text((W / 2, 685), "серии заканчиваются — играйте по банку", font=font(20, "Medium"), fill=MUTED, anchor="mm")
    return _png(img, d, brand)


def pd_time(kickoff) -> str:
    """«21:00» из ISO-времени матча."""
    s = str(kickoff)
    return s[11:16] if len(s) >= 16 else s


def schedule_card(day: str, rows: list[tuple[str, str, str, str]], more: int, brand: str = "",
                  heading: str = "Матчи дня", sport: str = "football") -> bytes:
    """Список матчей: до 8 строк (время, хозяева, гости, турнир) — расписание, теннис, экспресс."""
    img, d = _background((40, 80, 170), (130, 40, 120))
    img = _sport_icon(img, sport, cx=W - 170, cy=H - 150, r=150, alpha=30)
    d = ImageDraw.Draw(img)
    _title(d, heading, y=50, size=34)
    d.text((W / 2, 120), day.upper(), font=font(44, "ExtraBold"), fill=WHITE, anchor="mm")
    y = 175
    for t, h, a, lg in rows[:8]:
        d.rounded_rectangle((90, y, W - 90, y + 50), radius=14, fill=(24, 32, 64), outline=(70, 82, 120), width=2)
        d.text((120, y + 25), t, font=font(28, "ExtraBold"), fill=ACCENT, anchor="lm")
        match = f"{h} — {a}"
        size = 28
        while size > 18 and d.textlength(match, font=font(size)) > 700:
            size -= 2
        d.text((240, y + 25), match, font=font(size), fill=WHITE, anchor="lm")
        d.text((W - 120, y + 25), lg, font=font(20, "Medium"), fill=MUTED, anchor="rm")
        y += 60
    if more > 0:
        d.text((W / 2, y + 22), f"и ещё {more} матч(ей) — смотри список в посте", font=font(26, "Medium"),
               fill=MUTED, anchor="mm")
    return _png(img, d, brand)


def stats_card(title: str, rows: list[tuple[str, int, int, float | None]], brand: str = "") -> bytes:
    """Статистика: период, угадано из скольких, процент, ROI."""
    img, d = _background((30, 130, 90), (40, 80, 170))
    img = _sport_icon(img, "football", cx=W - 140, cy=120, r=110, alpha=26)
    d = ImageDraw.Draw(img)
    _title(d, "Статистика бота", y=50, size=34)
    d.text((W / 2, 125), title.upper(), font=font(40, "ExtraBold"), fill=WHITE, anchor="mm")
    y = 200
    step = min(120, (H - 230) // max(len(rows), 1))  # 4 строки — как раньше, 5 — плотнее, чтобы влезли
    box = step - 20
    for name, hits, n, roi in rows:
        d.rounded_rectangle((110, y, W - 110, y + box), radius=20, fill=(28, 36, 70))
        d.text((150, y + box / 2), name, font=font(32), fill=WHITE, anchor="lm")
        if n:
            share = hits / n
            d.text((720, y + box / 2), f"{hits}/{n} · {share * 100:.0f}%", font=font(38, "ExtraBold"),
                   fill=GREEN if share >= 0.5 else RED, anchor="mm")
            if roi is not None:
                d.text((W - 150, y + box / 2), f"ROI {roi:+.1f}%", font=font(30), fill=ACCENT, anchor="rm")
        else:
            d.text((720, y + box / 2), "матчей не было", font=font(30, "Medium"), fill=MUTED, anchor="mm")
        y += step
    return _png(img, d, brand)


def _ring(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, p: float, color: tuple) -> None:
    """Кольцо-индикатор вероятности с процентом в центре."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(52, 60, 96), width=10)
    d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * p, fill=color, width=10)
    d.text((cx, cy - 6), f"{100 * p:.0f}%", font=font(24, "ExtraBold"), fill=WHITE, anchor="mm")
    d.text((cx, cy + 16), "шанс", font=font(13, "Medium"), fill=MUTED, anchor="mm")


def top_card(picks: list[dict], day: str, brand: str = "") -> bytes:
    """⭐ Прогнозы дня: три «билета» с логотипами, прогнозом, кэфом и кольцом вероятности."""
    img, d = _background((255, 170, 0), (130, 60, 255), style=random.choice(("rays", "diagonal", "blobs")))
    d.text((W / 2, 62), "ПРОГНОЗЫ ДНЯ", font=font(54, "ExtraBold"), fill=WHITE, anchor="mm")
    hw = d.textlength("ПРОГНОЗЫ ДНЯ", font=font(54, "ExtraBold")) / 2
    for sx in (-1, 1):  # звёздочки по бокам заголовка
        cx = W / 2 + sx * (hw + 40)
        pts = [(cx + (18 if i % 2 == 0 else 8) * math.cos(math.radians(-90 + 36 * i)),
                62 + (18 if i % 2 == 0 else 8) * math.sin(math.radians(-90 + 36 * i))) for i in range(10)]
        d.polygon(pts, fill=ACCENT)
    d.text((W / 2, 112), f"{day.upper()} · САМОЕ НАДЁЖНОЕ ПО ЛИНИИ", font=font(22, "Medium"), fill=MUTED, anchor="mm")
    n = len(picks)
    cw, gap = 372, 22
    x0 = (W - n * cw - (n - 1) * gap) // 2
    for i, p in enumerate(picks):
        x, y0, y1 = x0 + i * (cw + gap), 146, 652
        hc, ac = _rgb(p["home"].get("color", "3b4a7a")), _rgb(p["away"].get("color", "8a2b2b"))
        # стеклянная карточка с цветной полосой сверху
        panel = Image.new("RGBA", (cw, y1 - y0), (0, 0, 0, 0))
        pd_ = ImageDraw.Draw(panel)
        pd_.rounded_rectangle((0, 0, cw - 1, y1 - y0 - 1), radius=28, fill=(18, 24, 50, 215),
                              outline=(255, 255, 255, 40), width=2)
        for k in range(cw):  # градиентная полоса цветами команд
            pd_.line([(k, 0), (k, 8)], fill=_mix(hc, ac, k / cw) + (255,))
        mask = Image.new("L", panel.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, y1 - y0 - 1), radius=28, fill=255)
        img.paste(panel, (x, y0), Image.composite(panel, Image.new("RGBA", panel.size), mask).split()[3])
        d = ImageDraw.Draw(img)
        # номер
        d.ellipse((x + 18, y0 + 24, x + 70, y0 + 76), fill=ACCENT)
        d.text((x + 44, y0 + 50), str(i + 1), font=font(30, "ExtraBold"), fill=(25, 20, 10), anchor="mm")
        d.text((x + cw - 22, y0 + 40), p["time"], font=font(30, "ExtraBold"), fill=ACCENT, anchor="ra")
        d.text((x + cw - 22, y0 + 76), p["league"], font=_fit(d, p["league"], 18, 230, "Medium"), fill=MUTED, anchor="ra")
        # логотипы внахлёст
        size = 100
        lh = _logo(p["home"].get("logo"), size, p["home"]["ru"][:2].upper(), hc)
        la = _logo(p["away"].get("logo"), size, p["away"]["ru"][:2].upper(), ac)
        cx = x + cw // 2
        img.paste(lh, (cx - size + 12, y0 + 102), lh)
        img.paste(la, (cx - 12, y0 + 102), la)
        d = ImageDraw.Draw(img)
        _centered_lines(d, p["home"]["ru"], cx, y0 + 214, cw - 40, 26)
        d.text((cx, y0 + 276), "—", font=font(22), fill=MUTED, anchor="mm")
        _centered_lines(d, p["away"]["ru"], cx, y0 + 288, cw - 40, 26)
        # прогноз: золотая плашка + кэф + кольцо
        _gold_box(img, (x + 20, y0 + 352, x + cw - 20, y0 + 404), radius=18)
        d = ImageDraw.Draw(img)
        d.text((cx, y0 + 378), p["label"], font=_fit(d, p["label"], 26, cw - 70, "ExtraBold"), fill=(30, 22, 6), anchor="mm")
        # две ровные колонки: «КЭФ» и «ШАНС» с полоской вероятности
        lx, rx, ly = x + cw // 4, x + 3 * cw // 4, y0 + 418
        d.line([(cx, ly + 6), (cx, ly + 72)], fill=(70, 80, 120), width=2)
        for colx, lab, val, colr in ((lx, "КЭФ", f"{p['odds']:.2f}", WHITE), (rx, "ШАНС", f"{100 * p['p']:.0f}%", (46, 204, 113))):
            d.text((colx, ly + 10), lab, font=font(16, "Medium"), fill=MUTED, anchor="mm")
            d.text((colx, ly + 40), val, font=font(36, "ExtraBold"), fill=colr, anchor="mm")
        bw = cw // 2 - 70
        d.rounded_rectangle((rx - bw / 2, ly + 68, rx + bw / 2, ly + 74), radius=3, fill=(52, 60, 96))
        d.rounded_rectangle((rx - bw / 2, ly + 68, rx - bw / 2 + max(6, bw * p["p"]), ly + 74), radius=3, fill=(46, 204, 113))
    return _png(img, d, brand)


def news_card(photo_url: str | None, title: str, tag: str, brand: str = "", sport: str = "", fallback_prompt: str = "") -> bytes:
    """Новость: фото из источника на весь кадр + наше оформление поверх (плашка рубрики, заголовок, градиент).

    Если фото нет или оно не скачалось — картинка от нейросети, а если и она недоступна — наш фирменный фон.
    """
    photo = None
    if photo_url:
        try:
            r = requests.get(photo_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and len(r.content) > 5000:
                photo = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            photo = None
    if photo is None:
        return ai_card(fallback_prompt or "sports arena at night", title, tag, brand, sport=sport)
    # кадрирование «cover»: заполняем 1280×720 без полей, чуть выше центра — там обычно лица и мяч
    k = max(W / photo.width, H / photo.height)
    photo = photo.resize((int(photo.width * k) + 1, int(photo.height * k) + 1), Image.LANCZOS)
    left, top = (photo.width - W) // 2, int((photo.height - H) * 0.35)
    img = photo.crop((left, top, left + W, top + H))
    # фирменная тонировка: тёмный градиент снизу и цветной отсвет слева
    shade = Image.new("L", (1, H))
    for y in range(H):
        shade.putpixel((0, y), int(240 * max(0, (y - H * 0.30) / (H * 0.70)) ** 1.15))
    img = Image.composite(Image.new("RGB", (W, H), (8, 10, 24)), img, shade.resize((W, H)))
    tint = Image.new("RGB", (W, H), random.choice([(255, 170, 0), (0, 160, 255), (230, 40, 80), (120, 80, 255)]))
    side = Image.new("L", (W, 1))
    for x in range(W):
        side.putpixel((x, 0), int(70 * max(0, 1 - x / (W * 0.45))))
    img = Image.composite(tint, img, side.resize((W, H)))
    d = ImageDraw.Draw(img)
    # заголовок: до трёх строк, подбираем размер
    text = title.upper()
    size = 58
    while True:
        f = font(size, "ExtraBold")
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= W - 140 or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= 3 or size <= 34:
            break
        size -= 4
    step = size + 12
    top_y = H - 70 - step * len(lines)
    for k_, line in enumerate(lines[:3]):
        d.text((70, top_y + k_ * step), line, font=font(size, "ExtraBold"), fill=WHITE, anchor="la")
    # плашка рубрики над заголовком и золотая черта слева
    tw = d.textlength(tag.upper(), font=font(22, "ExtraBold")) + 36
    _gold_box(img, (70, top_y - 58, int(70 + tw), top_y - 18), radius=20)
    d = ImageDraw.Draw(img)
    d.text((70 + tw / 2, top_y - 38), tag.upper(), font=font(22, "ExtraBold"), fill=(30, 22, 6), anchor="mm")
    d.rectangle((44, top_y - 4, 50, top_y + step * len(lines[:3]) - 14), fill=ACCENT)
    return _png(img, d, brand)
