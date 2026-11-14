"""Editorial covers in the channel's existing Montserrat and gold sports style."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import card

DATA = Path(__file__).resolve().parent.parent / "data"
SPORTS = (("🏒", "hockey"), ("🏀", "basketball"), ("🎾", "tennis"), ("🎮", "esports"), ("⚽", "football"))


def _normal(name):
    name = str(name).casefold().replace("ё", "е")
    return re.sub(r"[^\wа-я]+", " ", name).strip()


def match_details(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pair = next((line for line in lines if " — " in line), "")
    pair = re.sub(r"^[^\wА-Яа-яЁё]+", "", pair)
    home_name, separator, away_name = pair.partition(" — ")
    if not separator:
        return None
    league = next((line.lstrip("🏆 ") for line in lines if line.startswith("🏆")), "")
    sport = next((sport for emoji, sport in SPORTS if emoji in text), "football")
    matches = []
    for filename in ("matches.json", "other.json"):
        try:
            source = json.loads((DATA / filename).read_text(encoding="utf-8"))
            matches += [m for m in source.values() if isinstance(m, dict) and isinstance(m.get("home"), dict)
                        and isinstance(m.get("away"), dict)]
        except (OSError, ValueError, AttributeError):
            continue
    wanted = (_normal(home_name), _normal(away_name))
    candidates = [m for m in matches if (_normal(m["home"].get("ru", "")), _normal(m["away"].get("ru", ""))) == wanted]
    def distance(match):
        try:
            return abs(datetime.fromisoformat(match["kickoff"]).timestamp() - datetime.now(timezone.utc).timestamp())
        except (KeyError, ValueError, TypeError):
            return float("inf")
    found = min(candidates, key=distance) if candidates else None
    teams = []
    for index, name in enumerate((home_name, away_name)):
        team = found[("home", "away")[index]] if found else next(
            (team for m in matches for team in (m["home"], m["away"]) if _normal(team.get("ru", "")) == _normal(name)), {})
        # Only presentation fields enter this renderer. Forecasts and odds never do.
        teams.append({"ru": name, "logo": team.get("logo"), "color": team.get("color")})
    return teams[0], teams[1], league or (found or {}).get("div", "Спорт"), (found or {}).get("sport") or sport


def match_cover(text, brand="@aistavvit"):
    details = match_details(text)
    if not details:
        return None
    home, away, league, sport = details
    hc = card._rgb(home.get("color") or "1948a0")
    ac = card._rgb(away.get("color") or "a52c47")
    img, _ = card._background(hc, ac, style="diagonal")
    img = card._sport_icon(img, sport, cx=640, cy=370, r=235, alpha=22)
    d = ImageDraw.Draw(img)
    d.text((78, 70), "АИ СТАВИТ / МАТЧ-ЦЕНТР", font=card.font(23, "ExtraBold"), fill=card.ACCENT)
    card._pill(d, 1110, 54, "LIVE", (198, 44, 63), size=22)
    d.text((78, 113), "МАТЧ НАЧАЛСЯ", font=card.font(60, "ExtraBold"), fill=card.WHITE)
    league = card.safe(league)
    d.text((80, 193), league, font=card._fit(d, league, 26, 1100, "Medium"), fill=(195, 206, 229))
    for team, cx, color in ((home, 306, hc), (away, 974, ac)):
        panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        pd.rounded_rectangle((cx - 226, 251, cx + 226, 563), radius=30,
                             fill=(10, 18, 34, 200), outline=tuple(min(255, c + 65) for c in color) + (180,), width=2)
        pd.line((cx - 174, 563, cx + 174, 563), fill=card.ACCENT + (210,), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
        initials = "".join(word[0] for word in team["ru"].split()[:2]).upper()
        logo = card._logo(team.get("logo"), 176, initials, color)
        # A soft team-colored halo keeps dark and white logos readable alike.
        halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((cx - 114, 265, cx + 114, 473), fill=color + (140,))
        img = Image.alpha_composite(img.convert("RGBA"), halo.filter(ImageFilter.GaussianBlur(28))).convert("RGB")
        img.paste(logo, (cx - logo.width // 2, 281 + (176 - logo.height) // 2), logo)
        d = ImageDraw.Draw(img)
        card._centered_lines(d, team["ru"], cx, 480, 402, 32)
    d = ImageDraw.Draw(img)
    d.text((640, 369), "VS", font=card.font(63, "ExtraBold"), fill=card.ACCENT, anchor="mm")
    d.line((605, 425, 675, 425), fill=(255, 196, 0), width=3)
    d.rounded_rectangle((80, 602, 1200, 666), radius=16, fill=(13, 22, 42), outline=(57, 72, 104))
    d.ellipse((108, 626, 120, 638), fill=(255, 78, 99))
    d.text((140, 632), "СЛЕДИМ ЗА ИГРОЙ", font=card.font(23, "ExtraBold"), fill=card.WHITE, anchor="lm")
    d.text((1174, 632), "СОБЫТИЯ · РЕЗУЛЬТАТЫ", font=card.font(20, "Medium"), fill=(182, 196, 222), anchor="rm")
    return card._png(img, d, brand)


def topic_cover(kicker, title, subtitle, lines, colors, sport="football", brand="@aistavvit"):
    img, _ = card._background(*colors, style="diagonal")
    img = card._sport_icon(img, sport, cx=1085, cy=330, r=180, alpha=160)
    d = ImageDraw.Draw(img)
    d.text((80, 88), card.safe(kicker).upper(), font=card.font(26, "ExtraBold"), fill=card.ACCENT)
    d.line((82, 137, 195, 137), fill=card.ACCENT, width=4)
    words = card.safe(title).split()
    for size in range(62, 31, -2):
        wrapped, current = [], ""
        for word in words:
            candidate = (current + " " + word).strip()
            if current and d.textlength(candidate, font=card.font(size, "ExtraBold")) > 800:
                wrapped.append(current)
                current = word
            else:
                current = candidate
        if current:
            wrapped.append(current)
        if len(wrapped) <= 4:
            break
    for i, line in enumerate(wrapped[:4]):
        d.text((78, 188 + i * (size + 12)), line, font=card.font(size, "ExtraBold"), fill=card.WHITE)
    if subtitle:
        d.text((82, 505), subtitle, font=card._fit(d, subtitle, 26, 1100, "Medium"), fill=(202, 211, 232))
    if lines:
        d.rounded_rectangle((80, 558, 1200, 656), radius=20, fill=(11, 20, 39), outline=(65, 78, 110))
        for i, line in enumerate(lines[:2]):
            d.text((108, 576 + i * 34), line, font=card._fit(d, line, 22, 1050, "Medium"), fill=(210, 220, 240))
    return card._png(img, d, brand)
