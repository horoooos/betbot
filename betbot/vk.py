"""Кросспостинг из Telegram-канала в сообщество ВКонтакте (vk.com/aistavvit).

Берём новые посты канала (data/channel.json, его обновляет pages.sync_channel) и публикуем на стене
сообщества от имени сообщества: текст + картинка поста. Ставки/букмекеры и реферальные ссылки
вырезаем — ВК строго относится к рекламе ставок. Ссылка ведёт на наш сайт.

Для загрузки фото нужен личный ключ администратора VK_USER_TOKEN (wall, photos, offline).
VK_TOKEN публикует запись от имени сообщества. Без загруженной картинки публикация откладывается.
"""
from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

import requests

GROUP_ID = 228963529           # vk.com/aistavvit
API = "https://api.vk.ru/method/"
V = "5.199"
CHANNEL = Path(__file__).resolve().parent.parent / "data" / "channel.json"
SITE = "https://horoooos.github.io/betbot/"
MAX_PER_PASS = 1               # за проход — один пост: ВК банит стену за пачки (ошибка 9 Flood control)
MIN_GAP_S = 900                # и не чаще одного поста за 15 минут
HOUR_LIMIT = 2                 # больше 2 постов в час на стену не публикуем
DAY_LIMIT = 16                 # и не больше 16 в сутки — ВК режет за частые посты
TRIES_LIMIT = 3                # после трёх неудач пост пропускаем, чтобы очередь не вставала навсегда
PAUSE_S = 60 * 60
STALE_GAP = 2                  # отставание больше 2 постов — старую очередь пропускаем              # после «Flood control» молчим час — иначе ВК блокирует стену надолго
STOP = re.compile(r"betboom|бетбум|букмекер|промокод|фрибет|реферал", re.I)


class PhotoVerificationError(RuntimeError):
    """ВК не удалось подтвердить фото; запись нельзя считать опубликованной."""


class ShortLinkError(RuntimeError):
    """Не удалось получить короткую ссылку ВК; длинный адрес не подставляется молча."""


def _is_flood_error(error: object) -> bool:
    message = str(error).lower()
    return "flood" in message or ": 9 " in f" {message} "


def _token() -> str:
    """Личный ключ админа (может грузить фото) или ключ сообщества (VK_TOKEN: публикует текст со ссылкой)."""
    return os.environ.get("VK_USER_TOKEN") or os.environ.get("VK_TOKEN") or ""


def enabled() -> bool:
    return bool(_token())


def _verified_reserve_photo() -> str:
    if os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
        return ""
    photo = os.environ.get("VK_WALL_RESERVE_PHOTO", "").strip()
    if photo and not re.fullmatch(r"photo-?[1-9]\d*_[1-9]\d*", photo):
        raise RuntimeError("VK_WALL_RESERVE_PHOTO должен содержать проверенный публичный ID фото")
    return photo


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


SEED_PHOTOS = [   # фото сообщества, загруженные ранее (аварийный запас, когда загрузка во флуде)
    "photo-228963529_457239775",
    "photo-228963529_457239776",
    "photo-228963529_457239773",
    "photo-228963529_457239774",
    "photo-228963529_457239766",
]


def _photo(img: bytes) -> str | None:
    """Загружает фото именно в альбом стены через личный ключ администратора."""
    import time
    s = None
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
        except Exception as e:
            _photo.wall_err = f"попытка {attempt + 1}: {e}"[:250]
            print(f"  ! ВК: фото стены не загрузилось (попытка {attempt + 1}): {e}")
            if _is_flood_error(e):  # Flood control не лечится повтором и тем более другим типом фото
                break
            time.sleep(3)
    if not s:
        reasons = []
        if getattr(_photo, "wall_err", ""):
            reasons.append(f"фото стены: {_photo.wall_err}")
        if not os.environ.get("VK_USER_TOKEN"):
            reasons.append("нет VK_USER_TOKEN с правом загрузки фото стены")
        _photo.err = " | ".join(reasons)[:300] or "ВК не сохранил фото стены"
        print(f"  ! ВК: изображение не загружено: {_photo.err}; публикация отложена")
        return None
    try:
        return f"photo{s['owner_id']}_{s['id']}" + (f"_{s['access_key']}" if s.get("access_key") else "")
    except Exception as e:
        _photo.err = f"неполный ответ photos.saveWallPhoto: {e}"[:300]
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


