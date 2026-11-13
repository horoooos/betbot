"""Controlled VK media diagnostics. Never print tokens or signed upload URLs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betbot import postimg, vk


def call(method, token, **params):
    time.sleep(1)
    return vk._call(method, _tok=token, **params)


def main():
    mode = os.environ.get("VK_MEDIA_MODE", "access")
    user = os.environ.get("VK_USER_TOKEN", "").strip()
    group = os.environ.get("VK_TOKEN", "").strip()
    reader = os.environ.get("VK_SERVICE_KEY", "").strip() or user
    if not user:
        raise RuntimeError("VK_USER_TOKEN отсутствует")
    print("API_HOST: api.vk.ru", flush=True)
    print("INDEPENDENT_READ_KEY:", bool(os.environ.get("VK_SERVICE_KEY")), flush=True)
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
    except requests.RequestException:
        raise SystemExit("Ошибка транспорта VK; URL и ключи скрыты") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise SystemExit("Неожиданный формат ответа VK; содержимое скрыто") from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
