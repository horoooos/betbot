"""🎬 Короткие вертикальные ролики (1080×1920, 15 с) для ВК Клипов, YouTube Shorts, Дзена и Telegram.

Каждый день в 12:00 МСК бот берёт лучший заход вчерашнего дня («Прогноз: ТБ 2.5 → итог 3:1 ✅»), а если зашёл
экспресс — ещё и ролик про него. Ролик из трёх сцен с плавными переходами:
  1) «ПРОГНОЗ БОТА» — логотипы, команды, ставка и кэф;  2) «ИТОГ» — счёт и зелёная плашка «ЗАШЛО»;
  3) призыв — «вчера бот: 7 из 10», «бесплатные прогнозы каждый день», @aistavvit и сайт.
Публикация — у каждой платформы свой заголовок, описание и хештеги: Telegram-канал, стена ВК (видео), YouTube Shorts
(бесплатный API, секреты YT_*), а для Дзена — ролик и готовый текст владельцу в личку (Дзен не даёт загружать видео программно).
"""
from __future__ import annotations

import io
import json
import math
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFilter

from . import card

VW, VH = 1080, 1920
SCENE, FADE, FPS = 5.0, 0.5, 30
ROOT = Path(__file__).resolve().parent.parent
GOLD, GREEN, WHITE, MUTED = (255, 196, 0), (46, 204, 113), (255, 255, 255), (170, 182, 215)
SPORT_RU = {"football": "ФУТБОЛ", "hockey": "ХОККЕЙ", "basketball": "БАСКЕТБОЛ", "tennis": "ТЕННИС", "esports": "КИБЕРСПОРТ"}


def _bg(top: tuple, bottom: tuple) -> Image.Image:
    """Вертикальный фон: градиент, цветные пятна и мягкая сетка — в стиле карточек канала."""
    img = Image.new("RGB", (VW, VH))
    d = ImageDraw.Draw(img)
    for y in range(VH):
        k = y / VH
        d.line([(0, y), (VW, y)], fill=tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)))
    glow = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-300, -200, 700, 800), fill=(255, 196, 0, 60))
    g.ellipse((500, 1200, 1500, 2200), fill=(90, 120, 255, 70))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(160))).convert("RGB")
    d = ImageDraw.Draw(img)
    for x in range(0, VW, 90):
        d.line([(x, 0), (x, VH)], fill=(255, 255, 255, 10) if False else tuple(min(255, c + 6) for c in top), width=1)
    # фирменные уголки
    for (x, y, sx, sy) in ((40, 40, 1, 1), (VW - 40, 40, -1, 1), (40, VH - 40, 1, -1), (VW - 40, VH - 40, -1, -1)):
        d.line([(x, y), (x + 90 * sx, y)], fill=GOLD, width=6)
        d.line([(x, y), (x, y + 90 * sy)], fill=GOLD, width=6)
    return img


def _center(d: ImageDraw.ImageDraw, y: float, text: str, size: int, fill=WHITE, weight="ExtraBold", max_w: int = VW - 140):
    f = card.font(size, weight)
    while size > 28 and d.textlength(text, font=f) > max_w:
        size -= 4
        f = card.font(size, weight)
    d.text((VW / 2, y), text, font=f, fill=fill, anchor="mm")


def _pill(img: Image.Image, y: int, text: str, fill: tuple, fg=(20, 16, 6), size: int = 64) -> None:
    d = ImageDraw.Draw(img)
    f = card.font(size, "ExtraBold")
    w = d.textlength(text, font=f) + 110
    x0 = (VW - w) / 2
    d.rounded_rectangle((x0, y, x0 + w, y + size + 56), radius=(size + 56) // 2, fill=fill)
    d.text((VW / 2, y + (size + 56) / 2), text, font=f, fill=fg, anchor="mm")


def _check(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color=GREEN) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .35)], fill=WHITE, width=max(4, int(r / 5)))


def _logo(url: str | None, name: str) -> Image.Image:
    return card._logo(url, 300, "".join(w[0] for w in name.split()[:2]).upper(), (40, 60, 120))