def _short(url: str, state: dict | None = None) -> str:
    """Возвращает vk.cc-ссылку и кэширует её. Длинный адрес не подставляется молча."""
    cache = state.setdefault("vk_shortlinks", {}) if state is not None else {}
    if not isinstance(cache, dict):
        cache = {}
        if state is not None:
            state["vk_shortlinks"] = cache
    cached = cache.get(url)
    if isinstance(cached, str) and cached.startswith("vk.cc/"):
        return cached
    token = os.environ.get("VK_TOKEN") or os.environ.get("VK_USER_TOKEN")
    if not token:
        raise ShortLinkError("нет токена ВК для сокращения ссылки")
    errors = []
    tokens = list(dict.fromkeys((os.environ.get("VK_TOKEN"), os.environ.get("VK_USER_TOKEN"))))
    if _verified_reserve_photo() or os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
        tokens = [os.environ.get("VK_TOKEN")]
    for token in tokens:
        if not token:
            continue
        try:
            result = _call("utils.getShortLink", _tok=token, url=url)
            raw = str(result.get("short_url") or "").strip()
            parsed = urlsplit(raw if "://" in raw else "https://" + raw)
            if parsed.netloc.lower() not in {"vk.cc", "www.vk.cc"} or not parsed.path.strip("/"):
                raise ValueError("VK не вернул ссылку vk.cc")
            short = f"vk.cc{parsed.path}"
            cache[url] = short
            while len(cache) > 100:
                cache.pop(next(iter(cache)))
            return short
        except Exception as e:
            errors.append(str(e))
    raise ShortLinkError(f"не удалось сократить URL: {'; '.join(errors) or 'нет токена ВК'}") from None


def _ensure_short_comment(post_id: int, message: str) -> None:
    """Пишет ссылку первым комментарием, не дублируя её при повторной попытке."""
    if _verified_reserve_photo() or os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
        created = _call("wall.createComment", _tok=os.environ.get("VK_TOKEN"), owner_id=-GROUP_ID,
                        post_id=post_id, from_group=1, message=message, guid=f"betbot-site-{post_id}")
        if not isinstance(created, dict) or not created.get("comment_id"):
            raise RuntimeError("ВК не подтвердил комментарий со ссылкой")
        return
    # Чтение стены требует пользовательского ключа; публикация от имени группы
    # выполняется ключом сообщества, как и wall.post.
    read_token = os.environ.get("VK_USER_TOKEN") or os.environ.get("VK_TOKEN")
    result = _call("wall.getComments", _tok=read_token, owner_id=-GROUP_ID, post_id=post_id,
                   count=100, sort="desc")
    comments = result.get("items", []) if isinstance(result, dict) else []
    if any(str(c.get("text", "")).strip() == message for c in comments if isinstance(c, dict)):
        return
    write_token = os.environ.get("VK_TOKEN") or os.environ.get("VK_USER_TOKEN")
    created = _call("wall.createComment", _tok=write_token, owner_id=-GROUP_ID, post_id=post_id,
                    from_group=1, message=message)
    if not isinstance(created, dict) or not created.get("comment_id"):
        raise RuntimeError("ВК не подтвердил создание комментария со ссылкой")


def _retry_short_comments(state: dict) -> bool:
    """Повторяет отправку ссылки, если пост уже опубликован, а комментарий не прошёл."""
    pending = state.get("vk_comment_pending")
    if not isinstance(pending, dict):
        pending = {}
    now = time.time()
    attempted = False
    for source_id, item in list(pending.items()):
        if not isinstance(item, dict):
            pending.pop(source_id, None)
            continue
        if now < float(item.get("retry_at") or 0):
            continue
        attempted = True
        try:
            _ensure_short_comment(int(item["post_id"]), str(item["message"]))
            pending.pop(source_id, None)
            state["vk_comment_err"] = None
            print(f"  ВК: ссылка из поста {source_id} добавлена в комментарии")
        except Exception as e:
            item["retry_at"] = now + 900
            item["error"] = str(e)[:200]
            state["vk_comment_err"] = f"{source_id}: {str(e)[:200]}"
            print(f"  ! ВК: ссылка в комментарии к посту {source_id} не добавлена: {e}")
        break  # не отправляем пачку комментариев за один проход
    state["vk_comment_pending"] = pending
    return attempted


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


