"""Experimental GIF document rendering for a community-token wall test."""
from io import BytesIO

from PIL import Image, ImageDraw


def render(image: bytes) -> bytes:
    with Image.open(BytesIO(image)) as source:
        first = source.convert("RGB")
        first.thumbnail((1080, 1080))
    second = first.copy()
    ImageDraw.Draw(second).rectangle((0, second.height - 4, second.width, second.height), fill="#ffc400")
    result = BytesIO()
    first.save(result, "GIF", save_all=True, append_images=[second], duration=[1200, 1200], loop=0)
    return result.getvalue()
