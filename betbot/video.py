"""Видео-новость: из нашей карточки новости делаем короткий ролик в фирменном стиле.

Плавное приближение кадра, золотая полоса прогресса сверху, «вспышка» света по заголовку
и водяной знак @aistavvit на всём видео. Звук — тихая дорожка (Telegram тогда показывает
пост как видео, а не как GIF). ffmpeg берём из пакета imageio-ffmpeg — ставить в систему не нужно.
Если что-то не получилось — возвращаем None, и бот публикует новость обычной картинкой.
"""
from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .card import H, W, font

SECONDS = 9
FPS = 30


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(f"  ! видео: нет ffmpeg ({e})")
        return None


def _watermark(text: str = "@aistavvit") -> Image.Image:
    """Плашка водяного знака: полупрозрачная, с мягкой тенью — читается на любом фоне."""
    try:
        f = font(30, "ExtraBold")
    except OSError:
        f = font(30)
    pad = 16
    w = int(f.getlength(text)) + pad * 2 + 34
    img = Image.new("RGBA", (w + 20, 70), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((10, 10, w + 10, 60), 25, fill=(0, 0, 0, 120))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 12, w + 10, 58), 23, fill=(10, 14, 32, 150), outline=(255, 196, 0, 170), width=2)
    d.ellipse((10 + pad, 27, 10 + pad + 16, 43), fill=(255, 196, 0, 235))              # «живая» точка бренда
    d.text((10 + pad + 26, 35), text, font=f, fill=(255, 255, 255, 230), anchor="lm")
    return img


def _sweep() -> Image.Image:
    """Полоса блика, которая один раз проходит по кадру."""
    img = Image.new("RGBA", (260, H + 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in range(260):
        a = int(70 * (1 - abs(x - 130) / 130) ** 2)
        d.line((x, 0, x, H + 200), fill=(255, 255, 255, a))
    return img.rotate(-14, expand=True, resample=Image.BICUBIC)


def news_video(png: bytes) -> bytes | None:
    exe = _ffmpeg()
    if not exe:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            card = Image.open(io.BytesIO(png)).convert("RGB").resize((W, H))
            card.save(t / "card.png")
            _watermark().save(t / "wm.png")
            _sweep().save(t / "sweep.png")
            n = SECONDS * FPS
            # 1) карточка в 4 раза крупнее → плавный zoompan без дрожания; 2) блик по кадру на 1.2–2.6 с;
            # 3) золотая полоса прогресса сверху; 4) водяной знак справа снизу; 5) появление и затухание
            flt = (
                f"[0:v]scale={W * 4}:{H * 4},zoompan=z='1+0.07*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS}[bg];"
                f"[bg][2:v]overlay=x='-400+(W+800)*(t-1.2)/1.4':y=-100:enable='between(t,1.2,2.6)'[s];"
                f"color=c=0xffc400:s={W}x7:r={FPS}[bar];[s][bar]overlay=x='-W+W*t/{SECONDS}':y=0:shortest=1[b];"
                f"[b][1:v]overlay=x=W-w-22:y=H-h-46[w];"
                f"[w]fade=t=in:st=0:d=0.5,fade=t=out:st={SECONDS - 0.6}:d=0.6,format=yuv420p[v]"
            )
            cmd = [exe, "-y", "-loglevel", "error",
                   "-loop", "1", "-framerate", str(FPS), "-i", str(t / "card.png"),
                   "-loop", "1", "-i", str(t / "wm.png"),
                   "-loop", "1", "-i", str(t / "sweep.png"),
                   "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                   "-filter_complex", flt, "-map", "[v]", "-map", "3:a",
                   "-t", str(SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(t / "out.mp4")]
            subprocess.run(cmd, check=True, timeout=240, capture_output=True)
            data = (t / "out.mp4").read_bytes()
            return data if len(data) > 20000 else None
    except subprocess.CalledProcessError as e:
        print(f"  ! видео не собралось: {e.stderr.decode(errors='ignore')[-300:]}")
    except Exception as e:
        print(f"  ! видео не собралось: {e}")
    return None
