"""Отправка, редактирование и закрепление сообщений через Telegram Bot API (бесплатно)."""
import os
import time

import requests

LIMIT = 4000  # у Telegram лимит 4096 символов на сообщение
DRY = not (os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
_fake_id = 0


def _call(method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/{method}"
    params.setdefault("chat_id", os.environ["TELEGRAM_CHAT_ID"])
    for _ in range(5):
        r = requests.post(url, data=params, timeout=30)
        data = r.json()
        if r.status_code == 429:  # слишком часто — Telegram говорит, сколько подождать
            time.sleep(data.get("parameters", {}).get("retry_after", 5) + 1)
            continue
        return data
    return data


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


def send(text: str, silent: bool = False) -> list[int]:
    """Отправляет сообщение (длинное режется на части). Возвращает id сообщений."""
    global _fake_id
    ids = []
    for part in _chunks(text):
        if DRY:
            print("\n────────── [пост в Telegram] ──────────\n" + part)
            _fake_id += 1
            ids.append(_fake_id)
            continue
        data = _call("sendMessage", text=part, parse_mode="HTML", disable_web_page_preview=True,
                     disable_notification=silent)
        if not data.get("ok"):
            raise RuntimeError(f"Telegram: {data}")
        ids.append(data["result"]["message_id"])
        time.sleep(3)  # не больше ~20 сообщений в минуту в один канал
    return ids


def edit(message_id: int, text: str) -> bool:
    """Обновляет уже отправленное сообщение. False — если его больше нет (удалили)."""
    if DRY:
        print(f"\n────────── [обновление поста #{message_id}] ──────────\n" + text[:LIMIT])
        return True
    data = _call("editMessageText", message_id=message_id, text=text[:LIMIT], parse_mode="HTML",
                 disable_web_page_preview=True)
    return data.get("ok") or "not modified" in data.get("description", "")


def pin(message_id: int) -> None:
    if not DRY:
        _call("pinChatMessage", message_id=message_id, disable_notification=True)