def _scene_pick(m: dict) -> Image.Image:
    img = _bg((18, 26, 70), (8, 10, 30))
    d = ImageDraw.Draw(img)
    _center(d, 190, "АИ СТАВИТ", 54, GOLD)
    _center(d, 270, f"{SPORT_RU.get(m['sport'], '')} · {m.get('league') or ''}".strip(" ·"), 34, MUTED, "Bold")
    _center(d, 420, "ПРОГНОЗ БОТА", 96)
    for i, (key, url) in enumerate((("home", m.get("hl")), ("away", m.get("al")))):
        lg = _logo(url, m[key]).resize((300, 300))
        x = 130 if i == 0 else VW - 130 - 300
        img.paste(lg, (x, 620), lg if lg.mode == "RGBA" else None)
        _center_x = x + 150
        f = card.font(46, "ExtraBold")
        name = m[key] if d.textlength(m[key], font=f) < 420 else m[key][:16] + "…"
        d.text((_center_x, 980), name, font=f, fill=WHITE, anchor="mm")
    _center(d, 770, "VS", 80, GOLD)
    _pill(img, 1170, f"{m['tip']} · {m['odds']:.2f}", GOLD, size=72)
    if m.get("p"):
        _center(d, 1400, f"шанс по модели — {100 * m['p']:.0f}%", 48, WHITE, "Bold")
    _center(d, 1700, "смотри, чем закончилось →", 44, MUTED, "Bold")
    return img


def _scene_result(m: dict) -> Image.Image:
    img = _bg((10, 60, 40), (6, 14, 24))
    d = ImageDraw.Draw(img)
    _center(d, 300, "ИТОГ МАТЧА", 84)
    _center(d, 420, f"{m['home']} — {m['away']}", 50, MUTED, "Bold")
    _center(d, 760, m["score"].replace(":", " : "), 300)
    _check(d, VW / 2, 1150, 120)
    _pill(img, 1340, "ЗАШЛО", GREEN, fg=WHITE, size=90)
    _center(d, 1600, f"{m['tip']} · кэф {m['odds']:.2f}", 56, GOLD)
    return img


def _scene_express(ex: dict) -> Image.Image:
    img = _bg((60, 30, 90), (8, 10, 30))
    d = ImageDraw.Draw(img)
    _center(d, 260, ex.get("title", "ЭКСПРЕСС").upper(), 80, GOLD)
    _center(d, 360, "ЗАШЁЛ ЦЕЛИКОМ", 64)
    y = 520
    for g in ex["legs"][:6]:
        d.rounded_rectangle((80, y, VW - 80, y + 170), radius=34, fill=(20, 26, 60), outline=(70, 90, 150), width=3)
        _check(d, 160, y + 85, 44)
        f = card.font(40, "ExtraBold")
        t = f"{g['home']} — {g['away']}"
        while d.textlength(t, font=f) > VW - 340 and len(t) > 10:
            t = t[:-2]
        d.text((230, y + 60), t, font=f, fill=WHITE, anchor="lm")
        d.text((230, y + 120), f"{g['label']} · {g['odds']:.2f}  ({g.get('score', '')})", font=card.font(34, "Bold"), fill=GOLD, anchor="lm")
        y += 200
    _pill(img, min(y + 40, 1660), f"ОБЩИЙ КЭФ {ex['odds']:.2f}", GOLD, size=70)
    return img


