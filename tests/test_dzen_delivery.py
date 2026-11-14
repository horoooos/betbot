import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from betbot import dzen


class CuratedChannelTests(unittest.TestCase):
    def test_selection_excludes_forecasts_and_live_noise(self):
        rejected = ["🎯 ПРОГНОЗ · Футбол\n#прогноз", "🔎 ПОЛНЫЙ РАЗБОР: А — Б\n#футбол",
                    "⭐ ПРОГНОЗЫ ДНЯ", "⚽ ГОЛ! А 1:0 Б\n#футбол", "🏒 ШАЙБА! А — Б\n#хоккей",
                    "⚡ LIVE-ПРОГНОЗ · 25'", "✅ LIVE-прогноз зашёл\n#футбол", "🏁 ИТОГ · Футбол\n#итог",
                    "📖 Продолжение\n#футбол", "🔥 ЭКСПРЕСС ДНЯ: 1 из 3 уже зашли!", "pinned a photo"]
        for text in rejected:
            with self.subTest(text=text):
                self.assertIsNone(dzen.delivery_kind(text))

    def test_selection_keeps_requested_categories(self):
        allowed = {"⚽ Головин вернулся к тренировкам\n#футбол": "новость",
                   "📊 СТАТИСТИКА БОТА": "статистика", "📅 МАТЧИ ДНЯ": "матчи",
                   "⭐ МАТЧ ДНЯ": "матчи", "🔴 МАТЧ НАЧАЛСЯ\nА — Б\n#live": "начало",
                   "🔥 ЭКСПРЕСС ДНЯ": "экспресс", "❌ ЭКСПРЕСС ДНЯ НЕ ЗАШЁЛ": "экспресс",
                   "🌙 ИТОГИ ДНЯ": "сводка"}
        for text, expected in allowed.items():
            with self.subTest(text=text):
                self.assertEqual(dzen.delivery_kind(text), expected)

    def _run(self, entries, state, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            channel = Path(directory) / "channel.json"
            channel.write_text(json.dumps({"posts": entries}), encoding="utf-8")
            with patch.dict(os.environ, {"TELEGRAM_TOKEN": "test", "TELEGRAM_CHAT_ID": "source"}), \
                    patch.object(dzen, "CHANNEL", channel), patch.object(dzen, "hashtags", return_value="#спорт"), \
                    patch("betbot.postimg._card", return_value=b"sanitized-card") as card, \
                    patch("betbot.postimg.image_for", return_value=b"image"), \
                    patch.object(dzen.telegram, "_call") as send:
                if fail:
                    send.side_effect = RuntimeError("temporary")
                done = dzen.crosspost(state)
                return done, send.call_args_list, card.call_args_list

    def post(self, text):
        return {"html": text, "t": datetime.now(timezone.utc).isoformat(), "photo": "image"}

    def test_forecasts_filtered_start_sanitized_and_duplicate_suppressed(self):
        start = "🔴 МАТЧ НАЧАЛСЯ\n⚽ А — Б\n🎯 Наш прогноз: П1 · кэф 2\n💰 Ставка 1% банка\n#live"
        entries = {"1": self.post("🎯 ПРОГНОЗ · Футбол"), "2": self.post(start), "3": self.post(start),
                   "4": self.post("🔎 ПОЛНЫЙ РАЗБОР: А — Б"), "5": self.post("🏁 ИТОГ · Футбол\n#итог")}
        state = {"dz_last": 0}
        done, calls, cards = self._run(entries, state)
        self.assertEqual(done, 1)
        self.assertEqual(calls[0].args[0], "sendPhoto")
        self.assertEqual(calls[0].kwargs["files"]["photo"][1], b"sanitized-card")
        for text in (calls[0].kwargs["caption"], cards[0].args[0]):
            self.assertNotIn("прогноз", text.lower())
            self.assertNotIn("ставка", text.lower())
            self.assertNotIn("кэф", text.lower())
        self.assertEqual(state["dz_last"], 5)

    def test_direct_news_and_channel_retry_share_deduplication(self):
        text = "⚽ Важная новость\n#футбол"
        state = {"dz_last": 0}
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "test"}), \
                patch.object(dzen, "hashtags", return_value=""), patch.object(dzen.telegram, "_call") as send:
            dzen.post_news(b"image", text, 1, state=state)
            dzen.post_news(b"image", text, 1, state=state)
            self.assertEqual(send.call_count, 1)
        done, calls, _ = self._run({"1": self.post(text)}, state)
        self.assertEqual(done, 0)
        self.assertFalse(calls)

    def test_news_failed_direct_delivery_can_be_retried_by_channel_copy(self):
        state = {"dz_last": 0}
        done, calls, _ = self._run({"1": self.post("⚽ Важная новость\n#футбол")}, state, fail=True)
        self.assertEqual(done, 0)
        self.assertEqual(state["dz_last"], 0)
        done, calls, _ = self._run({"1": self.post("⚽ Важная новость\n#футбол")}, state)
        self.assertEqual(done, 1)
        self.assertIsNone(state["dz_err"])

    def test_no_daily_limit_and_statistics_include_the_body(self):
        state = {"dz_last": 0}
        entries = {str(i): self.post(f"⚽ Новость {i}\n#футбол") for i in range(1, 12)}
        self.assertEqual(self._run(entries, state)[0], 10)
        self.assertEqual(self._run(entries, state)[0], 1)
        entries = {"12": self.post("📊 СТАТИСТИКА БОТА"), "13": self.post("Вчера, 13 ноября: 17/37, ROI -13%")}
        done, calls, _ = self._run(entries, state)
        self.assertEqual(done, 1)
        self.assertIn("17/37", calls[0].kwargs["caption"])


if __name__ == "__main__":
    unittest.main()
