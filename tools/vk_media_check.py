"""Controlled VK media diagnostics. Never print tokens or signed upload URLs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urlsplit
from datetime import datetime, timezone

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betbot import postimg, vk


def call(method, token, **params):
    time.sleep(1)
    return vk._call(method, _tok=token, **params)


def link_preview(group, reader, parse_token=None):
    from PIL import Image

    class Metadata(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "meta" and attrs.get("property", "").startswith("og:"):
                self.values[attrs["property"]] = attrs.get("content", "")

    pages = [p for p in (vk.DOCS / "news").glob("*.html") if p.name.split("-", 1)[0].isdigit()]
    # The bot commit can precede Pages deployment. Use a page already public.
    for page in sorted(pages, key=lambda p: int(p.name.split("-", 1)[0]), reverse=True)[:10]:
        link = vk.SITE + "news/" + page.name
        response = requests.get(link, timeout=30)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError("Свежие страницы ещё не опубликованы на GitHub Pages")
    meta = Metadata()
    meta.feed(response.text)
    image_url = meta.values.get("og:image", "")
    host = urlsplit(image_url).hostname or ""
    if not image_url.startswith("https://") or not (image_url.startswith(vk.SITE) or host.endswith(".telesco.pe")):
        raise RuntimeError("Страница не содержит изображения с разрешённого источника")
    image = requests.get(image_url, timeout=30)
    image.raise_for_status()
    with Image.open(BytesIO(image.content)) as picture:
        print("SITE_IMAGE_SIZE:", picture.size, flush=True)
    print("PREVIEW_PAGE:", link, flush=True)
    extra = {}
    if parse_token:
        parsed = call("wall.parseAttachedLink", parse_token, links=json.dumps([link]))
        data = parsed.get("data", [])
        item = data[0] if data else {}
        preview = item.get("link", item).get("photo", {})
        if not preview.get("id") or "owner_id" not in preview:
            raise RuntimeError("VK не подготовил фото для карточки ссылки")
        extra["link_photo_id"] = f"{preview['owner_id']}_{preview['id']}"
        print("PARSED_PREVIEW_PHOTO: true", flush=True)
    post = call("wall.post", group, owner_id=-vk.GROUP_ID, from_group=1,
                message="Тест BetBot: карточка новости с картинкой сайта.",
                attachments=link, link_title=meta.values.get("og:title", "Новость BetBot"),
                guid="betbot-link-preview-" + os.environ.get("GITHUB_RUN_ID", str(int(time.time()))), **extra)
    post_id = int(post["post_id"])
    print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{post_id}", flush=True)
    result = call("wall.getById", reader, posts=f"-{vk.GROUP_ID}_{post_id}")
    items = result.get("items", []) if isinstance(result, dict) else result
    attachments = items[0].get("attachments", []) if items else []
    has_image = any(a.get("type") == "photo" or
                    (a.get("type") == "link" and a.get("link", {}).get("photo")) for a in attachments)
    print("PREVIEW_IMAGE_VERIFIED:", bool(has_image), flush=True)
    if not has_image:
        raise RuntimeError("VK создал запись без подтверждённой картинки-превью")


def main():
    mode = os.environ.get("VK_MEDIA_MODE", "access")
    user = os.environ.get("VK_USER_TOKEN", "").strip()
    group = os.environ.get("VK_TOKEN", "").strip()
    reader = os.environ.get("VK_SERVICE_KEY", "").strip() or user
    if not user:
        raise RuntimeError("VK_USER_TOKEN отсутствует")
    print("API_HOST: api.vk.ru", flush=True)
    print("INDEPENDENT_READ_KEY:", bool(os.environ.get("VK_SERVICE_KEY")), flush=True)
    if mode in {"link-preview", "link-parsed-preview"}:
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        link_preview(group, reader, user if mode == "link-parsed-preview" else None)
        return
    if mode == "access":
        mask = int(call("account.getAppPermissions", user))
        print("PERMISSIONS:", {name: bool(mask & bit) for name, bit in
                              (("photos", 4), ("wall", 8192), ("offline", 65536))}, flush=True)
        print("ACCESS_CHECK_OK: true", flush=True)
        return
    if mode == "album-access":
        result = call("photos.getAlbums", user, owner_id=-vk.GROUP_ID, count=100)
        print("ALBUM_ACCESS_OK: true", flush=True)
        print("ALBUM_COUNT:", result.get("count", len(result.get("items", []))), flush=True)
        return
    if mode not in {"wall", "album"}:
        raise RuntimeError("Неизвестный режим")
    state = json.loads(Path("data/state.json").read_text(encoding="utf-8"))
    until = max(float(state.get(k) or 0) for k in
                ("vk_pause_ts", "vk_photo_until", "vk_verify_retry_at"))
    if time.time() < until:
        raise RuntimeError("Загрузка отложена до " + datetime.fromtimestamp(until, timezone.utc).isoformat())
    posts = json.loads(Path("data/channel.json").read_text(encoding="utf-8"))["posts"]
    pid = max(posts, key=int)
    image = postimg.image_for(posts[pid], "новость", posts)
    if not image:
        raise RuntimeError("Картинка не создана")
    album_id = None
    if mode == "wall":
        server = call("photos.getWallUploadServer", user, group_id=vk.GROUP_ID)
    else:
        albums = call("photos.getAlbums", user, owner_id=-vk.GROUP_ID, count=100)
        album = next((a for a in albums.get("items", []) if a.get("title") == "BetBot · публикации"), None)
        if not album:
            album = call("photos.createAlbum", user, group_id=vk.GROUP_ID,
                         title="BetBot · публикации", upload_by_admins_only=1)
        album_id = int(album["id"])
        server = call("photos.getUploadServer", user, group_id=vk.GROUP_ID, album_id=album_id)
    is_png = image.startswith(b"\x89PNG")
    response = requests.post(server["upload_url"],
                             files={"photo" if mode == "wall" else "file1":
                                    ("betbot.png" if is_png else "betbot.jpg", image,
                                     "image/png" if is_png else "image/jpeg")},
                             timeout=60)
    response.raise_for_status()
    uploaded = response.json()
    photo_data = uploaded.get("photo" if mode == "wall" else "photos_list")
    if not photo_data or photo_data == "[]":
        raise RuntimeError("Сервер загрузки не вернул фотографию")
    params = dict(group_id=vk.GROUP_ID, server=uploaded["server"], hash=uploaded["hash"])
    if mode == "wall":
        saved = call("photos.saveWallPhoto", user, photo=photo_data, **params)
    else:
        saved = call("photos.save", user, album_id=album_id, photos_list=photo_data, **params)
    photo = saved[0]
    attachment = f"photo{photo['owner_id']}_{photo['id']}"
    if photo.get("access_key"):
        attachment += "_" + photo["access_key"]
    print("NEW_IMAGE_SAVED: true", flush=True)
    created = call("wall.post", group or user, owner_id=-vk.GROUP_ID, from_group=1,
                   message=f"Тест новой картинки BetBot · {mode} · {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
                   attachments=attachment)
    post_id = int(created["post_id"])
    print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{post_id}", flush=True)
    result = call("wall.getById", reader, posts=f"-{vk.GROUP_ID}_{post_id}")
    items = result.get("items", []) if isinstance(result, dict) else result
    has_photo = bool(items) and any(a.get("type") == "photo" for a in items[0].get("attachments", []))
    print("PHOTO_VERIFIED:", has_photo, flush=True)
    if not has_photo:
        raise RuntimeError("VK не вернул фото-вложение; пост не подтверждён")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        status = error.response.status_code if error.response is not None else "нет ответа"
        raise SystemExit(f"Ошибка транспорта: {type(error).__name__}, HTTP {status}; URL и ключи скрыты") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise SystemExit("Неожиданный формат ответа VK; содержимое скрыто") from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
