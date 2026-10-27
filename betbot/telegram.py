"""Отправка сообщений в Telegram через Bot API (бесплатно)."""
import os

import requests

LIMIT = 4000  # у Telegram лимит 4096 символов на сообщение


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


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM_TOKEN/TELEGRAM_CHAT_ID не заданы — вывожу сообщение в консоль]\n")
        print(text)
        return
    for part in _chunks(text):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": part, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=30,
        )
        r.raise_for_status()
