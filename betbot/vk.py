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
import time
from html import unescape
from pathlib import Path

import requests

GROUP_ID = 228963529           # vk.com/aistavvit
API = "https://api.vk.com/method/"
V = "5.199"
CHANNEL = Path(__file__).resolve().parent.parent / "data" / "channel.json"
SITE = "https://horoooos.github.io/betbot/"
MAX_PER_PASS = 1               # за проход — один пост: ВК банит стену за пачки (ошибка 9 Flood control)
MIN_GAP_S = 300                # и не чаще одного поста за 5 минут
HOUR_LIMIT = 4                 # больше 4 постов в час на стену не публикуем
TRIES_LIMIT = 3                # после трёх неудач пост пропускаем, чтобы очередь не вставала навсегда
PAUSE_S = 30 * 60              # после «Flood control» молчим 30 минут — иначе ВК блокирует стену надолго
STOP = re.compile(r"betboom|бетбум|букмекер|промокод|фрибет|реферал", re.I)


def _token() -> str:
    """Личный ключ админа (может грузить фото) или ключ сообщества (VK_TOKEN: публикует текст со ссылкой)."""
    return os.environ.get("VK_USER_TOKEN") or os.environ.get("VK_TOKEN") or ""


def enabled() -> bool:
    return bool(_token())


def _call(method: str, _tok: str | None = None, **params) -> dict:
    params.update(access_token=_tok or _token(), v=V)
    resp = requests.post(API + method, data=params, timeout=30)
    try:
        r = resp.json()
    except ValueError:
        raise RuntimeError(f"VK {method}: ответ не JSON ({resp.status_code}): {resp.text[:120]!r}") from None
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
    import time
    s, errs = None, []
    for attempt in range(3 if os.environ.get("VK_USER_TOKEN") else 0):
        # отдельные серверы загрузки ВК иногда отвечают «405 Not Allowed» — каждый раз берём новый сервер
        try:
            up = _call("photos.getWallUploadServer", group_id=GROUP_ID)["upload_url"]
            r = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60)
            try:
                res = r.json()
            except ValueError:
                raise RuntimeError(f"сервер загрузки ответил не JSON ({r.status_code}): {r.text[:80]!r}") from None
            s = _call("photos.saveWallPhoto", group_id=GROUP_ID, photo=res["photo"], server=res["server"], hash=res["hash"])[0]
            break
        except Exception as e:   # после 3 неудач — грузим через сообщения сообщества
            _photo.wall_err = f"попытка {attempt + 1}: {e}"[:250]
            print(f"  ! ВК: фото стены не загрузилось (попытка {attempt + 1}): {e}")
            time.sleep(3)
    if not s and getattr(_photo, "wall_err", ""):
        errs.append(f"стена: {_photo.wall_err}")
    try:
        if not s:
            if not os.environ.get("VK_TOKEN"):
                raise RuntimeError("нет VK_TOKEN для загрузки через сообщения")
            last = ""
            for attempt in range(3):   # ВК иногда отвечает пустым фото или не-JSON — пробуем заново с новым адресом
                try:
                    up = _call("photos.getMessagesUploadServer", _tok=os.environ["VK_TOKEN"], peer_id=0)["upload_url"]
                    r = requests.post(up, files={"photo": (("post.png", img, "image/png") if img[1:4] == b"PNG" else ("post.jpg", img, "image/jpeg"))}, timeout=60)
                    try:
                        res = r.json()
                    except ValueError:
                        raise RuntimeError(f"сервер загрузки ответил не JSON ({r.status_code}): {r.text[:80]!r}") from None
                    if not res.get("photo") or res.get("photo") == "[]":
                        raise RuntimeError(f"пустое фото ({len(img)} байт): {str(res)[:100]}")
                    s = _call("photos.saveMessagesPhoto", _tok=os.environ["VK_TOKEN"], photo=res["photo"], server=res["server"], hash=res["hash"])[0]
                    break
                except Exception as e:
                    last = str(e)
                    time.sleep(3)
            if not s:
                raise RuntimeError(f"после 3 попыток: {last}")
        return f"photo{s['owner_id']}_{s['id']}" + (f"_{s['access_key']}" if s.get("access_key") else "")
    except Exception as e:
        errs.append(f"сообщения: {e}")
        print(f"  ! ВК: картинка не загрузилась: {e}")
        _photo.err = " | ".join(errs)[:300]
        return None


DOCS = Path(__file__).resolve().parent.parent / "docs"
DELAY_MIN = 9  # ждём, пока страница поста появится на сайте — тогда ВК покажет карточку ссылки с картинкой


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


def _service(text: str) -> bool:
    """Служебные сообщения канала («… pinned a photo», «закрепил сообщение») — не посты."""
    return len(text) < 160 and bool(re.search(r"\bpinned\b|закрепил", text, re.I))


