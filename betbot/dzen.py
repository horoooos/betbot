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
    if "LIVE-прогноз" in text:                        # итог live не копируем отдельно — идёт вместе с матчем
        return None
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
    tags = hashtags(caption, "новость", limit=10)
    if len(cap) + len(tags) + 2 <= 1024:   # хештеги по теме (команды, игроки, лига) — в конец подписи
        cap += "\n" + tags
    telegram._call("sendPhoto", chat_id=TARGET, files={"photo": ("news.png", png, "image/png")}, caption=cap[:1024], parse_mode="HTML")


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
                post = posts[str(pid)]
                from . import postimg
                text = postimg.plain(post.get("html", "")).strip()
                tags = hashtags(post.get("html", ""), k)   # больше хештегов по теме — Дзен и соцсети лучше продвигают
                if post.get("photo"):   # с картинкой — копия, подпись с хештегами
                    telegram._call("copyMessage", chat_id=TARGET, from_chat_id=os.environ["TELEGRAM_CHAT_ID"], message_id=pid,
                                   caption=_caption(text, tags))
                else:                   # текстовый пост (разбор) — с нашей карточкой, иначе в Дзене он без картинки
                    img = postimg.image_for(post, k, posts)
                    cap = _caption(text, tags, f"\n\n📖 Полностью — в Telegram-канале: t.me/aistavvit/{pid}")
                    telegram._call("sendPhoto", chat_id=TARGET, files={"photo": ("post.png", img, "image/png")}, caption=cap)
                done += 1
            except Exception as e:
                print(f"  ! Дзен-канал: пост {pid} не скопирован (бот — админ в {TARGET}?): {e}")
                state["dz_err"] = f"{pid}: {e}"[:300]
                break                                 # попробуем в следующий проход
        state["dz_last"] = pid
    if done:
        print(f"  Дзен-канал: скопировано постов: {done}")
    return done
