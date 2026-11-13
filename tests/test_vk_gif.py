from io import BytesIO
import unittest
from PIL import Image
from betbot import vk_gif


class GifTests(unittest.TestCase):
    def test_render_preserves_card_size_and_has_two_frames(self):
        source = BytesIO()
        Image.new("RGB", (800, 450), "blue").save(source, "PNG")
        with Image.open(BytesIO(vk_gif.render(source.getvalue()))) as gif:
            self.assertEqual(gif.format, "GIF")
            self.assertEqual(gif.size, (800, 450))
            self.assertEqual(gif.n_frames, 2)


if __name__ == "__main__":
    unittest.main()