def _pending_has_photo(pending: dict) -> bool:
    if pending.get("poll_ts") is not None:
        from .vk_wall_events import PhotoMonitor
        monitor = PhotoMonitor(os.environ.get("VK_TOKEN"))
        monitor.start()
        monitor.server["ts"] = pending["poll_ts"]
        return monitor.verify(int(pending["post_id"]))
    result = _call("wall.getById", _tok=os.environ.get("VK_SERVICE_KEY") or os.environ.get("VK_USER_TOKEN"),
                   posts=f"-{GROUP_ID}_{pending['post_id']}")
    items = result.get("items", []) if isinstance(result, dict) else []
    attachments = items[0].get("attachments", []) if items else []
    return any(a.get("type") == "photo" for a in attachments if isinstance(a, dict))


def _resolve_pending_post(state: dict) -> bool:
    """Resolve a post created before a transient verification failure; never repost it blindly."""
    pending = state.get("vk_verify_pending")
    if not isinstance(pending, dict):
        return False
    # Older versions retried reads after 15 minutes even during the hour-long
    # flood pause. Migrate that scheduled retry once, without contacting VK.
    if not pending.get("retry_delay_s") and _is_flood_error(state.get("vk_err", "")):
        retry_at = float(state.get("vk_verify_retry_at") or 0)
        state["vk_verify_retry_at"] = max(retry_at, retry_at - 900 + PAUSE_S)
        pending["retry_delay_s"] = PAUSE_S
        state["vk_pause_ts"] = max(float(state.get("vk_pause_ts") or 0), state["vk_verify_retry_at"])
    if time.time() < float(state.get("vk_verify_retry_at") or 0):
        return True
    try:
        has_photo = _pending_has_photo(pending)
    except Exception as error:
        state["vk_err"] = f"{pending.get('pid')}: ожидает проверки фото записи {pending.get('post_id')}: {error}"[:300]
        delay = PAUSE_S if _is_flood_error(error) else 900
        pending["retry_delay_s"] = delay
        state["vk_verify_retry_at"] = time.time() + delay
        if _is_flood_error(error):
            state["vk_pause_ts"] = max(float(state.get("vk_pause_ts") or 0), state["vk_verify_retry_at"])
        print(f"  ВК: запись {pending.get('post_id')} создана; проверку повторю позже: {error}")
        return True
    if not has_photo:
        try:
            _call("wall.delete", _tok=os.environ.get("VK_TOKEN") if os.environ.get("VK_WALL_REQUIRE_FRESH") == "1" else os.environ.get("VK_USER_TOKEN"), owner_id=-GROUP_ID,
                  post_id=int(pending["post_id"]))
        except Exception as error:
            state["vk_err"] = f"{pending.get('pid')}: запись без фото не удалена: {error}"[:300]
            delay = PAUSE_S if _is_flood_error(error) else 900
            pending["retry_delay_s"] = delay
            state["vk_verify_retry_at"] = time.time() + delay
            return True
        pid = str(pending.get("pid", ""))
        cursor = state.setdefault("vk_photo_cursor", {})
        cursor[pid] = max(int(cursor.get(pid, 0)), int(pending.get("cursor", 0)) + 1)
        state.pop("vk_verify_pending", None)
        state.pop("vk_verify_retry_at", None)
        state["vk_err"] = f"{pid}: запись без фото удалена; повторю с другим вложением"
        return True

    pid = int(pending["pid"])
    state["vk_last"] = max(int(state.get("vk_last", 0)), pid)
    state["vk_at_ts"] = time.time()
    hour = time.strftime("%Y-%m-%d-%H", time.gmtime())
    lim = state.get("vk_hour") or {}
    if lim.get("h") != hour:
        lim = {"h": hour, "n": 0}
    lim["n"] = int(lim.get("n", 0)) + 1
    state["vk_hour"] = lim
    day = time.strftime("%Y-%m-%d", time.gmtime())
    dl = state.get("vk_day") or {}
    if dl.get("d") != day:
        dl = {"d": day, "n": 0}
    dl["n"] = int(dl.get("n", 0)) + 1
    state["vk_day"] = dl
    state["vk_mode"] = pending.get("attachment", "photo")
    state.setdefault("vk_photo_cursor", {}).pop(str(pid), None)
    state.pop("vk_verify_pending", None)
    state.pop("vk_verify_retry_at", None)
    state["vk_err"] = None
    comment = f"🔗 Сайт проекта: {pending['short']}"
    try:
        _ensure_short_comment(int(pending["post_id"]), comment)
        state.setdefault("vk_comment_pending", {}).pop(str(pid), None)
        state["vk_comment_err"] = None
    except Exception as error:
        state.setdefault("vk_comment_pending", {})[str(pid)] = {
            "post_id": int(pending["post_id"]), "message": comment,
            "retry_at": time.time() + 900, "error": str(error)[:200],
        }
        state["vk_comment_err"] = f"{pid}: {str(error)[:200]}"
    print(f"  ВК: фото записи {pending['post_id']} подтверждено; пост {pid} отмечен опубликованным")
    return True


