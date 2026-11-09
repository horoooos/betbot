"""Картинка для любого поста канала — для ВК и Дзена, где пост без картинки выглядит пусто.

Есть своя картинка у поста (прогноз, итог, новость) — берём её. Нет (полный разбор, «матч начался»,
текстовый итог) — рисуем фирменную карточку: рубрика, крупно матч, ниже турнир/результат.
"""
from __future__ import annotations

import re
from html import unescape

import requests

from . import card

# цвета фона по рубрике: (слева, справа)
COLORS = {"разбор": ((40, 60, 160), (120, 50, 170)), "итог": ((20, 120, 80), (30, 60, 140)),
          "начало": ((170, 30, 50), (60, 30, 120)), "новость": ((30, 80, 170), (20, 30, 90))}
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF☀-➿⬀-⯿️‍]")


def plain(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "")
    t = re.sub(r"<[^>]+>", "", t)
    return unescape(t)


def _clean(line: str) -> str:
    """Без эмодзи и лишних знаков — шрифт карточки их не рисует."""
    t = EMOJI_RE.sub("", line)
    t = re.sub(r"[✓✗✅❌·]+\s*$", "", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ·:-—")


def _lines(html: str) -> list[str]:
    return [x for x in (_clean(l) for l in plain(html).split("\n")) if x and not x.startswith("#")]


def _card(html: str, kind: str) -> bytes:
    ls = _lines(html)
    first = ls[0] if ls else "АИ СТАВИТ"
    if kind == "разбор":
        big = first.split(":", 1)[-1].strip() if ":" in first else first
        kicker, sub, rest = "Полный разбор матча", (ls[1] if len(ls) > 1 else ""), ls[2:5]
    elif kind == "начало":
        kicker, big, sub, rest = "Матч начался", (ls[1] if len(ls) > 1 else first), (ls[2] if len(ls) > 2 else ""), ["Смотрите онлайн на сайте АИ СТАВИТ"]
    elif kind == "итог":
        res = "Прогноз зашёл" if "ЗАШЛО" in html else "Прогноз не зашёл" if "МИМО" in html else ""
        kicker, big = "Итог матча", (ls[1] if len(ls) > 1 else first)
        sub = " · ".join(x for x in (first.replace("ИТОГ", "").strip(" ·"), res) if x)
        rest = ls[2:5]
    else:
        kicker, big, sub, rest = "Новости спорта", first, "", ls[1:3]
    big = big if len(big) <= 60 else big[:57] + "…"
    rest = [r if len(r) <= 70 else r[:67] + "…" for r in rest]
    return card.slide_card(kicker, big, sub, rest, COLORS.get(kind, COLORS["новость"]), brand="@aistavvit")


def image_for(post: dict, kind: str) -> bytes | None:
    """Картинка поста: своя (скачиваем) или нарисованная карточка."""
    if post.get("photo"):
        try:
            r = requests.get(post["photo"], timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and len(r.content) > 5000:
                return r.content
        except Exception:
            pass
    try:
        return _card(post.get("html", ""), kind)
    except Exception as e:
        print(f"  ! картинка поста не нарисовалась: {e}")
        return None
