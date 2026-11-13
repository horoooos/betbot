"""Verify newly created wall posts through community Long Poll events."""
import requests

from . import vk


class PhotoMonitor:
    def __init__(self, token):
        self.token = token
        self.server = None

    def start(self):
        settings = vk._call("groups.getLongPollSettings", _tok=self.token, group_id=vk.GROUP_ID)
        events = settings.get("events") or {}
        if not settings.get("is_enabled") or not events.get("wall_post_new"):
            flags = {name: int(value) for name, value in events.items() if isinstance(value, (bool, int))}
            flags["wall_post_new"] = 1
            vk._call("groups.setLongPollSettings", _tok=self.token, group_id=vk.GROUP_ID,
                     enabled=1, api_version=settings.get("api_version") or vk.V, **flags)
        self.server = vk._call("groups.getLongPollServer", _tok=self.token, group_id=vk.GROUP_ID)

    def verify(self, post_id):
        if not self.server:
            raise RuntimeError("Монитор стены не запущен")
        for _ in range(3):
            try:
                response = requests.get(self.server["server"], params={"act": "a_check", "key": self.server["key"],
                                        "ts": self.server["ts"], "wait": 2}, timeout=12)
                response.raise_for_status()
                result = response.json()
            except (requests.RequestException, ValueError):
                raise RuntimeError("Ошибка чтения событий VK; ключ Long Poll скрыт") from None
            if result.get("failed") == 1 and result.get("ts"):
                self.server["ts"] = result["ts"]
                continue
            if result.get("failed"):
                raise RuntimeError("VK не дал прочитать события публикации")
            self.server["ts"] = result.get("ts", self.server["ts"])
            for event in result.get("updates", []):
                post = event.get("object") or {}
                if event.get("type") == "wall_post_new" and event.get("group_id") == vk.GROUP_ID and post.get("id") == post_id:
                    return any(a.get("type") == "photo" for a in post.get("attachments", []))
        raise RuntimeError("Событие созданного поста пока не получено; повторно не публикуем")
