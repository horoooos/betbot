"""Replace the cover of an existing, verified match-start post in our mirror."""
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betbot import dzen, postimg, telegram


def main():
    source_id = int(os.environ["SOURCE_ID"])
    target_id = int(os.environ["TARGET_ID"])
    response = requests.get(f"https://t.me/s/aistavvit_dzen?before={target_id + 1}", timeout=25)
    response.raise_for_status()
    parts = re.split(r'data-post="aistavvit_dzen/(\d+)"', response.text)
    block = next((parts[i + 1] for i in range(1, len(parts) - 1, 2) if int(parts[i]) == target_id), "")
    if not re.search(r't\.me/aistavvit/' + str(source_id) + r'(?:["<\s]|$)', block):
        raise RuntimeError("Целевая запись не содержит ожидаемую ссылку на исходный матч")
    post = json.loads(dzen.CHANNEL.read_text(encoding="utf-8"))["posts"][str(source_id)]
    if dzen.delivery_kind(post["html"]) != "начало":
        raise RuntimeError("Обновление разрешено только для карточки старта матча")
    text = dzen._match_text(post["html"])
    image = postimg._card(text, "начало")
    caption = dzen._caption(text, "#спорт #матчи #аиставит", f"\n\n📖 Полностью: t.me/aistavvit/{source_id}")
    media = json.dumps({"type": "photo", "media": "attach://cover", "caption": caption}, ensure_ascii=False)
    result = telegram._call("editMessageMedia", chat_id=dzen.TARGET, message_id=target_id, media=media,
                            files={"cover": ("match.png", image, "image/png")})
    print("UPDATED_MESSAGE:", result.get("message_id"))
    print("POST_URL:", f"https://t.me/aistavvit_dzen/{target_id}")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException:
        raise SystemExit("Ошибка сетевого запроса; адрес с ключом бота скрыт") from None
