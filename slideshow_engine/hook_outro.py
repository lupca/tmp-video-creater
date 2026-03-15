import math
import random
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from moviepy import ColorClip, CompositeVideoClip, ImageClip, TextClip, vfx
from .config import FONT_PATH, H, W

DEFAULT_FONT_PATH = FONT_PATH


def _resolve_font() -> str:
    if DEFAULT_FONT_PATH.exists():
        return str(DEFAULT_FONT_PATH)
    return "Arial"


def _require_existing_file(path_like: str | Path, label: str) -> Path:
    path = Path(path_like)
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay {label}: {path}")
    return path


def _load_rgba_clip(path_like: str | Path, duration: float) -> ImageClip:
    """Load RGBA image with explicit mask to avoid alpha artifacts after transforms."""
    path = _require_existing_file(path_like, "file hinh")
    rgba = np.array(Image.open(path).convert("RGBA"))

    rgb = rgba[:, :, :3]
    alpha = (rgba[:, :, 3].astype("float32")) / 255.0

    base = ImageClip(rgb).with_duration(duration)
    mask = ImageClip(alpha, is_mask=True).with_duration(duration)
    return base.with_mask(mask)


def create_intro_hook(
    images: Sequence[str],
    duration: float = 3.0,
    intro_text: str = "Top 5 vot cau long\nDang mua nhat 2026!",
) -> CompositeVideoClip:
    """
    Tao hook mo dau 3s voi hieu ung pop-up stack:
    - Nen toi
    - 5 anh hien lan luot moi 0.2s, xep chong lech va xoay ngau nhien
    - Text hook khong lo xuat hien tu 1.0s
    """
    if len(images) < 5:
        raise ValueError("Can it nhat 5 anh cho intro hook.")
    if duration <= 0:
        raise ValueError("duration phai > 0")

    font_name = _resolve_font()

    # Nen toi de lam noi bat cac anh san pham trong suot.
    bg = ColorClip(size=(W, H), color=(20, 20, 20)).with_duration(duration)

    # Vi tri xep chong quanh trung tam de tao cam giac "vange".
    stacked_positions = [
        (W * 0.50 - 230, H * 0.52 - 260),
        (W * 0.50 - 170, H * 0.52 - 220),
        (W * 0.50 - 260, H * 0.52 - 160),
        (W * 0.50 - 140, H * 0.52 - 130),
        (W * 0.50 - 210, H * 0.52 - 80),
    ]

    rng = random.Random(2026)
    image_layers = []
    for idx, img_path in enumerate(images[:5]):
        source_path = _require_existing_file(img_path, f"anh intro thu {idx + 1}")
        start_t = idx * 0.2
        layer_duration = max(0.1, duration - start_t)

        angle = rng.uniform(-15, 15)

        clip = ImageClip(str(source_path)).with_duration(layer_duration)
        clip = clip.resized(width=400)
        clip = clip.rotated(angle)
        clip = clip.with_start(start_t)
        clip = clip.with_position((int(stacked_positions[idx][0]), int(stacked_positions[idx][1])))

        # Pop-in nhe: scale tu 88% -> 100% trong 0.25s dau cua tung anh.
        clip = clip.with_effects(
            [vfx.Resize(lambda t: 0.88 + 0.12 * min(1.0, t / 0.25))]
        )
        image_layers.append(clip)

    hook_text = TextClip(
        text=intro_text,
        font=font_name,
        font_size=100,
        color="#FFD400",
        stroke_color="black",
        stroke_width=3,
        method="caption",
        size=(int(W * 0.92), None),
        margin=(24, 36),
        interline=10,
        text_align="center",
        duration=max(0.1, duration - 1.0),
    )
    hook_text = hook_text.with_start(1.0)
    hook_text = hook_text.with_position(("center", "center"))
    hook_text = hook_text.with_effects([vfx.FadeIn(0.18)])

    return CompositeVideoClip([bg, *image_layers, hook_text], size=(W, H)).with_duration(
        duration
    )


def create_outro_cta(
    logo_path: str,
    arrow_path: str,
    duration: float = 3.0,
    cta_text: str = "San ngay Flash Sale\nTai Gio Hang Shopee!",
) -> CompositeVideoClip:
    """
    Tao outro CTA 3s:
    - Lop den mo 70% de de chen de len frame cuoi video san pham
    - Logo nhip tim (resize theo sin)
    - Text CTA ben duoi logo
    - Mui ten nhay len/xuong lien tuc theo sin
    """
    if duration <= 0:
        raise ValueError("duration phai > 0")

    logo_file = _require_existing_file(logo_path, "logo")
    arrow_file = _require_existing_file(arrow_path, "icon mui ten")

    font_name = _resolve_font()

    # Lop den mo de lam outtro de doc; co the overlay len frame cuoi.
    dark_overlay = ColorClip(size=(W, H), color=(0, 0, 0)).with_duration(duration)
    dark_overlay = dark_overlay.with_opacity(0.7)

    logo = _load_rgba_clip(logo_file, duration=duration)
    logo = logo.resized(width=420)

    # Heartbeat formula:
    # scale(t) = 1 + 0.06*sin(2*pi*f*t) + 0.03*sin(2*pi*2*f*t)
    # Song bac 2 tao cam giac "thump" kep nhu nhip tim.
    logo = logo.with_effects(
        [
            vfx.Resize(
                lambda t: 1.0
                + 0.06 * math.sin(2 * math.pi * 1.9 * t)
                + 0.03 * math.sin(2 * math.pi * 3.8 * t)
            )
        ]
    )
    logo = logo.with_position(("center", int(H * 0.26)))

    cta_text = TextClip(
        text=cta_text,
        font=font_name,
        font_size=74,
        color="white",
        stroke_color="#C1121F",
        stroke_width=2,
        method="caption",
        size=(int(W * 0.90), None),
        margin=(20, 30),
        interline=8,
        text_align="center",
        duration=duration,
    )
    cta_text = cta_text.with_position(("center", int(H * 0.56)))
    cta_text = cta_text.with_effects([vfx.FadeIn(0.2)])

    arrow = _load_rgba_clip(arrow_file, duration=duration)
    arrow = arrow.resized(width=120)

    base_y = int(H * 0.85)
    # Arrow bounce formula:
    # y(t) = base_y + A * sin(2*pi*f*t)
    # A la bien do (pixel), f la tan so nhay moi giay.
    arrow = arrow.with_position(
        lambda t: ("center", base_y + 22 * math.sin(2 * math.pi * 2.6 * t))
    )

    return CompositeVideoClip(
        [dark_overlay, logo, cta_text, arrow],
        size=(W, H),
    ).with_duration(duration)
