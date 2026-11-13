"""Photo stories published with the community token, independently of wall photos."""
from __future__ import annotations

from io import BytesIO
import json
import os
from datetime import datetime, timezone
import textwrap
import time

from PIL import Image, ImageDraw, ImageOps
import requests

from . import card, vk


def portrait(image: bytes, text: str = "", test: bool = False) -> bytes:
    canvas = Image.new("RGB", (1080, 1920), "#10172f")
    draw = ImageDraw.Draw(canvas)
    draw.text((60, 100), "АИ СТАВИТ", font=card.font(62), fill="#ffc400")
    with Image.open(BytesIO(image)) as source:
        picture = ImageOps.contain(source.convert("RGB"), (960, 840))
    canvas.paste(picture, ((1080 - picture.width) // 2, 260))
    lines = textwrap.wrap(vk._text(text), width=43)[:12]
    y = 260 + picture.height + 55
    for line in lines:
        draw.text((60, y), line, font=card.font(34), fill="white")
        y += 47
    draw.text((60, 1740), "Тест истории" if test else "Спортивные новости и прогнозы",
              font=card.font(32), fill="#ffc400")
    draw.text((60, 1800), "horoooos.github.io/betbot", font=card.font(30), fill="white")
    result = BytesIO()
    canvas.save(result, "JPEG", quality=92)
    return result.getvalue()


def _upload(url: str, image: bytes) -> str:
    try:
        response = requests.post(url, files={"file": ("story.jpg", image, "image/jpeg")}, timeout=60)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        raise RuntimeError("VK stories: ошибка загрузки; подписанный URL скрыт") from None
    except ValueError:
        raise RuntimeError("VK stories: сервер загрузки вернул не JSON") from None
    body = payload.get("response", payload)
    if not isinstance(body, dict) or not isinstance(body.get("upload_result"), str) or not body["upload_result"]:
        def shape(value, depth=0):
            if isinstance(value, dict) and depth < 3:
                return {str(k)[:40]: shape(v, depth + 1) for k, v in list(value.items())[:12]}
            if isinstance(value, list):
                return [shape(value[0], depth + 1)] if value else []
            return type(value).__name__
        print("STORY_UPLOAD_RESPONSE_SHAPE:", shape(payload), flush=True)
        if isinstance(payload.get("error"), dict):
            print("STORY_UPLOAD_ERROR_CODE:", payload["error"].get("error_code"), flush=True)
        raise RuntimeError("VK stories: сервер не вернул upload_result")
    return body["upload_result"]


def verify_story(story: dict) -> dict:
    token = os.environ.get("VK_TOKEN", "").strip()
    reference = f"{story['owner_id']}_{story['id']}"
    read = vk._call("stories.getById", _tok=token, stories=reference)
    verified = read.get("items", []) if isinstance(read, dict) else []
    found = next((item for item in verified if item.get("id") == story["id"]
                  and item.get("owner_id") == -vk.GROUP_ID), None)
    if not found or found.get("type") != "photo" or not found.get("photo") or found.get("is_deleted"):
        raise RuntimeError("VK stories: созданная история не прошла проверку фото; повторно не публикуем")
    return found


def publish_image(image: bytes, text: str = "", *, test: bool = False, on_saving=None, on_saved=None) -> dict:
    token = os.environ.get("VK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("VK_TOKEN отсутствует")
    server = vk._call("stories.getPhotoUploadServer", _tok=token, group_id=vk.GROUP_ID, add_to_news=1)
    uploaded = _upload(server["upload_url"], portrait(image, text, test))
    time.sleep(1)
    if on_saving:
        on_saving()
    saved = vk._call("stories.save", _tok=token, upload_results=uploaded)
    items = saved.get("items", []) if isinstance(saved, dict) else []
    if not items:
        raise RuntimeError("VK stories: сохранение не вернуло историю")
    story = items[0]
    if story.get("owner_id") != -vk.GROUP_ID or not story.get("id"):
        raise RuntimeError("VK stories: история сохранена не в ожидаемом сообществе")
    if on_saved:
        on_saved(story)
    reference = f"{story['owner_id']}_{story['id']}"
    print("STORY_URL:", "https://vk.com/story" + reference, flush=True)
    time.sleep(1)
    found = verify_story(story)
    print("STORY_PHOTO_VERIFIED: true", flush=True)
    return found


def crosspost(state: dict, checkpoint=None) -> int:
    """One current channel story per pass; preserve created IDs before verification."""
    if os.environ.get("VK_STORIES_ENABLED") != "1" or not os.environ.get("VK_TOKEN"):
        return 0
    posts = json.loads(vk.CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    now = time.time()
    checkpoint = checkpoint or (lambda: None)
    newest = max(map(int, posts))
    if "vk_story_last" not in state:
        state["vk_story_last"] = newest
        print(f"ВК истории: включены после поста {newest}")
        return 0
    if now < float(state.get("vk_story_retry_at") or 0):
        return 0

    def complete(pid, story):
        state["vk_story_last"] = max(int(state["vk_story_last"]), int(pid))
        state["vk_story_at"] = now
        state["vk_story_url"] = f"https://vk.com/story{story['owner_id']}_{story['id']}"
        state["vk_story_err"] = None
        state.pop("vk_story_pending", None)
        state.pop("vk_story_retry_at", None)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily = state.get("vk_story_day") or {}
        state["vk_story_day"] = {"date": day, "count": (int(daily.get("count", 0)) if daily.get("date") == day else 0) + 1}
        checkpoint()

    pending = state.get("vk_story_pending")
    if isinstance(pending, dict):
        if not pending.get("id"):
            state["vk_story_err"] = "Результат сохранения истории неизвестен; повторная публикация остановлена до проверки"
            return 0
        try:
            story = verify_story(pending)
            complete(pending["pid"], story)
            return 1
        except Exception as error:
            state["vk_story_err"] = str(error)[:250] if isinstance(error, RuntimeError) else "Ошибка проверки истории"
            state["vk_story_retry_at"] = now + 3600
            return 0
    if now - float(state.get("vk_story_at") or 0) < 900:
        return 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = state.get("vk_story_day") or {}
    if daily.get("date") == day and int(daily.get("count", 0)) >= 16:
        return 0
    from . import dzen, postimg
    for pid in sorted(int(k) for k in posts if int(k) > int(state["vk_story_last"])):
        post = posts[str(pid)]
        kind = dzen.kind(post.get("html", ""))
        if not kind or vk._service(vk._text(post.get("html", ""))):
            state["vk_story_last"] = pid
            continue
        try:
            timestamp = datetime.fromisoformat(post["t"].replace("Z", "+00:00")).timestamp()
            if now - timestamp > 86400:
                state["vk_story_last"] = pid
                continue
            image = postimg.image_for(post, kind, posts)
            if not image:
                raise RuntimeError("Картинка истории не создана")

            def saving():
                state["vk_story_pending"] = {"pid": pid, "started_at": now}
                checkpoint()

            def saved(story):
                state["vk_story_pending"] = {"pid": pid, "id": story["id"], "owner_id": story["owner_id"]}
                checkpoint()

            story = publish_image(image, post.get("html", ""), on_saving=saving, on_saved=saved)
            complete(pid, story)
            return 1
        except Exception as error:
            # An explicit API rejection means stories.save did not create it.
            if str(error).startswith("VK stories.save:"):
                state.pop("vk_story_pending", None)
            state["vk_story_err"] = str(error)[:250] if isinstance(error, RuntimeError) else "Ошибка публикации истории; результат сохранения требует проверки"
            state["vk_story_retry_at"] = now + 3600
            print("ВК истории:", state["vk_story_err"])
            checkpoint()
            return 0
    return 0
