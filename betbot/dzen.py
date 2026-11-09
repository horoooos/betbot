"""Канал-«фильтр» для Дзена: @aistavvit_dzen.

Бот копирует туда из основного канала только то, что нужно в Дзене: полные разборы матчей,
«Матч начался», новости и итоги матчей. Дзен (@zen_sync_bot) забирает посты уже из этого канала.
Копия — через copyMessage: картинка/видео и подпись как в оригинале, без пометки «переслано».
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import telegram

TARGET = "@aistavvit_dzen"
CHANNEL = Path(__file__).resolve().parent.parent / "data" / "channel.json"
MAX_PER_PASS = 10
NEWS_TAGS = ("#футбол", "#хоккей", "#баскетбол", "#теннис", "#киберспорт")


def kind(html: str) -> str | None:
    """Что это за пост: 'разбор' / 'начало' / 'итог' / 'новость' — или None (в Дзен не идёт)."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    if "ПОЛНЫЙ РАЗБОР" in text:
        return "разбор"
    if "МАТЧ НАЧАЛСЯ" in text:
        return "начало"
    if "ГОЛ" in text.split("\n")[0] or "#live" in text:
        return None                                   # голы и прочий live — нет
    if "#итог" in text and "ИТОГИ" not in text:       # итог матча, но не «итоги недели/месяца»
        return "итог"
    if any(t in text for t in NEWS_TAGS):
        return "новость"
    return None


def post_news(png: bytes, caption: str, source_id: int | None = None) -> None:
    """Новость — в канал для Дзена сразу картинкой (видео @zen_sync_bot не берёт, пост в Дзене был бы пустым)."""
    if not os.environ.get("TELEGRAM_TOKEN"):
        return
    cap = caption.replace("👇 Продолжение — в ответе", "📖 Полностью — в Telegram-канале @aistavvit")
    telegram._call("sendPhoto", chat_id=TARGET, files={"photo": ("news.png", png, "image/png")}, caption=cap[:1024], parse_mode="HTML")


def crosspost(state: dict) -> int:
    if not CHANNEL.exists() or not os.environ.get("TELEGRAM_TOKEN"):
        return 0
    posts = json.loads(CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    newest = max(int(k) for k in posts)
    if "dz_last" not in state:                        # первый запуск: начинаем с новых постов, старое не переносим
        state["dz_last"] = newest
        print(f"  Дзен-канал: копирование включено, начинаем после поста {newest}")
        return 0
    done = 0
    for pid in sorted(int(k) for k in posts if int(k) > state["dz_last"])[:MAX_PER_PASS]:
        k = kind(posts[str(pid)].get("html", ""))
        if k and k != "новость":                      # новости news.py отправляет сам — картинкой (см. post_news)
            try:
                telegram._call("copyMessage", chat_id=TARGET, from_chat_id=os.environ["TELEGRAM_CHAT_ID"], message_id=pid)
                done += 1
            except Exception as e:
                print(f"  ! Дзен-канал: пост {pid} не скопирован (бот — админ в {TARGET}?): {e}")
                state["dz_err"] = f"{pid}: {e}"[:300]
                break                                 # попробуем в следующий проход
        state["dz_last"] = pid
    if done:
        print(f"  Дзен-канал: скопировано постов: {done}")
    return done
