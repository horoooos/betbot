"""Канал-«фильтр» для Дзена: @aistavvit_dzen.

Бот копирует новости, статистику, расписания и старты матчей, экспрессы и общие итоги.
Одиночные прогнозы, разборы, голы, live-обновления и повторы исключены.
Суточного лимита нет. Дзен (@zen_sync_bot) забирает посты уже из этого канала.
Копия — через copyMessage: картинка/видео и подпись как в оригинале, без пометки «переслано».
"""
from __future__ import annotations

import json
import os
import re
import hashlib
import time
from datetime import datetime, timezone
from html import unescape
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
    if "LIVE-прогноз" in text:                        # итог live не копируем отдельно — идёт вместе с матчем
        return None
    if "ГОЛ" in text.split("\n")[0] or "#live" in text:
        return None                                   # голы и прочий live — нет
    if "#итог" in text and "ИТОГИ" not in text:       # итог матча, но не «итоги недели/месяца»
        return "итог"
    if any(t in text for t in NEWS_TAGS):
        return "новость"
    return None


def delivery_kind(html: str) -> str | None:
    """Editorial selection for the mirror; independent of image/hashtag kind()."""
    text = unescape(re.sub(r"<[^>]+>", " ", html or ""))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    head = re.sub(r"^[^\wА-Яа-яЁё]+", "", lines[0]).upper()
    if head.startswith(("ПРОДОЛЖЕНИЕ", "ПОЛНЫЙ РАЗБОР", "ПРОГНОЗ", "LIVE", "ИТОГ ·")) or re.match(r"^(ГОЛ|ШАЙБА|КАРТА)(?:\W|$)", head):
        return None
    if head.startswith("СТАТИСТИКА БОТА"):
        return "статистика"
    if head.startswith(("ИТОГИ ДНЯ", "ИТОГИ НЕДЕЛИ", "ИТОГИ МЕСЯЦА")):
        return "сводка"
    if head.startswith("ЭКСПРЕСС"):
        if re.search(r"\d+\s+ИЗ\s+\d+|ПРОМЕЖУТОЧ|УЖЕ ЗАШЛ", head):
            return None
        return "экспресс"
    if head.startswith("МАТЧ НАЧАЛСЯ"):
        return "начало"
    if "#live" in text.lower() or "LIVE-ПРОГНОЗ" in text.upper():
        return None
    if head.startswith(("МАТЧ ДНЯ", "МАТЧИ ДНЯ")):
        return "матчи"
    if "#итог" in text.lower():
        return None
    if any(tag in text.lower() for tag in NEWS_TAGS):
        return "новость"
    return None


