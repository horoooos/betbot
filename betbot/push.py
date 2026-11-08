"""Push-уведомления на телефоны и компьютеры подписчиков сайта (Firebase Cloud Messaging, бесплатно).

Подписки хранятся в базе сайта: push/{ключ} = {t: токен устройства, d: прогноз дня, m: {id матча: название}}.
Отправка — через FCM HTTP v1 от имени служебного аккаунта Firebase (секрет FIREBASE_SA в GitHub).
Без секрета модуль просто молчит — бот работает как раньше.
"""
from __future__ import annotations

import json
import os
import time

import requests

PROJECT = "aistavvit"
DB = "https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app"
SITE = "https://horoooos.github.io/betbot/"
_tok: dict = {"v": None, "exp": 0}
_subs: dict = {"v": None, "at": 0}


def enabled() -> bool:
    return bool(os.environ.get("FIREBASE_SA"))


def _token() -> str | None:
    """OAuth-токен служебного аккаунта (живёт час, переиспользуем)."""
    if _tok["v"] and time.time() < _tok["exp"] - 120:
        return _tok["v"]
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(os.environ["FIREBASE_SA"])
        creds = service_account.Credentials.from_service_account_info(info, scopes=[
            "https://www.googleapis.com/auth/firebase.messaging", "https://www.googleapis.com/auth/firebase.database",
            "https://www.googleapis.com/auth/userinfo.email"])
        creds.refresh(Request())
        _tok.update(v=creds.token, exp=time.time() + 3300)
        return creds.token
    except Exception as e:
        print(f"  ! push: не удалось авторизоваться в Firebase: {e}")
        return None


def _subscribers(tok: str) -> dict:
    if _subs["v"] is not None and time.time() - _subs["at"] < 300:
        return _subs["v"]
    try:
        r = requests.get(f"{DB}/push.json", params={"access_token": tok}, timeout=20)
        data = r.json() if r.ok else {}
    except requests.RequestException:
        data = {}
    _subs.update(v=data or {}, at=time.time())
    return _subs["v"]


def _send(tok: str, key: str, token: str, title: str, body: str, link: str, tag: str) -> bool:
    msg = {"message": {"token": token, "webpush": {
        "notification": {"title": title[:120], "body": body[:240], "icon": SITE + "icon-192.png", "badge": SITE + "favicon-32.png",
                         "tag": tag, "renotify": True},
        "fcm_options": {"link": link}, "headers": {"Urgency": "high", "TTL": "3600"}}}}
    try:
        r = requests.post(f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send", json=msg,
                          headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    except requests.RequestException:
        return False
    if r.status_code in (400, 404) and ("UNREGISTERED" in r.text or "INVALID_ARGUMENT" in r.text and "token" in r.text.lower()):
        requests.delete(f"{DB}/push/{key}.json", params={"access_token": tok}, timeout=20)   # устройство отписалось — чистим
        (_subs["v"] or {}).pop(key, None)
    return r.ok


def notify_match(match_id, title: str, body: str, link: str) -> int:
    """Всем, кто нажал «🔔 Голы» на этом матче."""
    if not enabled():
        return 0
    tok = _token()
    if not tok:
        return 0
    n = 0
    for key, s in list(_subscribers(tok).items()):
        if isinstance(s, dict) and s.get("t") and str(match_id) in (s.get("m") or {}):
            n += _send(tok, key, s["t"], title, body, link, f"ai-{match_id}")
    if n:
        print(f"  push: «{title}» → {n} устройств")
    return n


def notify_daily(title: str, body: str, link: str) -> int:
    """Всем, кто подписан на «Прогноз дня»."""
    if not enabled():
        return 0
    tok = _token()
    if not tok:
        return 0
    n = 0
    for key, s in list(_subscribers(tok).items()):
        if isinstance(s, dict) and s.get("t") and s.get("d"):
            n += _send(tok, key, s["t"], title, body, link, "ai-daily")
    print(f"  push: прогноз дня → {n} устройств")
    return n


def _score(e: dict) -> list[int] | None:
    try:
        if e.get("sport") == "tennis":
            return [sum(bool(x) for x in e["home"].get("set_won") or []), sum(bool(x) for x in e["away"].get("set_won") or [])]
        return [int(float(e["home"]["score"] or 0)), int(float(e["away"]["score"] or 0))]
    except (KeyError, TypeError, ValueError):
        return None


def watch(events: list[dict], store: dict) -> None:
    """Голы, начало и конец матчей — тем, кто нажал «🔔 Голы» в трансляции. store — память между запусками (state)."""
    if not enabled():
        return
    tok = _token()
    if not tok:
        return
    followed = {str(mid) for s in _subscribers(tok).values() if isinstance(s, dict) for mid in (s.get("m") or {})}
    for k in [k for k in store if k not in followed]:
        del store[k]
    if not followed:
        return
    from . import live   # ссылка на трансляцию
    for e in events:
        mid = str(e.get("id"))
        if mid not in followed or e.get("sport") == "esports":
            continue
        sport, st, sc = e.get("sport", "football"), e.get("state"), _score(e)
        h, a = e["home"].get("ru") or e["home"].get("name", ""), e["away"].get("ru") or e["away"].get("name", "")
        btn = live._tracker(e, sport, h, a)
        link = btn[1] if btn else SITE + "matches.html"
        prev = store.get(mid)
        store[mid] = {"s": sc, "st": st}
        if prev is None:
            continue
        if prev.get("st") == "pre" and st == "in":
            notify_match(mid, f"🔴 Матч начался: {h} — {a}", "Смотрите онлайн на АИ СТАВИТ", link)
        elif st == "in" and sc and prev.get("s") and sum(sc) > sum(prev["s"]) and sport != "basketball":
            word = {"football": "⚽ ГОЛ!", "hockey": "🏒 ШАЙБА!", "tennis": "🎾 СЕТ!"}.get(sport, "⚡")
            who = h if sc[0] > prev["s"][0] else a
            notify_match(mid, f"{word} {h} {sc[0]}:{sc[1]} {a}", f"{'Сет взял(а)' if sport == 'tennis' else 'Забивает'}: {who}", link)
        if st == "post" and prev.get("st") != "post" and sc:
            notify_match(mid, f"🏁 Финал: {h} {sc[0]}:{sc[1]} {a}", "Разбор и статистика матча на сайте", link)
