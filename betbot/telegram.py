"""Отправка сообщений и картинок через Telegram Bot API (бесплатно)."""
import os
import time
from pathlib import Path

import requests

LIMIT = 4000         # лимит текста сообщения — 4096
CAPTION_LIMIT = 1024  # лимит подписи к картинке
DRY = not (os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
PREVIEW = Path(__file__).resolve().parent.parent / "data" / "preview"  # куда пишем посты в тестовом режиме
_fake_id = 0


def _call(method: str, files=None, **params) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/{method}"
    params.setdefault("chat_id", os.environ["TELEGRAM_CHAT_ID"])
    data = {}
    for _ in range(5):
        r = requests.post(url, data=params, files=files, timeout=60)
        data = r.json()
        if r.status_code == 429:  # слишком часто — Telegram говорит, сколько подождать
            time.sleep(data.get("parameters", {}).get("retry_after", 5) + 1)
            continue
        break
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    time.sleep(3)  # не больше ~20 сообщений в минуту в один канал
    return data["result"]


def _chunks(text: str) -> list[str]:
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > LIMIT and cur:
            parts.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + block
    if cur:
        parts.append(cur)
    return parts


def _dry(kind: str, text: str, png: bytes | None = None) -> int:
    global _fake_id
    _fake_id += 1
    PREVIEW.mkdir(parents=True, exist_ok=True)
    if png:
        (PREVIEW / f"{_fake_id:03d}.png").write_bytes(png)
    (PREVIEW / f"{_fake_id:03d}_{kind}.txt").write_text(text, encoding="utf-8")
    print(f"[тест] {kind} #{_fake_id}: {text.splitlines()[0][:80] if text else ''}")
    return _fake_id


def send(text: str, reply_to: int | None = None, silent: bool = False) -> list[int]:
    """Отправляет текст (длинный режется на части). Возвращает id сообщений."""
    ids = []
    for part in _chunks(text):
        if DRY:
            ids.append(_dry("text", part))
            continue
        params = {"text": part, "parse_mode": "HTML", "disable_web_page_preview": True,
                  "disable_notification": silent}
        if reply_to:
            params["reply_to_message_id"] = reply_to
            params["allow_sending_without_reply"] = True
        ids.append(_call("sendMessage", **params)["message_id"])
    return ids


def send_photo(png: bytes, caption: str, reply_to: int | None = None) -> int:
    caption = caption[:CAPTION_LIMIT]
    if DRY:
        return _dry("photo", caption, png)
    params = {"caption": caption, "parse_mode": "HTML"}
    if reply_to:
        params["reply_to_message_id"] = reply_to
        params["allow_sending_without_reply"] = True
    return _call("sendPhoto", files={"photo": ("match.png", png, "image/png")}, **params)["message_id"]
