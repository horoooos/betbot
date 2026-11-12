"""РљСЂРѕСЃСЃРїРѕСЃС‚РёРЅРі РёР· Telegram-РєР°РЅР°Р»Р° РІ СЃРѕРѕР±С‰РµСЃС‚РІРѕ Р’РљРѕРЅС‚Р°РєС‚Рµ (vk.com/aistavvit).

Р‘РµСЂС‘Рј РЅРѕРІС‹Рµ РїРѕСЃС‚С‹ РєР°РЅР°Р»Р° (data/channel.json, РµРіРѕ РѕР±РЅРѕРІР»СЏРµС‚ pages.sync_channel) Рё РїСѓР±Р»РёРєСѓРµРј РЅР° СЃС‚РµРЅРµ
СЃРѕРѕР±С‰РµСЃС‚РІР° РѕС‚ РёРјРµРЅРё СЃРѕРѕР±С‰РµСЃС‚РІР°: С‚РµРєСЃС‚ + РєР°СЂС‚РёРЅРєР° РїРѕСЃС‚Р°. РЎС‚Р°РІРєРё/Р±СѓРєРјРµРєРµСЂС‹ Рё СЂРµС„РµСЂР°Р»СЊРЅС‹Рµ СЃСЃС‹Р»РєРё
РІС‹СЂРµР·Р°РµРј вЂ” Р’Рљ СЃС‚СЂРѕРіРѕ РѕС‚РЅРѕСЃРёС‚СЃСЏ Рє СЂРµРєР»Р°РјРµ СЃС‚Р°РІРѕРє. РЎСЃС‹Р»РєР° РІРµРґС‘С‚ РЅР° РЅР°С€ СЃР°Р№С‚.

РЎС‚РµРЅР° Р’Рљ РЅРµРґРѕСЃС‚СѓРїРЅР° РїРѕ РєР»СЋС‡Сѓ СЃРѕРѕР±С‰РµСЃС‚РІР° вЂ” РЅСѓР¶РµРЅ Р»РёС‡РЅС‹Р№ РєР»СЋС‡ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР° (СЃРµРєСЂРµС‚ VK_USER_TOKEN,
РїСЂР°РІР° wall, photos, offline). Р‘РµР· РЅРµРіРѕ СЂР°Р±РѕС‚Р°РµС‚ РєР»СЋС‡ СЃРѕРѕР±С‰РµСЃС‚РІР° VK_TOKEN: С‚РµРєСЃС‚ + РєР°СЂС‚РѕС‡РєР° СЃСЃС‹Р»РєРё РЅР° СЃР°Р№С‚.
"""
from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from pathlib import Path

import requests

GROUP_ID = 228963529           # vk.com/aistavvit
API = "https://api.vk.com/method/"
V = "5.199"
CHANNEL = Path(__file__).resolve().parent.parent / "data" / "channel.json"
SITE = "https://horoooos.github.io/betbot/"
MAX_PER_PASS = 1               # Р·Р° РїСЂРѕС…РѕРґ вЂ” РѕРґРёРЅ РїРѕСЃС‚: Р’Рљ Р±Р°РЅРёС‚ СЃС‚РµРЅСѓ Р·Р° РїР°С‡РєРё (РѕС€РёР±РєР° 9 Flood control)
MIN_GAP_S = 300                # Рё РЅРµ С‡Р°С‰Рµ РѕРґРЅРѕРіРѕ РїРѕСЃС‚Р° Р·Р° 5 РјРёРЅСѓС‚
HOUR_LIMIT = 4                 # Р±РѕР»СЊС€Рµ 4 РїРѕСЃС‚РѕРІ РІ С‡Р°СЃ РЅР° СЃС‚РµРЅСѓ РЅРµ РїСѓР±Р»РёРєСѓРµРј
TRIES_LIMIT = 3                # РїРѕСЃР»Рµ С‚СЂС‘С… РЅРµСѓРґР°С‡ РїРѕСЃС‚ РїСЂРѕРїСѓСЃРєР°РµРј, С‡С‚РѕР±С‹ РѕС‡РµСЂРµРґСЊ РЅРµ РІСЃС‚Р°РІР°Р»Р° РЅР°РІСЃРµРіРґР°
PAUSE_S = 30 * 60              # РїРѕСЃР»Рµ В«Flood controlВ» РјРѕР»С‡РёРј 45 РјРёРЅСѓС‚ вЂ” РёРЅР°С‡Рµ Р’Рљ Р±Р»РѕРєРёСЂСѓРµС‚ СЃС‚РµРЅСѓ РЅР°РґРѕР»РіРѕ
STOP = re.compile(r"betboom|Р±РµС‚Р±СѓРј|Р±СѓРєРјРµРєРµСЂ|РїСЂРѕРјРѕРєРѕРґ|С„СЂРёР±РµС‚|СЂРµС„РµСЂР°Р»", re.I)


