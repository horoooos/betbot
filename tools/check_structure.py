"""Проверка структуры проекта betbot перед любыми изменениями.

Запуск из корня проекта:
    python tools/check_structure.py

Показывает: ветку и состояние git, дерево, модули, workflow, данные, свежесть
и компиляцию всех модулей. Код возврата 1 — есть жёсткая проблема.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSK = timezone(timedelta(hours=3))
problems: list[str] = []


def head(title: str) -> None:
    print(f"\n=== {title} ===")


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:                              # noqa: BLE001
        return f"(git недоступен: {exc})"


def structure() -> None:
    head("Структура")
    skip = {".git"}
    for p in sorted(ROOT.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if p.name in skip:
            continue
        if p.is_dir():
            files = sum(1 for _ in p.rglob("*") if _.is_file())
            print(f"  {p.name + '/':24} каталог, файлов: {files}")
        else:
            print(f"  {p.name:24} {p.stat().st_size:>9} байт")

    mods = sorted((ROOT / "betbot").glob("*.py"))
    print(f"\n  модулей betbot/: {len(mods)}")
    wf = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    print(f"  workflow: {', '.join(w.name for w in wf)}")
    docs = sum(1 for _ in (ROOT / "docs").rglob("*") if _.is_file()) if (ROOT / "docs").exists() else 0
    print(f"  docs/: {docs} файлов")
    data = sum(1 for _ in (ROOT / "data").glob("*") if _.is_file())
    print(f"  data/: {data} файлов")


def required() -> None:
    head("Обязательные файлы")
    must = ["run.py", "requirements.txt", "README.md", "RULES.md",
            ".github/workflows/daily.yml", ".github/workflows/pages.yml",
            "docs/index.html", "data/results.csv", "data/state.json", "betbot/card.py", "betbot/inplay.py"]
    for name in must:
        p = ROOT / name
        if p.exists():
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name} — НЕТ")
            problems.append(f"нет файла {name}")


def compile_all() -> None:
    head("Компиляция")
    r = subprocess.run([sys.executable, "-m", "compileall", "-q", str(ROOT / "betbot"), str(ROOT / "run.py")],
                       capture_output=True, text=True, timeout=180)
    if r.returncode == 0:
        print("  ✓ все модули компилируются")
    else:
        print("  ✗ ошибки компиляции:")
        print((r.stdout + r.stderr)[-1500:])
        problems.append("ошибка компиляции")


def freshness() -> None:
    head("Свежесть данных")
    now = datetime.now(MSK)
    try:
        st = json.loads((ROOT / "data" / "state.json").read_text(encoding="utf-8"))
        print(f"  learned: {st.get('learned')} | vk_last: {st.get('vk_last')} | weights: {st.get('weights')}")
        print(f"  push: {st.get('push')} | shorts_day: {st.get('shorts_day')} | site_stamp: {st.get('site_stamp')}")
    except Exception as exc:                              # noqa: BLE001
        problems.append(f"state.json не читается: {exc}")
        print(f"  ✗ state.json: {exc}")
    try:
        import pandas as pd
        res = pd.read_csv(ROOT / "data" / "results.csv", dtype={"main_key": str})
        last = pd.to_datetime(res["date"]).max()
        hit = res["main_hit"].astype(str).str.lower().isin(["true", "1", "1.0"]).mean()
        print(f"  results.csv: {len(res)} строк, последняя {last.date()}, основной заход {hit * 100:.1f}%")
        if (now.date() - last.date()).days > 2:
            print(f"  ⚠ результаты не обновлялись {(now.date() - last.date()).days} дн.")
    except Exception as exc:                              # noqa: BLE001
        print(f"  ✗ results.csv: {exc}")
        problems.append("results.csv не читается")
    try:
        ch = json.loads((ROOT / "data" / "channel.json").read_text(encoding="utf-8"))["posts"]
        mx = max(int(k) for k in ch)
        ts = max(v["t"] for v in ch.values() if v.get("t"))
        age = now - datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(MSK)
        print(f"  channel.json: {len(ch)} постов, последний #{mx} в {ts} ({age.total_seconds() / 3600:.1f} ч назад)")
        if age.total_seconds() > 6 * 3600:
            print("  ⚠ в канале давно не было постов")
    except Exception as exc:                              # noqa: BLE001
        print(f"  ✗ channel.json: {exc}")
    for name in ("live_bets.csv", "express_bets.csv"):
        p = ROOT / "data" / name
        rows = max(0, len(p.read_text(encoding="utf-8").splitlines()) - 1) if p.exists() else -1
        print(f"  {name}: {'нет' if rows < 0 else f'{rows} записей'}")


def state_git() -> None:
    head("Git")
    print("  ветка:", git("rev-parse", "--abbrev-ref", "HEAD"))
    st = git("status", "--short")
    dirty = [line for line in st.splitlines() if line.strip()]
    print(f"  изменённых файлов: {len(dirty)}")
    for line in dirty[:10]:
        print("   ", line)
    if dirty:
        problems.append(f"незакоммиченных файлов: {len(dirty)}")
    print("  последний коммит:", git("log", "-1", "--format=%h %s"))


def main() -> int:
    print(f"Проверка структуры betbot · {datetime.now(MSK):%d.%m.%Y %H:%M} МСК")
    print(f"Путь: {ROOT}")
    state_git()
    structure()
    required()
    compile_all()
    freshness()
    head("Итог")
    if problems:
        print("  ✗ проблемы:")
        for p in problems:
            print("   -", p)
        return 1
    print("  ✓ структура в порядке")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
