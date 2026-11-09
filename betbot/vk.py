"""Кросспостинг из Telegram-канала в сообщество ВКонтакте (vk.com/aistavvit).

Берём новые посты канала (data/channel.json, его обновляет pages.sync_channel) и публикуем на стене
сообщества от имени сообщества: текст + картинка поста. Ставки/букмекеры и реферальные ссылки
вырезаем — ВК строго относится к рекламе ставок. Ссылка ведёт на наш сайт.

Стена ВК недоступна по ключу сообщества — нужен личный ключ администратора (секрет VK_USER_TOKEN,
права wall, photos, offline). Без него работает ключ сообщества VK_TOKEN: текст + карточка ссылки на сайт.
"""
from __future__ import annotations

import json
import os
import re
from html import unescape
from pathlib import Path

import requests

GROUP_ID = 228963529           # vk.com/aistavvit
API = "https://api.vk.com/method/"
V = "5.199"
CHANNEL = Path(__file__).resolve().parent.parent / "data" / "channel.json"
SITE = "https://horoooos.github.io/betbot/"
MAX_PER_PASS = 5               # не заваливаем стену, если в канале выйдет пачка постов
STOP = re.compile(r"betboom|бетбум|букмекер|промокод|фрибет|реферал", re.I)


def _token() -> str:
    """Личный ключ админа (может грузить фото) или ключ сообщества (VK_TOKEN: публикует текст со ссылкой)."""
    return os.environ.get("VK_USER_TOKEN") or os.environ.get("VK_TOKEN") or ""


def enabled() -> bool:
    return bool(_token())


def _call(method: str, **params) -> dict:
    params.update(access_token=_token(), v=V)
    r = requests.post(API + method, data=params, timeout=30).json()
    if "error" in r:
        raise RuntimeError(f"VK {method}: {r['error'].get('error_code')} {r['error'].get('error_msg')}")
    return r["response"]


def _text(html: str) -> str:
    """HTML поста Telegram → обычный текст для ВК, без строк про букмекеров и ставки на деньги."""
    t = re.sub(r"<br\s*/?>", "\n", html or "")
    t = re.sub(r"<a [^>]*>(#[^<]+)</a>", r"\1", t)          # хештеги оставляем текстом
    t = re.sub(r"<[^>]+>", "", t)
    t = unescape(t)
    lines = [ln for ln in t.split("\n") if not STOP.search(ln)]
    t = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def _photo(img: bytes) -> str | None:
    """Загружаем картинку и возвращаем вложение для поста.

    Личный ключ — как фото стены. Ключ сообщества фото стены грузить не умеет, поэтому грузим как
    «фото для сообщений сообщества» и прикрепляем к посту (нужны включённые сообщения сообщества).
    """
    try:
        if os.environ.get("VK_USER_TOKEN"):
            up = _call("photos.getWallUploadServer", group_id=GROUP_ID)["upload_url"]
            res = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60).json()
            s = _call("photos.saveWallPhoto", group_id=GROUP_ID, photo=res["photo"], server=res["server"], hash=res["hash"])[0]
        else:
            res = {}
            for attempt in range(3):   # сервер загрузки ВК иногда возвращает пустое фото — пробуем заново с новым адресом
                up = _call("photos.getMessagesUploadServer", peer_id=0)["upload_url"]
                try:
                    res = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60).json()
                except ValueError:
                    res = {}
                if res.get("photo") and res.get("photo") != "[]":
                    break
                import time
                time.sleep(2)
            if not res.get("photo") or res.get("photo") == "[]":
                raise RuntimeError(f"ВК не принял файл после 3 попыток ({len(img)} байт): {str(res)[:120]}")
            s = _call("photos.saveMessagesPhoto", photo=res["photo"], server=res["server"], hash=res["hash"])[0]
        return f"photo{s['owner_id']}_{s['id']}" + (f"_{s['access_key']}" if s.get("access_key") else "")
    except Exception as e:
        print(f"  ! ВК: картинка не загрузилась: {e}")
        _photo.err = str(e)[:200]
        return None