def _scene_cta(day_hits: int, day_n: int) -> Image.Image:
    img = _bg((20, 24, 70), (6, 8, 24))
    d = ImageDraw.Draw(img)
    if day_n and day_hits * 2 >= day_n:   # удачный день — показываем счёт
        _center(d, 360, "ВЧЕРА БОТ", 70, MUTED)
        _center(d, 560, f"{day_hits} из {day_n}", 220, GOLD)
        _center(d, 760, "прогнозов зашло", 64)
    else:                                  # неудачный — без цифр дня, про честность
        _center(d, 420, "ЧЕСТНАЯ", 120, GOLD)
        _center(d, 560, "СТАТИСТИКА", 120, GOLD)
        _center(d, 760, "каждый прогноз учтён", 64)
    _center(d, 1020, "Бесплатные прогнозы", 76)
    _center(d, 1110, "каждый день", 76)
    _pill(img, 1300, "@aistavvit", GOLD, size=86)
    _center(d, 1560, "прогнозы и матчи онлайн — на сайте", 44, MUTED, "Bold")
    _center(d, 1630, "horoooos.github.io/betbot", 46, WHITE)
    _center(d, 1800, "18+ · прогноз — не гарантия", 34, MUTED, "Bold")
    return img


def render(scenes: list[Image.Image]) -> bytes | None:
    """Сцены → MP4 (H.264, 30 к/с): лёгкое приближение каждой сцены и плавные переходы между ними."""
    from .video import _ffmpeg
    exe = _ffmpeg()
    if not exe:
        return None
    total = SCENE * len(scenes) - FADE * (len(scenes) - 1)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        args, parts = [], []
        frames = int(SCENE * FPS)
        for i, sc in enumerate(scenes):
            sc.save(t / f"s{i}.png")
            args += ["-loop", "1", "-framerate", str(FPS), "-t", str(SCENE), "-i", str(t / f"s{i}.png")]
            parts.append(f"[{i}:v]scale={VW * 2}:{VH * 2},zoompan=z='1+0.05*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                         f":d={frames}:s={VW}x{VH}:fps={FPS},setsar=1[z{i}]")
        chain, last = "", "z0"
        for i in range(1, len(scenes)):
            off = SCENE * i - FADE * i
            chain += f";[{last}][z{i}]xfade=transition=slideup:duration={FADE}:offset={off:.2f}[x{i}]"
            last = f"x{i}"
        flt = ";".join(parts) + chain + f";[{last}]fade=t=in:st=0:d=0.4,format=yuv420p[v]"
        n = len(scenes)
        cmd = [exe, "-y", "-loglevel", "error", *args, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-filter_complex", flt, "-map", "[v]", "-map", f"{n}:a", "-t", f"{total:.2f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(t / "out.mp4")]
        try:
            subprocess.run(cmd, check=True, timeout=300, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"  ! ролик не собрался: {e.stderr.decode(errors='ignore')[-300:]}")
            return None
        data = (t / "out.mp4").read_bytes()
        return data if len(data) > 30000 else None


def _logos(m: dict) -> dict:
    """Логотипы и турнир матча из памяти бота (matches.json / other.json)."""
    for path in (ROOT / "data" / "matches.json", ROOT / "data" / "other.json"):
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in store.values():
            if str(v.get("id")) == str(m["id"]):
                lg = lambda t: (t.get("logo") or [None, None])[1] if isinstance(t.get("logo"), list) else t.get("logo")  # noqa: E731
                return {"hl": lg(v.get("home", {})), "al": lg(v.get("away", {}))}
    return {}


def best_of_day(res: pd.DataFrame, day: pd.Timestamp) -> tuple[dict | None, int, int]:
    """Лучший заход дня (самый высокий кэф) и счёт дня «зашло из»."""
    r = res[pd.to_datetime(res["date"]).dt.normalize() == day.normalize()]
    r = r[pd.to_numeric(r["main_odds"], errors="coerce") > 1]
    hit = r["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"])
    if not len(r) or not hit.any():
        return None, int(hit.sum()), len(r)
    b = r[hit].sort_values("main_odds", ascending=False).iloc[0]
    from .live import _league
    sport = b["sport"] if isinstance(b.get("sport"), str) else "football"
    try:
        league = _league({"div": str(b["div"]), "sport": sport})
    except Exception:
        league = ""
    m = {"id": str(b["id"]), "sport": sport, "home": str(b["home"]), "away": str(b["away"]), "score": str(b["score"]),
         "tip": str(b["main_label"]), "odds": float(b["main_odds"]), "p": float(b["main_p"]) if pd.notna(b.get("main_p")) else None,
         "league": league}
    m.update(_logos(m))
    return m, int(hit.sum()), len(r)


def clip_best(res: pd.DataFrame, day: pd.Timestamp) -> tuple[bytes | None, dict | None]:
    m, w, n = best_of_day(res, day)
    if not m:
        return None, None
    return render([_scene_pick(m), _scene_result(m), _scene_cta(w, n)]), m


def clip_express(ex: dict, w: int, n: int) -> bytes | None:
    return render([_scene_express(ex), _scene_cta(w, n)])


def _vk_video(mp4: bytes, name: str, desc: str) -> str | None:
    """Ролик на стену сообщества ВК (нужен личный ключ с правом video)."""
    from . import vk
    import os
    if not os.environ.get("VK_USER_TOKEN"):
        return "нет VK_USER_TOKEN"
    try:
        r = vk._call("video.save", group_id=vk.GROUP_ID, name=name[:120], description=desc[:4000], wallpost=1, is_private=0)
        up = requests.post(r["upload_url"], files={"video_file": ("clip.mp4", mp4, "video/mp4")}, timeout=180)
        return None if up.ok else f"загрузка: {up.status_code} {up.text[:120]}"
    except Exception as e:
        return str(e)[:200]


SITE = "https://horoooos.github.io/betbot/"
SPORT_TAG = {"football": "футбол", "hockey": "хоккей", "basketball": "баскетбол", "tennis": "теннис", "esports": "киберспорт"}
SPORT_EN = {"football": "football", "hockey": "hockey", "basketball": "basketball", "tennis": "tennis", "esports": "esports"}


def _tag(words: str) -> str:
    """«Нью-Йорк Никс» → #НьюЙоркНикс."""
    import re
    parts = re.findall(r"[\wА-Яа-яЁё]+", words)
    return "#" + "".join(p[:1].upper() + p[1:] for p in parts) if parts else ""


def texts(kind: str, m: dict | None = None, ex: dict | None = None) -> dict:
    """Уникальные тексты под каждую платформу: Telegram, ВК, YouTube Shorts и Дзен (заголовок, описание, хештеги/теги)."""
    if kind == "best":
        h, a, tip, odds, score, sport = m["home"], m["away"], m["tip"], m["odds"], m["score"], m["sport"]
        league = (m.get("league") or "").split(" · ")[-1]
        teams = [_tag(h), _tag(a)]
        lg = [_tag(league)] if league else []
        sp = SPORT_TAG.get(sport, "спорт")
        tg = (f"🎬 <b>Заход дня</b>: {h} — {a}\n🎯 {tip} · кэф {odds:.2f} → итог {score} ✅\n\n"
              f"Бесплатные прогнозы каждый день — @aistavvit · <a href=\"{SITE}\">сайт</a>\n\n"
              + " ".join(["#заходдня", f"#{sp}"] + teams[:2]))
        vk_name = f"{h} — {a}: {tip} зашёл ✅ кэф {odds:.2f}"
        vk_desc = (f"Прогноз бота АИ СТАВИТ на матч {h} — {a}: {tip} по кэфу {odds:.2f}. Итог {score} — ЗАШЛО ✅\n\n"
                   f"Бесплатные прогнозы на {sp} и другие виды спорта каждый день, честная статистика — все прогнозы учтены.\n"
                   f"Telegram: https://t.me/aistavvit\nСайт: {SITE}\n\n"
                   + " ".join(["#заходдня", "#прогнозынаспорт", "#ставкинаспорт", f"#{sp}", f"#прогноз{sp}", "#клипы", "#спорт"] + teams + lg))
        yt_title = f"{h} — {a}: прогноз {tip} зашёл ✅ #shorts"
        yt_desc = (f"Бот АИ СТАВИТ дал прогноз {tip} (кэф {odds:.2f}) на матч {h} — {a}. Итог: {score} — прогноз зашёл!\n\n"
                   f"📲 Бесплатные прогнозы каждый день: https://t.me/aistavvit\n🌐 Статистика и матчи онлайн: {SITE}\n\n"
                   f"18+. Прогноз — не гарантия.\n\n" + " ".join(["#shorts", "#прогнозынаспорт", f"#{sp}"] + teams))
        yt_tags = [f"прогноз {h} {a}", f"{h} {a}", h, a, f"прогноз на {sp}", "прогнозы на спорт", "ставки на спорт",
                   "заход дня", SPORT_EN.get(sport, "sport"), "betting tips", league or sp, "АИ СТАВИТ"]
        dz_title = f"{h} — {a}: бот поставил {tip} и не ошибся"
        dz_desc = (f"Прогноз {tip} по кэфу {odds:.2f}, итог {score}. Как бот выбирает ставки и почему вся статистика открыта — "
                   f"в Telegram @aistavvit и на сайте {SITE}")
        dz_tags = ["прогнозы на спорт", "ставки", sp, h, a] + ([league] if league else [])
    else:
        title = ex.get("title", "Экспресс")
        legs = ex.get("legs", [])
        teams = [_tag(g["home"]) for g in legs[:3]]
        lines = "\n".join(f"✅ {g['home']} — {g['away']}: {g['label']} · {g['odds']:.2f}" for g in legs)
        tg = (f"🎬 <b>{title} зашёл!</b> Общий кэф {ex['odds']:.2f} ✅\n\n{lines}\n\n"
              f"Бесплатно каждый день — @aistavvit\n\n#экспресс #заходдня #ставкинаспорт")
        vk_name = f"{title} зашёл ✅ общий кэф {ex['odds']:.2f}"
        vk_desc = (f"{title} от бота АИ СТАВИТ зашёл целиком — общий кэф {ex['odds']:.2f}.\n\n{lines}\n\n"
                   f"Telegram: https://t.me/aistavvit\nСайт: {SITE}\n\n"
                   + " ".join(["#экспресс", "#экспрессдня", "#прогнозынаспорт", "#ставкинаспорт", "#клипы", "#спорт"] + teams))
        yt_title = f"{title} зашёл ✅ кэф {ex['odds']:.2f} #shorts"
        yt_desc = (f"{title} от бота АИ СТАВИТ — все события зашли, общий кэф {ex['odds']:.2f}.\n\n{lines}\n\n"
                   f"📲 https://t.me/aistavvit\n🌐 {SITE}\n\n18+. Прогноз — не гарантия.\n\n#shorts #экспресс #прогнозынаспорт")
        yt_tags = ["экспресс дня", "экспресс на сегодня", "прогнозы на спорт", "ставки на спорт", "АИ СТАВИТ"] + [g["home"] for g in legs[:4]]
        dz_title = f"{title} зашёл: общий кэф {ex['odds']:.2f}"
        dz_desc = f"Все события экспресса зашли. Разбор и новые экспрессы — в Telegram @aistavvit и на сайте {SITE}"
        dz_tags = ["экспресс", "ставки", "прогнозы на спорт"]
    tags_len, yt_ok = 0, []
    for t in yt_tags:   # у YouTube лимит на теги — 500 символов
        if t and tags_len + len(t) + 2 <= 480:
            yt_ok.append(t[:100])
            tags_len += len(t) + 2
    return {"tg": tg, "vk_name": vk_name[:128], "vk_desc": vk_desc[:5000], "yt_title": yt_title[:100], "yt_desc": yt_desc[:4900],
            "yt_tags": yt_ok, "dz_title": dz_title[:120], "dz_desc": dz_desc, "dz_tags": dz_tags}


def _youtube(mp4: bytes, t: dict) -> str | None:
    """Загрузка в YouTube Shorts (бесплатный YouTube Data API). Нужны секреты YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN."""
    import os
    cid, sec, ref = os.environ.get("YT_CLIENT_ID"), os.environ.get("YT_CLIENT_SECRET"), os.environ.get("YT_REFRESH_TOKEN")
    if not (cid and sec and ref):
        return "YouTube не подключён (нет секретов YT_*)"
    try:
        tok = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": cid, "client_secret": sec, "refresh_token": ref, "grant_type": "refresh_token"}).json()
        if "access_token" not in tok:
            return f"YouTube: ключ не обновился: {str(tok)[:150]}"
        auth = {"Authorization": f"Bearer {tok['access_token']}"}
        meta = {"snippet": {"title": t["yt_title"], "description": t["yt_desc"], "tags": t["yt_tags"], "categoryId": "17",
                            "defaultLanguage": "ru", "defaultAudioLanguage": "ru"},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
        r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                          headers={**auth, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4",
                                   "X-Upload-Content-Length": str(len(mp4))}, data=json.dumps(meta), timeout=60)
        if r.status_code != 200 or "Location" not in r.headers:
            return f"YouTube: {r.status_code} {r.text[:150]}"
        up = requests.put(r.headers["Location"], headers={**auth, "Content-Type": "video/mp4"}, data=mp4, timeout=300)
        if up.status_code not in (200, 201):
            return f"YouTube загрузка: {up.status_code} {up.text[:150]}"
        print(f"  YouTube Shorts: https://youtube.com/shorts/{up.json().get('id')}")
        return None
    except Exception as e:
        return f"YouTube: {e}"[:200]


def _dzen(state: dict, mp4: bytes, t: dict) -> None:
    """Дзен не даёт загружать видео программно — шлём ролик и готовый текст владельцу в личку (он сделал /dzen у бота)."""
    from . import telegram
    chat = state.get("dzen_chat")
    if not chat:
        return
    cap = (f"📤 <b>Для Дзена</b> (скачай ролик → Дзен-Студия → «Ролик»)\n\n<b>Заголовок:</b>\n{t['dz_title']}\n\n"
           f"<b>Описание:</b>\n{t['dz_desc']}\n\n<b>Теги:</b>\n{', '.join(t['dz_tags'])}")
    try:
        telegram._call("sendVideo", chat_id=chat, files={"video": ("clip.mp4", mp4, "video/mp4")}, caption=cap[:1024],
                       parse_mode="HTML", width=VW, height=VH, supports_streaming=True)
    except Exception as e:
        print(f"  ! ролик для Дзена не отправлен: {e}")


def run(state: dict, now: pd.Timestamp, res: pd.DataFrame, brand: str = "@aistavvit") -> None:
    """Раз в день (12:00–13:00 МСК): ролик «лучший заход вчера» (+ «экспресс зашёл», если был) →
    Telegram, ВК, YouTube Shorts (если подключён) и владельцу в личку для Дзена — у каждой платформы свой текст и теги."""
    from . import telegram
    now = now.tz_convert("Europe/Moscow")
    day = f"{now:%Y-%m-%d}"
    if now.hour != 12 or state.get("shorts_day") == day or res is None or not len(res):
        return
    state["shorts_day"] = day
    yday = now.tz_localize(None).normalize() - pd.Timedelta(days=1)
    clips = []
    mp4, m = clip_best(res, yday)
    if mp4:
        clips.append((mp4, texts("best", m=m)))
    try:
        exs = json.loads((ROOT / "docs" / "express.json").read_text(encoding="utf-8"))
        _, w, n = best_of_day(res, yday)
        for ex in exs:
            if ex.get("status") == "won" and ex.get("day") == f"{yday:%Y-%m-%d}":
                mp = clip_express(ex, w, n)
                if mp:
                    clips.append((mp, texts("express", ex=ex)))
    except (OSError, ValueError, KeyError):
        pass
    errs = {}
    for mp4, t in clips:
        try:
            telegram.send_video(mp4, t["tg"], width=VW, height=VH, duration=int(SCENE * 3 - FADE * 2))
        except Exception as e:
            print(f"  ! ролик в Telegram не отправлен: {e}")
        errs["vk"] = _vk_video(mp4, t["vk_name"], t["vk_desc"])
        errs["youtube"] = _youtube(mp4, t)
        _dzen(state, mp4, t)
    state["shorts_err"] = {k: v for k, v in errs.items() if v} or None
    if clips:
        print(f"  🎬 ролики: {len(clips)}")