def crosspost(state: dict, checkpoint=None) -> int:
    """Публикует в ВК посты канала, вышедшие после прошлого запуска. Возвращает, сколько опубликовано."""
    if not enabled() or not CHANNEL.exists():
        return 0
    posts = json.loads(CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    newest = max(int(k) for k in posts)
    checkpoint = checkpoint or (lambda: None)
    reserve = _verified_reserve_photo()
    if reserve and not state.get("vk_reserve_mode_initialized"):
        # The old pending post used an unverified attachment. Keep its identity
        # for review and start the new, confirmed route with future channel posts.
        old_pending = state.pop("vk_verify_pending", None)
        if old_pending:
            state.setdefault("vk_legacy_pending", []).append(old_pending)
            state["vk_legacy_pending"] = state["vk_legacy_pending"][-10:]
        state["vk_reserve_mode_initialized"] = True
        state["vk_last"] = newest
        state["vk_at_ts"] = time.time()
        state["vk_pause_ts"] = 0
        state["vk_photo_until"] = 0
        state["vk_err"] = None
        state.pop("vk_verify_retry_at", None)
        checkpoint()
        print(f"ВК: проверенное резервное фото включено; начинаем после {newest}")
        return 0
    if "vk_last" not in state:           # первый запуск: старое не переносим, начинаем с новых постов
        state["vk_last"] = newest
        print(f"  ВК: кросспостинг включён, начинаем после поста {newest}")
        return 0
    if _resolve_pending_post(state):
        return 0
    if os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
        retry_at = max(float(state.get("vk_fresh_retry_at") or 0),
                       float(os.environ.get("VK_WALL_FRESH_NOT_BEFORE") or 0))
        if time.time() < retry_at:
            state["vk_err"] = "Загрузка актуального фото ограничена VK; архивная подмена отключена"
            return 0
    if newest - int(state["vk_last"]) > STALE_GAP:   # очередь устарела — публикуем только новые посты
        skipped = newest - int(state["vk_last"])
        state["vk_last"] = newest - STALE_GAP
        print(f"  ВК: очередь очищена, пропущено {skipped} старых постов")
    resume = (Path(__file__).resolve().parent.parent / "data" / "vk_resume.txt")
    if resume.exists():   # ручной сигнал «возобновить публикации сейчас»
        try:
            marker_key = resume.read_text(encoding="utf-8-sig").strip() or "resume"
        except OSError:
            marker_key = "resume"
        if state.get("vk_resume_key") != marker_key:
            state["vk_resume_key"] = marker_key
            state["vk_pause_ts"] = 0
            state["vk_floods"] = 0
            state["vk_err"] = None
            print("  ВК: публикации возобновлены вручную")
        try:
            resume.unlink()
        except OSError:
            pass
    # тормоза: после Flood control ВК блокирует стену, поэтому молчим и постепенно наращиваем темп
    now_ts = time.time()
    if now_ts < max(float(state.get("vk_pause_ts") or 0), float(state.get("vk_photo_until") or 0)):
        return 0
    hour = time.strftime("%Y-%m-%d-%H", time.gmtime())
    lim = state.get("vk_hour") or {}
    if lim.get("h") != hour:
        lim = {"h": hour, "n": 0}
    if lim.get("n", 0) >= HOUR_LIMIT:
        return 0
    if now_ts - float(state.get("vk_at_ts") or 0) < MIN_GAP_S:
        return 0
    day = time.strftime("%Y-%m-%d", time.gmtime())
    dl = state.get("vk_day") or {}
    if dl.get("d") != day:
        dl = {"d": day, "n": 0}
    if dl.get("n", 0) >= DAY_LIMIT:
        return 0
    if now_ts < float(state.get("vk_link_retry_at") or 0):
        return 0
    if _retry_short_comments(state):
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
        try:
            short = _short(link, state)
            state["vk_short_err"] = None
            state.pop("vk_link_retry_at", None)
        except ShortLinkError as e:
            state["vk_short_err"] = f"{pid}: {e}"[:250]
            state["vk_link_retry_at"] = time.time() + 900
            print(f"  ВК: пост {pid} отложен — короткая ссылка недоступна: {e}")
            break
        text += "\n\n" + (f"📺 Смотреть матч онлайн 👉 {short}" if started else f"📊 Подробнее на сайте 👉 {short}")
        # Личный ключ загружает картинку, ключ сообщества публикует запись.
        from . import dzen, postimg
        tags = dzen.hashtags(p.get("html", ""), "начало" if started else dzen.kind(p.get("html", "")), limit=8)
        if tags:   # хештеги по теме (команды, игроки, лига) — ВК лучше показывает пост в поиске и рекомендациях
            text += "\n\n" + tags
        fresh_probe = bool(reserve and os.environ.get("VK_WALL_PREFER_FRESH") == "1"
                           and os.environ.get("VK_USER_TOKEN")
                           and now_ts >= max(float(state.get("vk_fresh_retry_at") or 0),
                                             float(os.environ.get("VK_WALL_FRESH_NOT_BEFORE") or 0)))
        img = postimg.image_for(p, ("начало" if started else dzen.kind(p.get("html", "")) or "новость"), posts) if not reserve or fresh_probe else None
        _photo.err = "" if img or reserve else "картинка поста не получена"
        _photo.wall_err = ""
        photo_off = now_ts < float(state.get("vk_photo_until") or 0)   # ВК во флуде на загрузку фото
        cache = state.setdefault("vk_photos", [])
        photo = None if photo_off else (_photo(img) if img else None)
        if photo and not reserve:
            state["vk_photo_source"] = "fresh"
            state["vk_fresh_err"] = None
            state["vk_fresh_retry_at"] = 0
        if reserve:
            if photo:
                state["vk_photo_source"] = "fresh"
                state["vk_fresh_err"] = None
                state["vk_fresh_retry_at"] = 0
            else:
                if fresh_probe:
                    error = getattr(_photo, "err", "") or "картинка поста не получена"
                    state["vk_fresh_err"] = str(error)[:300]
                    # The upload restriction is independent of community wall posting.
                    # Keep archive posts working; do not hammer the personal key.
                    state["vk_fresh_retry_at"] = time.time() + (6 * 3600 if _is_flood_error(error) else 3600)
                    checkpoint()
                    print("  ВК: новое фото пока недоступно; повторная проверка загрузки отложена")
                photo = reserve
                state["vk_photo_source"] = "archive"
                text += "\n\nИллюстрация из архива проекта."
        if photo and photo.startswith("photo-"):
            cache.insert(0, photo)
            del cache[12:]                       # держим последние 12 загруженных
            state["vk_photos"] = cache
        # VK can silently discard old photo IDs, including previously saved
        # community photos. Publish only the image uploaded for this post.
        photo_candidates = [photo] if photo else []
        if not photo_candidates:
            # Картинка обязательна. Оставляем указатель очереди на этом посте и
            # повторяем попытку позже; текстом без вложения не публикуем.
            state["vk_err"] = f"{pid} фото: нет доступного изображения ({_photo.err})"[:300]
            delay = PAUSE_S if _is_flood_error(_photo.err) else 900
            state["vk_photo_until"] = time.time() + delay
            if os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
                state["vk_fresh_err"] = str(_photo.err)[:300]
                state["vk_fresh_retry_at"] = time.time() + (6 * 3600 if _is_flood_error(_photo.err) else 3600)
                checkpoint()
            print(f"  ВК: пост {pid} отложен — не удалось получить/загрузить фото: {_photo.err}")
            break
        if "flood" in (_photo.err or "").lower() or " 9 " in f" {_photo.err} ":
            state["vk_photo_until"] = time.time() + PAUSE_S
        if not photo:
            photo = photo_candidates[0]
        state["vk_err"] = f"{pid} фото: {_photo.err}" if _photo.err else None
        state["vk_wall_err"] = f"{pid}: {_photo.wall_err}" if _photo.wall_err else None   # почему не вышло фото стены по личному ключу
        # Сначала прикрепляем проверенное фото стены вместе со ссылкой, затем фото отдельно.
        tries = []
        for candidate in photo_candidates:
            if candidate.startswith("photo-"):
                tries.append([candidate, link])
            tries.append([candidate])
        last_photo_error = None
        photo_cursor = state.setdefault("vk_photo_cursor", {})
        cursor = max(0, int(photo_cursor.get(str(pid), 0)))
        try:
            for i, att in enumerate(tries[cursor:], start=cursor):
                try:
                    monitor = None
                    if reserve or os.environ.get("VK_WALL_REQUIRE_FRESH") == "1":
                        from .vk_wall_events import PhotoMonitor
                        monitor = PhotoMonitor(os.environ.get("VK_TOKEN"))
                        monitor.start()
                    # стену публикуем ключом сообщества: у Kate-токена лимит на wall.post (9 Flood control),
                    # а загрузка фото — личным (photos.* групповым ключом недоступны)
                    result = _call("wall.post", _tok=os.environ.get("VK_TOKEN"), owner_id=-GROUP_ID, from_group=1,
                                   message=text[:15000], attachments=",".join(att), guid=f"betbot-channel-{GROUP_ID}-{pid}-{i}")
                    post_id = result.get("post_id") if isinstance(result, dict) else None
                    if not post_id:
                        raise PhotoVerificationError("VK wall.post не вернул id записи для проверки фото")
                    state["vk_verify_pending"] = {
                        "pid": pid, "post_id": int(post_id), "short": short,
                        "attachment": "+".join(a[:5] for a in att), "cursor": i,
                    }
                    if monitor:
                        state["vk_verify_pending"]["poll_ts"] = monitor.server["ts"]
                    checkpoint()
                    try:
                        has_photo = monitor.verify(int(post_id)) if monitor else _pending_has_photo(state["vk_verify_pending"])
                    except Exception as check_error:
                        raise PhotoVerificationError(
                            f"запись {post_id} создана; проверка фото временно недоступна ({check_error})"
                        ) from None
                    if not has_photo:
                        # Удаляем запись, если ВК принял запрос, но потерял картинку.
                        try:
                            _call("wall.delete", _tok=os.environ.get("VK_TOKEN") if os.environ.get("VK_WALL_REQUIRE_FRESH") == "1" else os.environ.get("VK_USER_TOKEN"), owner_id=-GROUP_ID,
                                  post_id=post_id)
                        except Exception as delete_error:
                            raise PhotoVerificationError(
                                f"ВК создал запись без фото и не удалил её ({delete_error})"
                            ) from None
                        state.pop("vk_verify_pending", None)
                        photo_cursor[str(pid)] = i + 1
                        raise RuntimeError("ВК создал запись без фото; запись удалена, пробую резервное вложение")
                    state.pop("vk_verify_pending", None)
                    state["vk_mode"] = "+".join(a[:5] for a in att) or "текст"
                    break
                except PhotoVerificationError:
                    raise
                except RuntimeError as e:
                    last_photo_error = e
                    msg = str(e).lower()
                    if i == len(tries) - 1 or "flood" in msg or ": 9" in msg or "captcha" in msg or ": 14" in msg:
                        raise
                    state["vk_err"] = f"{pid} фото+ссылка: {e}"[:300]
            else:
                raise RuntimeError(f"ни одно резервное фото не прошло проверку: {last_photo_error}")
            state["vk_last"] = pid
            photo_cursor.pop(str(pid), None)
            state["vk_at_ts"] = time.time()
            lim["n"] = lim.get("n", 0) + 1
            state["vk_hour"] = lim
            dl["n"] = dl.get("n", 0) + 1
            state["vk_day"] = dl
            (state.get("vk_try") or {}).pop(str(pid), None)
            state.pop("vk_captcha", None)
            state["vk_floods"] = 0
            state["vk_err"] = None
            comment = f"🔗 Сайт проекта: {short}"
            try:
                _ensure_short_comment(int(post_id), comment)
                state.setdefault("vk_comment_pending", {}).pop(str(pid), None)
                state["vk_comment_err"] = None
            except Exception as comment_error:
                # Стеновой пост уже опубликован с фото. Не дублируем его из-за
                # ошибки комментария; сохраним ссылку и повторим отдельно.
                pending = state.setdefault("vk_comment_pending", {})
                pending[str(pid)] = {"post_id": int(post_id), "message": comment,
                                     "retry_at": time.time() + 900, "error": str(comment_error)[:200]}
                while len(pending) > 100:
                    pending.pop(next(iter(pending)))
                state["vk_comment_err"] = f"{pid}: {str(comment_error)[:200]}"
                print(f"  ! ВК: пост с фото опубликован, ссылку в комментарии отправлю повторно: {comment_error}")
            done += 1
        except Exception as e:
            msg = str(e)
            print(f"  ! ВК: пост {pid} не опубликован: {msg}")
            state["vk_err"] = f"{pid}: {msg}"[:300]   # видно в data/state.json без журнала GitHub
            if isinstance(e, PhotoVerificationError):
                # Не продвигаем очередь и не пытаемся повторно создать запись,
                # пока не удаётся безопасно проверить наличие изображения.
                state["vk_pause_ts"] = time.time() + PAUSE_S
                delay = PAUSE_S if _is_flood_error(e) else 900
                state["vk_verify_retry_at"] = time.time() + delay
                if isinstance(state.get("vk_verify_pending"), dict):
                    state["vk_verify_pending"]["retry_delay_s"] = delay
                print(f"  ВК: публикация {pid} остановлена до проверки фото: {msg}")
                break
            tries = state.setdefault("vk_try", {})
            tries[str(pid)] = tries.get(str(pid), 0) + 1
            if "captcha" in msg.lower() or ": 14" in msg:
                # ВК просит капчу — это его антибот-защита, автоматически её не решаем.
                # Молчим 6 часов; публикации вернутся, когда вход в сообщество подтвердят вручную.
                state["vk_pause_ts"] = time.time() + 6 * 3600
                state["vk_captcha"] = True
                print("  ВК: просит капчу — пауза 6 часов (защиту ВК обходим только вручную: "
                      "подтвердите вход/публикацию в самом ВК)")
                break
            if "flood" in msg.lower() or ": 9" in msg:
                # ВК ограничил частоту: старый бэклог не долбим — начинаем со свежих постов.
                # Если флуд повторяется, пауза растёт: 1 час → 6 часов → 24 часа.
                newest_now = max(int(k) for k in posts)
                state["vk_last"] = max(pid, newest_now - 2)
                tries.pop(str(pid), None)
                n = int(state.get("vk_floods", 0)) + 1
                state["vk_floods"] = n
                pause = PAUSE_S if n == 1 else 6 * 3600 if n == 2 else 24 * 3600
                state["vk_pause_ts"] = time.time() + pause
                print(f"  ВК: Flood control №{n} — пауза {pause // 3600} ч; бэклог пропущен, "
                      f"продолжим после {state['vk_last']}")
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