def _token() -> str:
    """Р›РёС‡РЅС‹Р№ РєР»СЋС‡ Р°РґРјРёРЅР° (РјРѕР¶РµС‚ РіСЂСѓР·РёС‚СЊ С„РѕС‚Рѕ) РёР»Рё РєР»СЋС‡ СЃРѕРѕР±С‰РµСЃС‚РІР° (VK_TOKEN: РїСѓР±Р»РёРєСѓРµС‚ С‚РµРєСЃС‚ СЃРѕ СЃСЃС‹Р»РєРѕР№)."""
    return os.environ.get("VK_USER_TOKEN") or os.environ.get("VK_TOKEN") or ""


def enabled() -> bool:
    return bool(_token())


def _call(method: str, _tok: str | None = None, **params) -> dict:
    params.update(access_token=_tok or _token(), v=V)
    resp = requests.post(API + method, data=params, timeout=30)
    try:
        r = resp.json()
    except ValueError:
        raise RuntimeError(f"VK {method}: РѕС‚РІРµС‚ РЅРµ JSON ({resp.status_code}): {resp.text[:120]!r}") from None
    if "error" in r:
        raise RuntimeError(f"VK {method}: {r['error'].get('error_code')} {r['error'].get('error_msg')}")
    return r["response"]


def _text(html: str) -> str:
    """HTML РїРѕСЃС‚Р° Telegram в†’ РѕР±С‹С‡РЅС‹Р№ С‚РµРєСЃС‚ РґР»СЏ Р’Рљ, Р±РµР· СЃС‚СЂРѕРє РїСЂРѕ Р±СѓРєРјРµРєРµСЂРѕРІ Рё СЃС‚Р°РІРєРё РЅР° РґРµРЅСЊРіРё."""
    t = re.sub(r"<br\s*/?>", "\n", html or "")
    t = re.sub(r"<a [^>]*>(#[^<]+)</a>", r"\1", t)          # С…РµС€С‚РµРіРё РѕСЃС‚Р°РІР»СЏРµРј С‚РµРєСЃС‚РѕРј
    t = re.sub(r"<[^>]+>", "", t)
    t = unescape(t)
    lines = [ln for ln in t.split("\n") if not STOP.search(ln)]
    t = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def _photo(img: bytes) -> str | None:
    """Р—Р°РіСЂСѓР¶Р°РµРј РєР°СЂС‚РёРЅРєСѓ Рё РІРѕР·РІСЂР°С‰Р°РµРј РІР»РѕР¶РµРЅРёРµ РґР»СЏ РїРѕСЃС‚Р°.

    Р›РёС‡РЅС‹Р№ РєР»СЋС‡ вЂ” РєР°Рє С„РѕС‚Рѕ СЃС‚РµРЅС‹. РљР»СЋС‡ СЃРѕРѕР±С‰РµСЃС‚РІР° С„РѕС‚Рѕ СЃС‚РµРЅС‹ РіСЂСѓР·РёС‚СЊ РЅРµ СѓРјРµРµС‚, РїРѕСЌС‚РѕРјСѓ РіСЂСѓР·РёРј РєР°Рє
    В«С„РѕС‚Рѕ РґР»СЏ СЃРѕРѕР±С‰РµРЅРёР№ СЃРѕРѕР±С‰РµСЃС‚РІР°В» Рё РїСЂРёРєСЂРµРїР»СЏРµРј Рє РїРѕСЃС‚Сѓ (РЅСѓР¶РЅС‹ РІРєР»СЋС‡С‘РЅРЅС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ СЃРѕРѕР±С‰РµСЃС‚РІР°).
    """
    import time
    s, errs = None, []
    for attempt in range(3 if os.environ.get("VK_USER_TOKEN") else 0):
        # РѕС‚РґРµР»СЊРЅС‹Рµ СЃРµСЂРІРµСЂС‹ Р·Р°РіСЂСѓР·РєРё Р’Рљ РёРЅРѕРіРґР° РѕС‚РІРµС‡Р°СЋС‚ В«405 Not AllowedВ» вЂ” РєР°Р¶РґС‹Р№ СЂР°Р· Р±РµСЂС‘Рј РЅРѕРІС‹Р№ СЃРµСЂРІРµСЂ
        try:
            up = _call("photos.getWallUploadServer", group_id=GROUP_ID)["upload_url"]
            r = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60)
            try:
                res = r.json()
            except ValueError:
                raise RuntimeError(f"СЃРµСЂРІРµСЂ Р·Р°РіСЂСѓР·РєРё РѕС‚РІРµС‚РёР» РЅРµ JSON ({r.status_code}): {r.text[:80]!r}") from None
            s = _call("photos.saveWallPhoto", group_id=GROUP_ID, photo=res["photo"], server=res["server"], hash=res["hash"])[0]
            break
        except Exception as e:   # РїРѕСЃР»Рµ 3 РЅРµСѓРґР°С‡ вЂ” РіСЂСѓР·РёРј С‡РµСЂРµР· СЃРѕРѕР±С‰РµРЅРёСЏ СЃРѕРѕР±С‰РµСЃС‚РІР°
            _photo.wall_err = f"РїРѕРїС‹С‚РєР° {attempt + 1}: {e}"[:250]
            print(f"  ! Р’Рљ: С„РѕС‚Рѕ СЃС‚РµРЅС‹ РЅРµ Р·Р°РіСЂСѓР·РёР»РѕСЃСЊ (РїРѕРїС‹С‚РєР° {attempt + 1}): {e}")
            time.sleep(3)
    if not s and getattr(_photo, "wall_err", ""):
        errs.append(f"СЃС‚РµРЅР°: {_photo.wall_err}")
    try:
        if not s:
            if not os.environ.get("VK_TOKEN"):
                raise RuntimeError("РЅРµС‚ VK_TOKEN РґР»СЏ Р·Р°РіСЂСѓР·РєРё С‡РµСЂРµР· СЃРѕРѕР±С‰РµРЅРёСЏ")
            last = ""
            for attempt in range(3):   # Р’Рљ РёРЅРѕРіРґР° РѕС‚РІРµС‡Р°РµС‚ РїСѓСЃС‚С‹Рј С„РѕС‚Рѕ РёР»Рё РЅРµ-JSON вЂ” РїСЂРѕР±СѓРµРј Р·Р°РЅРѕРІРѕ СЃ РЅРѕРІС‹Рј Р°РґСЂРµСЃРѕРј
                try:
                    up = _call("photos.getMessagesUploadServer", _tok=os.environ["VK_TOKEN"], peer_id=0)["upload_url"]
                    r = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60)
                    try:
                        res = r.json()
                    except ValueError:
                        raise RuntimeError(f"СЃРµСЂРІРµСЂ Р·Р°РіСЂСѓР·РєРё РѕС‚РІРµС‚РёР» РЅРµ JSON ({r.status_code}): {r.text[:80]!r}") from None
                    if not res.get("photo") or res.get("photo") == "[]":
                        raise RuntimeError(f"РїСѓСЃС‚РѕРµ С„РѕС‚Рѕ ({len(img)} Р±Р°Р№С‚): {str(res)[:100]}")
                    s = _call("photos.saveMessagesPhoto", _tok=os.environ["VK_TOKEN"], photo=res["photo"], server=res["server"], hash=res["hash"])[0]
                    break
                except Exception as e:
                    last = str(e)
                    time.sleep(3)
            if not s:
                raise RuntimeError(f"РїРѕСЃР»Рµ 3 РїРѕРїС‹С‚РѕРє: {last}")
        return f"photo{s['owner_id']}_{s['id']}" + (f"_{s['access_key']}" if s.get("access_key") else "")
    except Exception as e:
        errs.append(f"СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        print(f"  ! Р’Рљ: РєР°СЂС‚РёРЅРєР° РЅРµ Р·Р°РіСЂСѓР·РёР»Р°СЃСЊ: {e}")
        _photo.err = " | ".join(errs)[:300]
        return None


DOCS = Path(__file__).resolve().parent.parent / "docs"
DELAY_MIN = 9  # Р¶РґС‘Рј, РїРѕРєР° СЃС‚СЂР°РЅРёС†Р° РїРѕСЃС‚Р° РїРѕСЏРІРёС‚СЃСЏ РЅР° СЃР°Р№С‚Рµ вЂ” С‚РѕРіРґР° Р’Рљ РїРѕРєР°Р¶РµС‚ РєР°СЂС‚РѕС‡РєСѓ СЃСЃС‹Р»РєРё СЃ РєР°СЂС‚РёРЅРєРѕР№


def _site_link(pid: int) -> str:
    """РЎС‚СЂР°РЅРёС†Р° РїРѕСЃС‚Р° РЅР° РЅР°С€РµРј СЃР°Р№С‚Рµ: РЅРѕРІРѕСЃС‚СЊ РёР»Рё РїСЂРѕРіРЅРѕР· РЅР° РјР°С‚С‡; РёРЅР°С‡Рµ РіР»Р°РІРЅР°СЏ."""
    news = sorted((DOCS / "news").glob(f"{pid}-*.html"))
    if news:
        return SITE + "news/" + news[0].name
    needle = f"t.me/aistavvit/{pid}\""
    for f in sorted((DOCS / "predictions").glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)[:300]:
        if needle in f.read_text(encoding="utf-8", errors="ignore"):
            return SITE + "predictions/" + f.name
    return SITE


def _short(url: str) -> str:
    """РљРѕСЂРѕС‚РєР°СЏ СЃСЃС‹Р»РєР° Р’Рљ (vk.cc/вЂ¦); РЅРµ РІС‹С€Р»Рѕ вЂ” РёСЃС…РѕРґРЅР°СЏ."""
    try:
        return _call("utils.getShortLink", url=url)["short_url"].replace("https://", "")
    except Exception:
        return url.replace("https://", "")


def _live_link(text: str) -> str | None:
    """В«РњР°С‚С‡ РЅР°С‡Р°Р»СЃСЏВ»: СЃСЃС‹Р»РєР° РЅР° РЅР°С€Сѓ С‚СЂР°РЅСЃР»СЏС†РёСЋ СЌС‚РѕРіРѕ РјР°С‚С‡Р° (РёС‰РµРј РїР°СЂСѓ РєРѕРјР°РЅРґ РІ docs/matches.json)."""
    try:
        for m in json.loads((DOCS / "matches.json").read_text(encoding="utf-8")):
            if m.get("home") and m.get("away") and f"{m['home']} вЂ” {m['away']}" in text and m.get("url"):
                return SITE + m["url"]
    except (OSError, ValueError):
        pass
    return None


def _service(text: str) -> bool:
    """РЎР»СѓР¶РµР±РЅС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ РєР°РЅР°Р»Р° (В«вЂ¦ pinned a photoВ», В«Р·Р°РєСЂРµРїРёР» СЃРѕРѕР±С‰РµРЅРёРµВ») вЂ” РЅРµ РїРѕСЃС‚С‹."""
    return len(text) < 160 and bool(re.search(r"\bpinned\b|Р·Р°РєСЂРµРїРёР»", text, re.I))


def _stats_tail(pid: int, posts: dict) -> bool:
    """РўРµРєСЃС‚ СЃС‚Р°С‚РёСЃС‚РёРєРё (В«Р’С‡РµСЂР°, 9 РЅРѕСЏР±СЂСЏ: вЂ¦В»), РІС‹С€РµРґС€РёР№ РѕС‚РІРµС‚РѕРј СЃСЂР°Р·Сѓ РїРѕСЃР»Рµ РєР°СЂС‚РёРЅРєРё В«РЎРўРђРўРРЎРўРРљРђ Р‘РћРўРђВ»."""
    p = posts.get(str(pid)) or {}
    if not _text(p.get("html", "")).startswith("Р’С‡РµСЂР°,"):
        return False
    return any("РЎРўРђРўРРЎРўРРљРђ Р‘РћРўРђ" in (posts.get(str(j)) or {}).get("html", "") for j in range(pid - 1, pid - 4, -1))


def crosspost(state: dict) -> int:
    """РџСѓР±Р»РёРєСѓРµС‚ РІ Р’Рљ РїРѕСЃС‚С‹ РєР°РЅР°Р»Р°, РІС‹С€РµРґС€РёРµ РїРѕСЃР»Рµ РїСЂРѕС€Р»РѕРіРѕ Р·Р°РїСѓСЃРєР°. Р’РѕР·РІСЂР°С‰Р°РµС‚, СЃРєРѕР»СЊРєРѕ РѕРїСѓР±Р»РёРєРѕРІР°РЅРѕ."""
    if not enabled() or not CHANNEL.exists():
        return 0
    posts = json.loads(CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    newest = max(int(k) for k in posts)
    if "vk_last" not in state:           # РїРµСЂРІС‹Р№ Р·Р°РїСѓСЃРє: СЃС‚Р°СЂРѕРµ РЅРµ РїРµСЂРµРЅРѕСЃРёРј, РЅР°С‡РёРЅР°РµРј СЃ РЅРѕРІС‹С… РїРѕСЃС‚РѕРІ
        state["vk_last"] = newest
        print(f"  Р’Рљ: РєСЂРѕСЃСЃРїРѕСЃС‚РёРЅРі РІРєР»СЋС‡С‘РЅ, РЅР°С‡РёРЅР°РµРј РїРѕСЃР»Рµ РїРѕСЃС‚Р° {newest}")
        return 0
    # С‚РѕСЂРјРѕР·Р°: РїРѕСЃР»Рµ Flood control Р’Рљ Р±Р»РѕРєРёСЂСѓРµС‚ СЃС‚РµРЅСѓ, РїРѕСЌС‚РѕРјСѓ РјРѕР»С‡РёРј Рё РїРѕСЃС‚РµРїРµРЅРЅРѕ РЅР°СЂР°С‰РёРІР°РµРј С‚РµРјРї
    now_ts = time.time()
    if now_ts < float(state.get("vk_pause_ts") or 0):
        return 0
    hour = time.strftime("%Y-%m-%d-%H", time.gmtime())
    lim = state.get("vk_hour") or {}
    if lim.get("h") != hour:
        lim = {"h": hour, "n": 0}
    if lim.get("n", 0) >= HOUR_LIMIT:
        return 0
    if now_ts - float(state.get("vk_at_ts") or 0) < MIN_GAP_S:
        return 0
    fresh = sorted(int(k) for k in posts if int(k) > state["vk_last"])[:MAX_PER_PASS]
    done = 0
    for pid in fresh:
        p = posts[str(pid)]
        text = _text(p.get("html", ""))
        started = "РњРђРўР§ РќРђР§РђР›РЎРЇ" in text
        if len(text) < 20 or ("#live" in p.get("html", "") and not started):   # РіРѕР»С‹ Рё РїСЂРѕС‡РёР№ live РІ Р’Рљ РЅРµ РґСѓР±Р»РёСЂСѓРµРј
            state["vk_last"] = pid
            continue
        if text.startswith("рџ“– РџСЂРѕРґРѕР»Р¶РµРЅРёРµ") or _service(text) or _stats_tail(pid, posts):
            # РїСЂРѕРґРѕР»Р¶РµРЅРёРµ РЅРѕРІРѕСЃС‚Рё Рё С‚РµРєСЃС‚ СЃС‚Р°С‚РёСЃС‚РёРєРё СѓР¶Рµ РІРѕС€Р»Рё РІ СЃРІРѕР№ РїРѕСЃС‚ (РЅРёР¶Рµ); В«pinned a photoВ» вЂ” СЃР»СѓР¶РµР±РЅРѕРµ
            state["vk_last"] = pid
            continue
        if "РЎРўРђРўРРЎРўРРљРђ Р‘РћРўРђ" in text:   # РєР°СЂС‚РёРЅРєР° СЃС‚Р°С‚РёСЃС‚РёРєРё + С‚РµРєСЃС‚ РѕС‚РІРµС‚РѕРј РІ Telegram в†’ РІ Р’Рљ РѕРґРЅРёРј РїРѕСЃС‚РѕРј
            for j in range(pid + 1, pid + 4):
                if _stats_tail(j, posts):
                    text = text.rstrip() + "\n\n" + _text(posts[str(j)].get("html", ""))
                    break
        if "РџСЂРѕРґРѕР»Р¶РµРЅРёРµ вЂ” РІ РѕС‚РІРµС‚Рµ" in text:   # РґР»РёРЅРЅР°СЏ РЅРѕРІРѕСЃС‚СЊ: РІ Р’Рљ вЂ” РѕРґРЅРёРј РїРѕСЃС‚РѕРј, РІРјРµСЃС‚Рµ СЃ РїСЂРѕРґРѕР»Р¶РµРЅРёРµРј
            text = "\n".join(ln for ln in text.split("\n") if "РџСЂРѕРґРѕР»Р¶РµРЅРёРµ вЂ” РІ РѕС‚РІРµС‚Рµ" not in ln)
            for j in range(pid + 1, pid + 4):
                cont = _text((posts.get(str(j)) or {}).get("html", ""))
                if cont.startswith("рџ“– РџСЂРѕРґРѕР»Р¶РµРЅРёРµ"):
                    body = "\n".join(ln for ln in cont.split("\n")[1:] if not ln.strip().startswith("#")).strip()
                    lines = text.rstrip().split("\n")
                    tags = lines.pop() if lines and lines[-1].strip().startswith("#") else ""
                    text = "\n".join(lines).rstrip() + "\n\n" + body + ("\n\n" + tags if tags else "")
                    text = re.sub(r"\n{3,}", "\n\n", text)
                    break
        import pandas as pd
        link = _live_link(text) if started else None
        if started:
            text = "\n".join(ln for ln in text.split("\n") if ln.strip() != "#live")
        if not link:
            if pd.Timestamp.now(tz="UTC") - pd.Timestamp(p["t"]) < pd.Timedelta(minutes=DELAY_MIN):
                break                     # РїРѕСЃС‚ СЃРѕРІСЃРµРј СЃРІРµР¶РёР№ вЂ” СЃС‚СЂР°РЅРёС†Р° РЅР° СЃР°Р№С‚Рµ РµС‰С‘ РїСѓР±Р»РёРєСѓРµС‚СЃСЏ, РІРµСЂРЅС‘РјСЃСЏ РїРѕР·Р¶Рµ
            link = _site_link(pid)
        short = _short(link)   # РІРЅРµС€РЅРёРµ СЃСЃС‹Р»РєРё Р’Рљ РЅРµ РїСЂСЏС‡РµС‚ РїРѕРґ СЃР»РѕРІРѕ вЂ” РґРµР»Р°РµРј РєРѕСЂРѕС‚РєСѓСЋ vk.cc/вЂ¦
        text += "\n\n" + (f"рџ“є РЎРјРѕС‚СЂРµС‚СЊ РјР°С‚С‡ РѕРЅР»Р°Р№РЅ рџ‘‰ {short}" if started else f"рџ“Љ РџРѕРґСЂРѕР±РЅРµРµ РЅР° СЃР°Р№С‚Рµ рџ‘‰ {short}")
        # СЃ Р»РёС‡РЅС‹Рј РєР»СЋС‡РѕРј вЂ” С„РѕС‚Рѕ РїРѕСЃС‚Р°; СЃ РєР»СЋС‡РѕРј СЃРѕРѕР±С‰РµСЃС‚РІР° вЂ” С‚РµРєСЃС‚ СЃРѕ СЃСЃС‹Р»РєРѕР№ РЅР° РЅР°С€ СЃР°Р№С‚
        from . import dzen, postimg
        tags = dzen.hashtags(p.get("html", ""), "РЅР°С‡Р°Р»Рѕ" if started else dzen.kind(p.get("html", "")), limit=8)
        if tags:   # С…РµС€С‚РµРіРё РїРѕ С‚РµРјРµ (РєРѕРјР°РЅРґС‹, РёРіСЂРѕРєРё, Р»РёРіР°) вЂ” Р’Рљ Р»СѓС‡С€Рµ РїРѕРєР°Р·С‹РІР°РµС‚ РїРѕСЃС‚ РІ РїРѕРёСЃРєРµ Рё СЂРµРєРѕРјРµРЅРґР°С†РёСЏС…
            text += "\n\n" + tags
        img = postimg.image_for(p, ("РЅР°С‡Р°Р»Рѕ" if started else dzen.kind(p.get("html", "")) or "РЅРѕРІРѕСЃС‚СЊ"), posts)
        _photo.err = "" if img else "РєР°СЂС‚РёРЅРєР° РїРѕСЃС‚Р° РЅРµ РїРѕР»СѓС‡РµРЅР°"
        _photo.wall_err = ""
        photo = _photo(img) if img else None
        state["vk_err"] = f"{pid} С„РѕС‚Рѕ: {_photo.err}" if not photo else None   # СЃС‚Р°СЂСѓСЋ РѕС€РёР±РєСѓ СЃС‚РёСЂР°РµРј
        state["vk_wall_err"] = f"{pid}: {_photo.wall_err}" if _photo.wall_err else None   # РїРѕС‡РµРјСѓ РЅРµ РІС‹С€Р»Рѕ С„РѕС‚Рѕ СЃС‚РµРЅС‹ РїРѕ Р»РёС‡РЅРѕРјСѓ РєР»СЋС‡Сѓ
        # С„РѕС‚Рѕ В«РёР· СЃРѕРѕР±С‰РµРЅРёР№В» СЃРѕРѕР±С‰РµСЃС‚РІР° Р’Рљ РЅР° СЃС‚РµРЅРµ РѕРґРёРЅ РЅРµ РїРѕРєР°Р·С‹РІР°РµС‚ вЂ” РїСЂРѕР±СѓРµРј РІРјРµСЃС‚Рµ СЃ РєР°СЂС‚РѕС‡РєРѕР№ СЃСЃС‹Р»РєРё
        # (РЅР°С€Рµ С„РѕС‚Рѕ РєР°Рє РѕР±Р»РѕР¶РєР° СЃСЃС‹Р»РєРё); РЅРµ РїСЂРёРЅСЏР» вЂ” РїСѓР±Р»РёРєСѓРµРј РєР°Рє СЂР°РЅСЊС€Рµ, С‚РµРєСЃС‚ СЃРѕ СЃСЃС‹Р»РєРѕР№
        if photo and photo.startswith("photo-"):   # С„РѕС‚Рѕ В«РёР· СЃРѕРѕР±С‰РµРЅРёР№В» СЃРѕРѕР±С‰РµСЃС‚РІР° вЂ” С‚РѕР»СЊРєРѕ РІРјРµСЃС‚Рµ СЃРѕ СЃСЃС‹Р»РєРѕР№
            tries = [[photo, link], [photo]] if link != SITE else [[photo]]
        else:                                      # С„РѕС‚Рѕ СЃС‚РµРЅС‹ (Р»РёС‡РЅС‹Р№ РєР»СЋС‡) Р’Рљ РїРѕРєР°Р·С‹РІР°РµС‚ РєР°Рє РѕР±С‹С‡РЅСѓСЋ РєР°СЂС‚РёРЅРєСѓ
            tries = [[photo] if photo else []]
        try:
            for i, att in enumerate(tries):
                try:
                    _call("wall.post", owner_id=-GROUP_ID, from_group=1, message=text[:15000], attachments=",".join(att))
                    state["vk_mode"] = "+".join(a[:5] for a in att) or "С‚РµРєСЃС‚"
                    break
                except RuntimeError as e:
                    if i == len(tries) - 1:
                        raise
                    state["vk_err"] = f"{pid} С„РѕС‚Рѕ+СЃСЃС‹Р»РєР°: {e}"[:300]
            state["vk_last"] = pid
            state["vk_at_ts"] = time.time()
            lim["n"] = lim.get("n", 0) + 1
            state["vk_hour"] = lim
            (state.get("vk_try") or {}).pop(str(pid), None)
            state["vk_err"] = None
            done += 1
        except Exception as e:
            msg = str(e)
            print(f"  ! Р’Рљ: РїРѕСЃС‚ {pid} РЅРµ РѕРїСѓР±Р»РёРєРѕРІР°РЅ: {msg}")
            state["vk_err"] = f"{pid}: {msg}"[:300]   # РІРёРґРЅРѕ РІ data/state.json Р±РµР· Р¶СѓСЂРЅР°Р»Р° GitHub
            tries = state.setdefault("vk_try", {})
            tries[str(pid)] = tries.get(str(pid), 0) + 1
            if "flood" in msg.lower() or ": 9" in msg:
                # Р’Рљ РѕРіСЂР°РЅРёС‡РёР» С‡Р°СЃС‚РѕС‚Сѓ: СЃС‚Р°СЂС‹Р№ Р±СЌРєР»РѕРі РЅРµ РґРѕР»Р±РёРј вЂ” РЅР°С‡РёРЅР°РµРј СЃРѕ СЃРІРµР¶РёС… РїРѕСЃС‚РѕРІ,
                # РёРЅР°С‡Рµ Р±РѕС‚ С‚СЂР°С‚РёС‚ С‡Р°СЃС‹ РЅР° РїРѕСЃС‚С‹, РєРѕС‚РѕСЂС‹Рµ СѓР¶Рµ РЅРµР°РєС‚СѓР°Р»СЊРЅС‹
                newest_now = max(int(k) for k in posts)
                state["vk_last"] = max(pid, newest_now - 2)
                tries.pop(str(pid), None)
                state["vk_pause_ts"] = time.time() + PAUSE_S
                print(f"  Р’Рљ: РїР°СѓР·Р° {PAUSE_S // 60} РјРёРЅСѓС‚ вЂ” Р’Рљ РѕРіСЂР°РЅРёС‡РёР» С‡Р°СЃС‚РѕС‚Сѓ; "
                      f"СЃС‚Р°СЂС‹Р№ Р±СЌРєР»РѕРі РїСЂРѕРїСѓС‰РµРЅ, РїСЂРѕРґРѕР»Р¶РёРј РїРѕСЃР»Рµ {state['vk_last']}")
                break
            if tries[str(pid)] >= TRIES_LIMIT:   # Р±РµР·РЅР°РґС‘Р¶РЅС‹Р№ РїРѕСЃС‚ РЅРµ РґРѕР»Р¶РµРЅ РґРµСЂР¶Р°С‚СЊ РѕС‡РµСЂРµРґСЊ
                state["vk_last"] = pid
                tries.pop(str(pid), None)
                print(f"  Р’Рљ: РїРѕСЃС‚ {pid} РїСЂРѕРїСѓС‰РµРЅ РїРѕСЃР»Рµ {TRIES_LIMIT} РЅРµСѓРґР°С‡")
                continue
            break                         # РІСЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР° вЂ” РїРѕРїСЂРѕР±СѓРµРј РІ СЃР»РµРґСѓСЋС‰РёР№ РїСЂРѕС…РѕРґ
    if done:
        print(f"  Р’Рљ: РѕРїСѓР±Р»РёРєРѕРІР°РЅРѕ РїРѕСЃС‚РѕРІ: {done}")
    return done