def _stats_tail(pid: int, posts: dict) -> bool:
    """Текст статистики («Вчера, 9 ноября: …»), вышедший ответом сразу после картинки «СТАТИСТИКА БОТА»."""
    p = posts.get(str(pid)) or {}
    if not _text(p.get("html", "")).startswith("Вчера,"):
        return False
    return any("СТАТИСТИКА БОТА" in (posts.get(str(j)) or {}).get("html", "") for j in range(pid - 1, pid - 4, -1))


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
    # тормоза: после Flood control ВК блокирует стену, поэтому молчим и постепенно наращиваем темп
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
        started = "МАТЧ НАЧАЛСЯ" in text
        if len(text) < 20 or ("#live" in p.get("html", "") and not started):   # голы и прочий live в ВК не дублируем
            state["vk_last"] = pid
            continue
        if text.startswith("📖 Продолжение") or _service(text) or _stats_tail(pid, posts):
            # продолжение новости и текст статистики уже вошли в свой пост (ниже); «pinned a photo» — служебное
            state["vk_last"] = pid
            continue
        if "СТАТИСТИКА БОТА" in text:   # картинка статистики + текст ответом в Telegram → в ВК одним постом
            for j in range(pid + 1, pid + 4):
                if _stats_tail(j, posts):
                    text = text.rstrip() + "\n\n" + _text(posts[str(j)].get("html", ""))
                    break
        if "Продолжение — в ответе" in text:   # длинная новость: в ВК — одним постом, вместе с продолжением
            text = "\n".join(ln for ln in text.split("\n") if "Продолжение — в ответе" not in ln)
            for j in range(pid + 1, pid + 4):
                cont = _text((posts.get(str(j)) or {}).get("html", ""))
                if cont.startswith("📖 Продолжение"):
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
                break                     # пост совсем свежий — страница на сайте ещё публикуется, вернёмся позже
            link = _site_link(pid)
        short = _short(link)   # внешние ссылки ВК не прячет под слово — делаем короткую vk.cc/…
        text += "\n\n" + (f"📺 Смотреть матч онлайн 👉 {short}" if started else f"📊 Подробнее на сайте 👉 {short}")
        # с личным ключом — фото поста; с ключом сообщества — текст со ссылкой на наш сайт
        from . import dzen, postimg
        tags = dzen.hashtags(p.get("html", ""), "начало" if started else dzen.kind(p.get("html", "")), limit=8)
        if tags:   # хештеги по теме (команды, игроки, лига) — ВК лучше показывает пост в поиске и рекомендациях
            text += "\n\n" + tags
        img = postimg.image_for(p, ("начало" if started else dzen.kind(p.get("html", "")) or "новость"), posts)
        _photo.err = "" if img else "картинка поста не получена"
        _photo.wall_err = ""
        photo = _photo(img) if img else None
        state["vk_err"] = f"{pid} фото: {_photo.err}" if not photo else None   # старую ошибку стираем
        state["vk_wall_err"] = f"{pid}: {_photo.wall_err}" if _photo.wall_err else None   # почему не вышло фото стены по личному ключу
        # фото «из сообщений» сообщества ВК на стене один не показывает — пробуем вместе с карточкой ссылки
        # (наше фото как обложка ссылки); не принял — публикуем как раньше, текст со ссылкой
        if photo and photo.startswith("photo-"):   # фото «из сообщений» сообщества — только вместе со ссылкой
            tries = [[photo, link], [photo]] if link != SITE else [[photo]]
        else:                                      # фото стены (личный ключ) ВК показывает как обычную картинку
            tries = [[photo] if photo else []]
        try:
            for i, att in enumerate(tries):
                try:
                    _call("wall.post", owner_id=-GROUP_ID, from_group=1, message=text[:15000], attachments=",".join(att))
                    state["vk_mode"] = "+".join(a[:5] for a in att) or "текст"
                    break
                except RuntimeError as e:
                    if i == len(tries) - 1:
                        raise
                    state["vk_err"] = f"{pid} фото+ссылка: {e}"[:300]
            state["vk_last"] = pid
            state["vk_at_ts"] = time.time()
            lim["n"] = lim.get("n", 0) + 1
            state["vk_hour"] = lim
            (state.get("vk_try") or {}).pop(str(pid), None)
            state["vk_err"] = None
            done += 1
        except Exception as e:
            msg = str(e)
            print(f"  ! ВК: пост {pid} не опубликован: {msg}")
            state["vk_err"] = f"{pid}: {msg}"[:300]   # видно в data/state.json без журнала GitHub
            tries = state.setdefault("vk_try", {})
            tries[str(pid)] = tries.get(str(pid), 0) + 1
            if "flood" in msg.lower() or ": 9" in msg:
                # ВК ограничил частоту: старый бэклог не долбим — начинаем со свежих постов,
                # иначе бот тратит часы на посты, которые уже неактуальны
                newest_now = max(int(k) for k in posts)
                state["vk_last"] = max(pid, newest_now - 2)
                tries.pop(str(pid), None)
                state["vk_pause_ts"] = time.time() + PAUSE_S
                print(f"  ВК: пауза {PAUSE_S // 60} минут — ВК ограничил частоту; "
                      f"старый бэклог пропущен, продолжим после {state['vk_last']}")
                break
            if tries[str(pid)] >= TRIES_LIMIT:   # безнадёжный пост не должен держать очередь
                state["vk_last"] = pid
                tries.pop(str(pid), None)
                print(f"  ВК: пост {pid} пропущен после {TRIES_LIMIT} неудач")
                continue
            break                         # временная ошибка — попробуем в следующий проход
    if done:
        print(f"  ВК: опубликовано постов: {done}")
    return done
