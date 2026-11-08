"""Кросспостинг из Telegram-канала в сообщество ВКонтакте (vk.com/aistavvit).

Берём новые посты канала (data/channel.json, его обновляет pages.sync_channel) и публикуем на стене
сообщества от имени сообщества: текст + картинка поста. Ставки/букмекеры и реферальные ссылки
вырезаем — ВК строго относится к рекламе ставок. Ссылка ведёт на наш сайт.

Стена ВК недоступна по ключу сообщества — нужен личный ключ администратора (секрет VK_USER_TOKEN,
права wall, photos, offline). Без него модуль молчит.
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
MAX_PER_PASS = 3               # не заваливаем стену, если в канале выйдет пачка постов
STOP = re.compile(r"betboom|бетбум|букмекер|промокод|фрибет|реферал", re.I)


def enabled() -> bool:
    return bool(os.environ.get("VK_USER_TOKEN"))


def _call(method: str, **params) -> dict:
    params.update(access_token=os.environ["VK_USER_TOKEN"], v=V)
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


def _photo(url: str) -> str | None:
    """Загружаем картинку поста на стену сообщества, возвращаем вложение photo<owner>_<id>."""
    try:
        img = requests.get(url, timeout=30).content
        up = _call("photos.getWallUploadServer", group_id=GROUP_ID)["upload_url"]
        res = requests.post(up, files={"photo": ("post.jpg", img, "image/jpeg")}, timeout=60).json()
        saved = _call("photos.saveWallPhoto", group_id=GROUP_ID, photo=res["photo"], server=res["server"], hash=res["hash"])[0]
        return f"photo{saved['owner_id']}_{saved['id']}"
    except Exception as e:
        print(f"  ! ВК: картинка не загрузилась: {e}")
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
        if len(text) < 20 or "#live" in p.get("html", ""):   # пустые посты и live (голы, «матч начался») в ВК не дублируем
            state["vk_last"] = pid
            continue
        text += f"\n\n📊 Прогнозы, статистика и матчи онлайн: {SITE}"
        att = [a for a in [_photo(p["photo"]) if p.get("photo") else None] if a]
        try:
            _call("wall.post", owner_id=-GROUP_ID, from_group=1, message=text[:15000], attachments=",".join(att))
            state["vk_last"] = pid
            done += 1
        except Exception as e:
            print(f"  ! ВК: пост {pid} не опубликован: {e}")
            break                         # ошибка ключа/лимита — попробуем в следующий проход
    if done:
        print(f"  ВК: опубликовано постов: {done}")
    return done