def _delivery_key(html: str, k: str, day: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", html or ""))
    lines = [line.strip().lower() for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else ""
    if k == "начало":
        title = next((line for line in lines if " — " in line), title)
    title = re.sub(r"[^\wа-яё]+", " ", title).strip()
    return f"{day}:{k}:" + hashlib.sha256(title.encode()).hexdigest()[:24]


def _remember(state: dict, source_id, key: str, result=None, k=None) -> None:
    for name, value in (("dz_sent_ids", str(source_id) if source_id else None), ("dz_sent_keys", key)):
        items = state.setdefault(name, [])
        if value and value not in items:
            items.append(value)
        del items[:-1500]
    state["dz_err"] = None
    if isinstance(result, dict) and result.get("message_id"):
        state["dz_last_delivery"] = {"source_id": source_id, "message_id": result["message_id"], "kind": k}


def _seen(state: dict, source_id, key: str) -> bool:
    return str(source_id) in state.get("dz_sent_ids", []) or key in state.get("dz_sent_keys", [])


def _match_text(html: str) -> str:
    from .postimg import plain
    text = plain(html)
    lines = [line for line in text.splitlines() if not re.search(
        r"прогноз|ставк|кэф|коэф|букмекер|% банка|#live", line, re.I)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def post_news(png: bytes, caption: str, source_id: int | None = None, *, state: dict | None = None) -> None:
    """Новость — в канал для Дзена сразу картинкой (видео @zen_sync_bot не берёт, пост в Дзене был бы пустым)."""
    if not os.environ.get("TELEGRAM_TOKEN"):
        return
    if delivery_kind(caption) != "новость":
        return
    state = state if state is not None else {}
    key = _delivery_key(caption, "новость", datetime.now(timezone.utc).date().isoformat())
    if _seen(state, source_id, key):
        return
    cap = caption.replace("👇 Продолжение — в ответе", "📖 Полностью — в Telegram-канале @aistavvit")
    tags = hashtags(caption, "новость", limit=10)
    if len(cap) + len(tags) + 2 <= 1024:   # хештеги по теме (команды, игроки, лига) — в конец подписи
        cap += "\n" + tags
    result = telegram._call("sendPhoto", chat_id=TARGET, files={"photo": ("news.png", png, "image/png")}, caption=cap[:1024], parse_mode="HTML")
    _remember(state, source_id, key, result, "новость")


SPORT_TAG = (("⚽", "#футбол"), ("🏒", "#хоккей"), ("🏀", "#баскетбол"), ("🎾", "#теннис"), ("🎮", "#киберспорт"))
KIND_TAGS = {"разбор": ["#прогноз", "#прогнознаматч", "#ставкинаспорт", "#аналитика"],
             "начало": ["#онлайн", "#трансляция", "#прямойэфир", "#прогноз"],
             "итог": ["#итоги", "#результат", "#прогноз", "#ставкинаспорт"],
             "новость": ["#новостиспорта", "#спорт", "#главное"]}
LEAGUE_WORDS = ("NHL", "NBA", "WNBA", "ATP", "WTA", "КХЛ", "РПЛ", "АПЛ", "CS2", "Dota", "Премьер-лига", "Ла Лига",
                "Серия A", "Бундеслига", "Лига 1", "Лига чемпионов", "Лига Европы", "Лига конференций", "Лига наций",
                "Чемпионшип", "Эредивизи", "Суперлига", "MLS", "Евролига")


def _tag(words: str) -> str:
    """«Динамо Махачкала» → #ДинамоМахачкала, «Сан-Хосе» → #СанХосе."""
    parts = re.findall(r"[\wА-Яа-яЁё]+", words)
    return "#" + "".join(p[:1].upper() + p[1:] for p in parts) if parts else ""


def hashtags(html: str, k: str | None, limit: int = 12) -> str:
    """Хештеги по теме поста для Дзена и соцсетей: команды и игроки из текста, лига, вид спорта, рубрика."""
    from . import photos
    text = re.sub(r"<[^>]+>", " ", html or "")
    have = {t.lower() for t in re.findall(r"#[\wА-Яа-яЁё]+", text)}
    out: list[str] = []
    for emo, t in SPORT_TAG:
        if emo in text:
            out.append(t)
            break
    for w in LEAGUE_WORDS:
        if w in text:
            out.append(_tag(w))
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()][:4]
    pairs = 0
    for ln in lines:   # «Спартак — Зенит» → #Спартак #Зенит (без заголовка поста вроде «МАТЧ НАЧАЛСЯ»)
        ln = re.sub(r"^[^\wА-Яа-яЁё]*(?:[А-ЯЁA-Z]{2,}[:\s]+)*", "", ln)
        m = re.match(r"([А-ЯЁA-Z][^—·🏆]{1,40}?)\s+(?:—|\d+:\d+)\s+([А-ЯЁA-Z][^—·🏆(]{1,40})", ln)
        if m and pairs < 2:
            out += [_tag(x.strip()) for x in m.groups()]
            pairs += 1
    if not pairs:   # новость: герои из заголовка — люди «Имя Фамилия» и клубы
        out += [_tag(n) for n in photos.names(lines[0] if lines else "", singles=False)[:3]]
    out += KIND_TAGS.get(k or "", []) + ["#аиставит"]
    seen, res = set(), []
    for t in out:
        if t and len(t) > 2 and len(t) <= 30 and t.lower() not in seen and t.lower() not in have:
            seen.add(t.lower())
            res.append(t)
    return " ".join(res[:limit])


def _caption(text: str, tags: str, tail: str = "") -> str:
    """Подпись до 1024 символов: текст (обрезаем по строке), хвост и хештеги в конце."""
    end = (tail + ("\n\n" + tags if tags else ""))
    if len(text) + len(end) > 1024:
        cut = text[:1024 - len(end) - 2]
        text = (cut[:cut.rfind("\n")] if "\n" in cut[200:] else cut) + "…"
    return text + end


def crosspost(state: dict, checkpoint=None) -> int:
    if not CHANNEL.exists() or not os.environ.get("TELEGRAM_TOKEN"):
        return 0
    posts = json.loads(CHANNEL.read_text(encoding="utf-8")).get("posts", {})
    if not posts:
        return 0
    checkpoint = checkpoint or (lambda: None)
    newest = max(int(k) for k in posts)
    if "dz_last" not in state:                        # первый запуск: начинаем с новых постов, старое не переносим
        state["dz_last"] = newest
        print(f"  Дзен-канал: копирование включено, начинаем после поста {newest}")
        return 0
    done = 0
    for pid in sorted(int(k) for k in posts if int(k) > state["dz_last"])[:MAX_PER_PASS * 30]:
        post = posts[str(pid)]
        html = post.get("html", "")
        k = delivery_kind(html)
        try:
            posted_at = datetime.fromisoformat(post.get("t", "").replace("Z", "+00:00"))
            age = time.time() - posted_at.timestamp()
            day = posted_at.astimezone(timezone.utc).date().isoformat()
        except (ValueError, TypeError):
            age, day = float("inf"), "unknown"
        max_age = 1200 if k == "начало" else 86400 if k in {"статистика", "сводка", "матчи"} else 21600
        key = _delivery_key(html, k or "skip", day)
        if k and 0 <= age <= max_age and not _seen(state, pid, key):
            try:
                from . import postimg
                text = _match_text(html) if k in {"начало", "матчи"} else postimg.plain(html).strip()
                if k == "статистика":
                    tail = posts.get(str(pid + 1), {}).get("html", "")
                    if postimg.plain(tail).strip().startswith("Вчера,"):
                        text += "\n\n" + postimg.plain(tail).strip()
                tags = "#спорт #матчи #аиставит" if k in {"начало", "матчи"} else hashtags(html, k)
                cap = _caption(text, tags, f"\n\n📖 Полностью: t.me/aistavvit/{pid}")
                if post.get("photo") and k != "начало":
                    result = telegram._call("copyMessage", chat_id=TARGET, from_chat_id=os.environ["TELEGRAM_CHAT_ID"], message_id=pid,
                                   caption=cap)
                else:
                    # Start cards are redrawn from sanitized text so the original
                    # forecast cannot remain embedded in the copied image.
                    img = postimg._card(text, "начало") if k == "начало" else postimg.image_for(post, k, posts)
                    if not img:
                        raise RuntimeError("Картинка публикации не получена")
                    result = telegram._call("sendPhoto", chat_id=TARGET, files={"photo": ("post.png", img, "image/png")}, caption=cap)
                _remember(state, pid, key, result, k)
                done += 1
            except Exception as e:
                print(f"  ! Дзен-канал: пост {pid} не скопирован (бот — админ в {TARGET}?): {e}")
                state["dz_err"] = f"{pid}: {e}"[:300]
                break                                 # попробуем в следующий проход
        state["dz_last"] = pid
        checkpoint()
        if done >= MAX_PER_PASS:
            break
    if done:
        print(f"  Дзен-канал: скопировано постов: {done}")
    return done