DOCS = Path(__file__).resolve().parent.parent / "docs"
DELAY_MIN = 4   # ждём, пока страница поста появится на сайте — тогда ВК покажет карточку ссылки с картинкой


def _site_link(pid: int) -> str:
    """Страница поста на нашем сайте: новость или прогноз на матч; иначе главная."""
    news = sorted((DOCS / "news").glob(f"{pid}-*.html"))
    if news:
        return SITE + "news/" + news[0].name
    needle = f"t.me/aistavvit/{pid}\""
    for f in sorted((DOCS / "predictions").glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)[:300]:
        if needle in f.read_text(encoding="utf-8", errors="ignore"):
            return SITE + "predictions/" + f.name
    return SITE


def _short(url: str) -> str:
    """Короткая ссылка ВК (vk.cc/…); не вышло — исходная."""
    try:
        return _call("utils.getShortLink", url=url)["short_url"].replace("https://", "")
    except Exception:
        return url.replace("https://", "")


def _live_link(text: str) -> str | None:
    """«Матч начался»: ссылка на нашу трансляцию этого матча (ищем пару команд в docs/matches.json)."""
    try:
        for m in json.loads((DOCS / "matches.json").read_text(encoding="utf-8")):
            if m.get("home") and m.get("away") and f"{m['home']} — {m['away']}" in text and m.get("url"):
                return SITE + m["url"]
    except (OSError, ValueError):
        pass
    return None


def crosspost(state: dict) -> int:
    """Публикует в ВК посты канала, вышедшие после прошлого запуска. Возвращает, сколько опубликовано."""
    if not enabled() or not CHANNEL.exists():
        return 0
    posts = json.loads(CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    newest = max(int(k) for k in posts)
    if "vk_last" not in state:           # первый запуск: старое не переносим, начинаем с новых постов
        state["vk_last"] = newest
        print(f"  ВК: кросспостинг включён, начинаем после поста {newest}")
        return 0
    fresh = sorted(int(k) for k in posts if int(k) > state["vk_last"])[:MAX_PER_PASS]
    done = 0
    for pid in fresh:
        p = posts[str(pid)]
        text = _text(p.get("html", ""))
        started = "МАТЧ НАЧАЛСЯ" in text
        if len(text) < 20 or ("#live" in p.get("html", "") and not started):   # голы и прочий live в ВК не дублируем
            state["vk_last"] = pid
            continue
        import pandas as pd
        link = _live_link(text) if started else None
        if started:
            text = "\n".join(ln for ln in text.split("\n") if ln.strip() != "#live")
        if not link:
            if pd.Timestamp.now(tz="UTC") - pd.Timestamp(p["t"]) < pd.Timedelta(minutes=DELAY_MIN):
                break                     # пост совсем свежий — страница на сайте ещё публикуется, вернёмся позже
            link = _site_link(pid)
        short = _short(link)   # внешние ссылки ВК не прячет под слово — делаем короткую vk.cc/…
        text += "\n\n" + (f"📺 Смотреть матч онлайн 👉 {short}" if started else f"📊 Подробнее на сайте 👉 {short}")
        # с личным ключом — фото поста; с ключом сообщества — текст со ссылкой на наш сайт
        from . import dzen, postimg
        img = postimg.image_for(p, ("начало" if started else dzen.kind(p.get("html", "")) or "новость"), posts)
        photo = _photo(img) if img else None
        if not photo and getattr(_photo, "err", ""):
            state["vk_err"] = f"фото: {_photo.err}"
        att = [photo] if photo else []   # ссылка — в тексте: карточку ссылки ВК без подходящей картинки не принимает
        try:
            _call("wall.post", owner_id=-GROUP_ID, from_group=1, message=text[:15000], attachments=",".join(att))
            state["vk_last"] = pid
            done += 1
        except Exception as e:
            print(f"  ! ВК: пост {pid} не опубликован: {e}")
            state["vk_err"] = f"{pid}: {e}"[:300]   # видно в data/state.json без журнала GitHub
            break                         # ошибка ключа/лимита — попробуем в следующий проход
    if done:
        print(f"  ВК: опубликовано постов: {done}")
    return done
