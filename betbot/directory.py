"""Справочник для страниц команд, игроков и турниров на сайте.

docs/dir.json     — русские названия команд и теннисистов, таблица транслитерации, все турниры бота.
docs/teamids.json — «вид спорта|русское название» → путь и id на ESPN (чтобы со старых страниц
                    команд и из прогнозов можно было открыть живую страницу с расписанием и составом).
Данные о самих командах и игроках сайт берёт прямо у ESPN, поэтому файлы меняются редко.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import leagues, names, sports

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
IDS = ROOT / "data" / "teamids.json"
DOMESTIC = {f"soccer/{v[3]}" for v in [*leagues.MAIN.values(), *leagues.EXTRA.values()]}


def _write(path: Path, data) -> bool:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _leagues() -> list[dict]:
    out = []
    for code, (flag, country, name, slug) in leagues.ALL.items():
        out.append({"p": f"soccer/{slug}", "n": name, "c": country, "f": flag, "s": "football",
                    "nat": code in leagues.NATIONAL})
    for code, (flag, country, name, path, sport) in sports.LEAGUES.items():
        if path:
            out.append({"p": path, "n": name, "c": "США" if sport != "tennis" else "Теннис", "f": flag, "s": sport})
    return out


def export(events: list[dict]) -> None:
    cache = names._load()
    teams, players = {}, {}
    for k, v in cache.items():
        if k.startswith("tennis:"):
            players[k[7:]] = v
        elif k.startswith("national:"):
            if not v.startswith("Сборная "):   # «Сборная Norway» — перевода нет, оставляем латиницу
                teams.setdefault(k[9:], v)
        else:
            teams[k] = v
    teams.update(names.FIXED)
    changed = _write(DOCS / "dir.json", {"teams": teams, "players": players, "tr": names._TR, "leagues": _leagues()})

    ids = json.loads(IDS.read_text(encoding="utf-8")) if IDS.exists() else {}
    for e in events:
        sport = e.get("sport", "football")
        if sport == "esports":
            continue
        if sport == "football":
            slug = (leagues.ALL.get(e.get("div")) or (None,) * 4)[3]
            path = f"soccer/{slug}" if slug else None
        else:
            path = (sports.LEAGUES.get(e.get("div")) or (None,) * 5)[3]
        if not path:
            continue
        for side in ("home", "away"):
            t = e.get(side) or {}
            if t.get("ru") and t.get("id"):
                key = f"{sport}|{t['ru']}"
                old = ids.get(key)
                # для клуба запоминаем чемпионат, а не кубок/еврокубок: так точнее состав и таблица
                if old and old[1] == str(t["id"]) and "." in old[0] and path.split("/")[1].count(".") and \
                        not path.endswith(".1") and old[0].endswith(".1"):
                    continue
                ids[key] = [path, str(t["id"]), t.get("name", "")]
    IDS.write_text(json.dumps(ids, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    if _write(DOCS / "teamids.json", ids) or changed:
        print(f"Справочник команд для сайта обновлён: {len(ids)} команд и игроков")


def team_link(sport: str, ru: str, prefix: str = "") -> str | None:
    """Ссылка на живую страницу команды/теннисиста, если знаем их id на ESPN."""
    ids = json.loads(IDS.read_text(encoding="utf-8")) if IDS.exists() else {}
    x = ids.get(f"{sport}|{ru}")
    if not x:
        return None
    page = "player.html" if sport == "tennis" else "team.html"
    return f"{prefix}{page}?p={x[0]}&id={x[1]}"
