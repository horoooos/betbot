"""Photo stories published with the community token, independently of wall photos."""
from __future__ import annotations

from io import BytesIO
import os
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


def publish_image(image: bytes, text: str = "", *, test: bool = False) -> dict:
    token = os.environ.get("VK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("VK_TOKEN отсутствует")
    server = vk._call("stories.getPhotoUploadServer", _tok=token, group_id=vk.GROUP_ID, add_to_news=1)
    uploaded = _upload(server["upload_url"], portrait(image, text, test))
    time.sleep(1)
    saved = vk._call("stories.save", _tok=token, upload_results=uploaded)
    items = saved.get("items", []) if isinstance(saved, dict) else []
    if not items:
        raise RuntimeError("VK stories: сохранение не вернуло историю")
    story = items[0]
    if story.get("owner_id") != -vk.GROUP_ID or not story.get("id"):
        raise RuntimeError("VK stories: история сохранена не в ожидаемом сообществе")
    reference = f"{story['owner_id']}_{story['id']}"
    print("STORY_URL:", "https://vk.com/story" + reference, flush=True)
    time.sleep(1)
    read = vk._call("stories.getById", _tok=token, stories=reference)
    verified = read.get("items", []) if isinstance(read, dict) else []
    found = next((item for item in verified if item.get("id") == story["id"]
                  and item.get("owner_id") == -vk.GROUP_ID), None)
    if not found or found.get("type") != "photo" or not found.get("photo") or found.get("is_deleted"):
        raise RuntimeError("VK stories: созданная история не прошла проверку фото; повторно не публикуем")
    print("STORY_PHOTO_VERIFIED: true", flush=True)
    return found
