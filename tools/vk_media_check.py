"""Controlled VK media diagnostics. Never print tokens or signed upload URLs."""
from __future__ import annotations

import json
import os
import re
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


def public_photo_reference(value):
    if not re.fullmatch(r"photo-?[1-9]\d*_[1-9]\d*", value):
        raise RuntimeError("Нужен публичный ID фотографии без адреса файла и ключей доступа")
    return value


def resolve_recipient(token, value):
    value = value.strip()
    if "://" in value or value.startswith(("vk.com/", "vk.ru/", "m.vk.com/", "m.vk.ru/")):
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.hostname not in {"vk.com", "vk.ru", "m.vk.com", "m.vk.ru"}:
            raise RuntimeError("Для получателя нужна ссылка на профиль VK")
        value = parsed.path.strip("/")
    if value.startswith("id") and value[2:].isdigit():
        value = value[2:]
    if value.isdigit() and int(value) > 0:
        return int(value)
    if not value or "/" in value:
        raise RuntimeError("Укажите профиль пользователя для загрузки GIF")
    resolved = call("utils.resolveScreenName", token, screen_name=value)
    if not isinstance(resolved, dict) or resolved.get("type") != "user" or not resolved.get("object_id"):
        raise RuntimeError("Получатель должен быть пользователем VK")
    return int(resolved["object_id"])


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
    if mode == "event-photo":
        from betbot.vk_wall_events import PhotoMonitor
        attachment = public_photo_reference(os.environ.get("VK_PUBLIC_PHOTO_REFERENCE", "").strip())
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        monitor = PhotoMonitor(group)
        monitor.start()
        print("WALL_EVENT_MONITOR_READY: true", flush=True)
        created = call("wall.post", group, owner_id=-vk.GROUP_ID, from_group=1,
                       message="Тест BetBot: проверка картинки через события сообщества.",
                       attachments=attachment, guid="betbot-event-photo-" + attachment)
        post_id = int(created["post_id"])
        print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{post_id}", flush=True)
        has_photo = monitor.verify(post_id)
        print("WALL_EVENT_PHOTO_VERIFIED:", has_photo, flush=True)
        if not has_photo:
            raise RuntimeError("Событие VK не содержит фото-вложения")
        short = vk._short(vk.SITE)
        comment = call("wall.createComment", group, owner_id=-vk.GROUP_ID, post_id=post_id,
                       from_group=1, message="🔗 Сайт проекта: " + short, guid="betbot-event-site-" + str(post_id))
        print("SHORT_LINK_COMMENT_CREATED:", bool(comment.get("comment_id")), flush=True)
        return
    if mode in {"existing-photo", "keyed-photo"}:
        if mode == "keyed-photo":
            attachment = os.environ.get("VK_TEST_PHOTO_ATTACHMENT", "").strip()
            if not re.fullmatch(r"photo-?[1-9]\d*_[1-9]\d*_[A-Za-z0-9]+", attachment):
                raise RuntimeError("В защищённом секрете нет полного вложения фотографии")
        else:
            attachment = public_photo_reference(os.environ.get("VK_PUBLIC_PHOTO_REFERENCE", "").strip())
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        created = call("wall.post", group, owner_id=-vk.GROUP_ID, from_group=1,
                       message="Тест BetBot: прикрепление публичной фотографии из обычного поста.",
                       attachments=attachment, guid="betbot-" + mode + "-" + "_".join(attachment.split("_")[:2]))
        print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{int(created['post_id'])}", flush=True)
        print("WALL_DISPLAY_REQUIRES_VERIFICATION: true", flush=True)
        return
    if mode == "docs-info":
        documents = call("docs.get", group, owner_id=-vk.GROUP_ID, count=10)
        print("GROUP_DOCUMENT_COUNT:", documents.get("count"), flush=True)
        for document in documents.get("items", []):
            print("DOCUMENT_METADATA:", {"id": document.get("id"), "owner_id": document.get("owner_id"),
                  "ext": document.get("ext"), "type": document.get("type"),
                  "preview_types": list((document.get("preview") or {}).keys())}, flush=True)
        return
    if mode == "graffiti-wall":
        from PIL import Image
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        server = call("docs.getMessagesUploadServer", group, type="graffiti", peer_id=-vk.GROUP_ID)
        print("GRAFFITI_UPLOAD_SERVER_READY: true", flush=True)
        posts = json.loads(Path("data/channel.json").read_text(encoding="utf-8"))["posts"]
        pid = max(posts, key=int)
        image = postimg.image_for(posts[pid], "новость", posts)
        if not image:
            raise RuntimeError("Картинка граффити не создана")
        with Image.open(BytesIO(image)) as source:
            picture = source.convert("RGBA")
            picture.thumbnail((1024, 1024))
            output = BytesIO()
            picture.save(output, "PNG")
        uploaded = requests.post(server["upload_url"],
                                 files={"file": ("betbot.png", output.getvalue(), "image/png")}, timeout=60)
        print("GRAFFITI_UPLOAD_HTTP:", uploaded.status_code, flush=True)
        uploaded.raise_for_status()
        payload = uploaded.json()
        if not payload.get("file"):
            raise RuntimeError("VK не вернул идентификатор загруженного граффити")
        saved = call("docs.save", group, file=payload["file"])
        graffiti = saved.get("graffiti", {})
        if not graffiti.get("owner_id") or not graffiti.get("id"):
            raise RuntimeError("VK не подтвердил сохранение граффити")
        attachment = f"graffiti{graffiti['owner_id']}_{graffiti['id']}"
        if graffiti.get("access_key"):
            attachment += "_" + graffiti["access_key"]
        print("GRAFFITI_SAVED: true", flush=True)
        post = call("wall.post", group, owner_id=-vk.GROUP_ID, from_group=1,
                    message="Тест BetBot: карточка новости как граффити.", attachments=attachment,
                    guid="betbot-graffiti-test-" + os.environ.get("GITHUB_RUN_ID", str(int(time.time()))))
        print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{int(post['post_id'])}", flush=True)
        print("WALL_DISPLAY_REQUIRES_VERIFICATION: true", flush=True)
        return
    if mode in {"gif-wall", "gif-message-wall"}:
        from betbot import vk_gif
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        peer_id = None
        if mode == "gif-message-wall":
            peer_id = resolve_recipient(group, os.environ.get("VK_DOC_TEST_RECIPIENT", ""))
            allowed = call("messages.isMessagesFromGroupAllowed", group, group_id=vk.GROUP_ID, user_id=peer_id)
            if not allowed.get("is_allowed"):
                raise RuntimeError("Пользователь ещё не разрешил сообщения группы")
            print("RECIPIENT_PERMISSION_CONFIRMED: true", flush=True)
        try:
            server = (call("docs.getMessagesUploadServer", group, type="doc", peer_id=peer_id)
                      if mode == "gif-message-wall" else call("docs.getWallUploadServer", group, group_id=vk.GROUP_ID))
        except RuntimeError as error:
            if ": 15 " not in str(error):
                raise
            permissions = call("groups.getTokenPermissions", group)
            names = {p.get("name") for p in permissions.get("permissions", [])}
            print("GROUP_PERMISSION_NAMES:", sorted(str(n) for n in names), flush=True)
            if not {"docs", "manage"}.issubset(names):
                raise RuntimeError("Ключу группы недостаёт права docs или manage для настройки загрузки GIF") from None
            call("groups.edit", group, group_id=vk.GROUP_ID, docs=2)
            print("DOCUMENT_SECTION_LIMITED_ENABLED: true", flush=True)
            server = call("docs.getWallUploadServer", group, group_id=vk.GROUP_ID)
        print("GIF_UPLOAD_SERVER_READY: true", flush=True)
        posts = json.loads(Path("data/channel.json").read_text(encoding="utf-8"))["posts"]
        pid = max(posts, key=int)
        image = postimg.image_for(posts[pid], "новость", posts)
        if not image:
            raise RuntimeError("Картинка GIF не создана")
        gif = vk_gif.render(image)
        uploaded = requests.post(server["upload_url"], files={"file": ("betbot.gif", gif, "image/gif")}, timeout=60)
        print("GIF_UPLOAD_HTTP:", uploaded.status_code, flush=True)
        uploaded.raise_for_status()
        payload = uploaded.json()
        if not payload.get("file"):
            raise RuntimeError("VK не вернул идентификатор загруженного GIF")
        saved = call("docs.save", group, file=payload["file"], title="BetBot — тест GIF-картинки")
        document = saved.get("doc", {}) if isinstance(saved, dict) else saved[0] if saved else {}
        if document.get("ext", "").lower() != "gif" or not document.get("id") or not document.get("owner_id"):
            raise RuntimeError("VK не подтвердил сохранение GIF-документа")
        attachment = f"doc{document['owner_id']}_{document['id']}"
        if document.get("access_key"):
            attachment += "_" + document["access_key"]
        print("GIF_DOCUMENT_SAVED: true", flush=True)
        print("GIF_HAS_PREVIEW:", bool(document.get("preview")), flush=True)
        post = call("wall.post", group, owner_id=-vk.GROUP_ID, from_group=1,
                    message="Тест BetBot: карточка новости в формате GIF.", attachments=attachment,
                    guid="betbot-gif-test-" + os.environ.get("GITHUB_RUN_ID", str(int(time.time()))))
        post_id = int(post["post_id"])
        print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{post_id}", flush=True)
        print("WALL_DISPLAY_REQUIRES_VERIFICATION: true", flush=True)
        return
    if mode in {"story-to-wall", "story-to-wall-user"}:
        from betbot import vk_stories
        story_id = os.environ.get("VK_STORY_TEST_ID", "").strip()
        if not story_id.isdigit():
            raise RuntimeError("Укажите ID истории цифрами")
        story = vk_stories.verify_story({"owner_id": -vk.GROUP_ID, "id": int(story_id)})
        photo = story["photo"]
        if not photo.get("id") or not photo.get("owner_id"):
            raise RuntimeError("Фото истории не содержит ID для прикрепления")
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        if photo.get("access_key"):
            attachment += "_" + photo["access_key"]
        print("STORY_PHOTO_FOUND: true", flush=True)
        print("PHOTO_OWNER_AND_ID:", photo["owner_id"], photo["id"], flush=True)
        publisher = user if mode == "story-to-wall-user" else group
        if not publisher:
            raise RuntimeError("Отсутствует ключ для выбранного способа публикации")
        created = call("wall.post", publisher, owner_id=-vk.GROUP_ID, from_group=1,
                       message="Тест BetBot: фотография из опубликованной истории.",
                       attachments=attachment, guid="betbot-" + mode + "-" + story_id)
        post_id = int(created["post_id"])
        print("POST_URL:", f"https://vk.com/wall-{vk.GROUP_ID}_{post_id}", flush=True)
        result = call("wall.getById", reader, posts=f"-{vk.GROUP_ID}_{post_id}")
        items = result.get("items", []) if isinstance(result, dict) else result
        photos = [a for a in items[0].get("attachments", []) if a.get("type") == "photo"] if items else []
        print("WALL_PHOTO_VERIFIED:", bool(photos), flush=True)
        if not photos:
            raise RuntimeError("VK создал пост, но не вернул фото истории в его вложениях")
        return
    if mode == "story-test":
        from betbot import vk_stories
        posts = json.loads(Path("data/channel.json").read_text(encoding="utf-8"))["posts"]
        pid = max(posts, key=int)
        image = postimg.image_for(posts[pid], "новость", posts)
        if not image:
            raise RuntimeError("Картинка истории не создана")
        vk_stories.publish_image(image, posts[pid].get("html", ""), test=True)
        return
    if not user:
        raise RuntimeError("VK_USER_TOKEN отсутствует")
    print("API_HOST: api.vk.ru", flush=True)
    print("INDEPENDENT_READ_KEY:", bool(os.environ.get("VK_SERVICE_KEY")), flush=True)
    if mode == "app-info":
        result = call("apps.get", user)
        for app in result.get("items", []):
            print("TOKEN_APPLICATION:", {k: app.get(k) for k in ("id", "title", "type")}, flush=True)
        return
    if mode in {"link-preview", "link-parsed-preview", "link-community-preview"}:
        if not group:
            raise RuntimeError("VK_TOKEN отсутствует")
        parser = group if mode == "link-community-preview" else user if mode == "link-parsed-preview" else None
        link_preview(group, reader, parser)
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
