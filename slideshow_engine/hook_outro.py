import math
import random
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from moviepy import ColorClip, CompositeVideoClip, ImageClip, TextClip, vfx
from .config import FONT_PATH, H, MAX_PRODUCTS, MIN_PRODUCTS, W

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


def _compute_stack_positions(count: int, seed: int = 2026) -> list[tuple[float, float]]:
    """Generate overlapping stack positions centred on screen for *count* images."""
    rng = random.Random(seed)
    cx, cy = W * 0.50, H * 0.52
    # Spread images in a loose cluster; more images → wider spread
    spread_x = 120 + count * 12
    spread_y = 80 + count * 18
    positions = []
    for i in range(count):
        angle = (2 * math.pi * i / count) + rng.uniform(-0.3, 0.3)
        r = 0.5 + rng.uniform(0, 0.5)
        x = cx - 200 + r * spread_x * math.cos(angle)
        y = cy - 180 + r * spread_y * math.sin(angle)
        positions.append((x, y))
    return positions


def create_intro_hook(
    images: Sequence[str],
    duration: float = 3.0,
    intro_text: str = "Top 5 vot cau long\nDang mua nhat 2026!",
) -> CompositeVideoClip:
    """Intro hook with stacked pop-in images.  Supports 2-10 images."""
    count = min(len(images), MAX_PRODUCTS)
    if count < MIN_PRODUCTS:
        raise ValueError(f"Can it nhat {MIN_PRODUCTS} anh cho intro hook.")
    if duration <= 0:
        raise ValueError("duration phai > 0")

    font_name = _resolve_font()

    bg = ColorClip(size=(W, H), color=(20, 20, 20)).with_duration(duration)

    stacked_positions = _compute_stack_positions(count)

    rng = random.Random(2026)
    image_layers = []
    stagger = min(0.2, (duration * 0.4) / max(count, 1))  # fit all pop-ins in first 40%
    for idx, img_path in enumerate(images[:count]):
        source_path = _require_existing_file(img_path, f"anh intro thu {idx + 1}")
        start_t = idx * stagger
        layer_duration = max(0.1, duration - start_t)

        angle = rng.uniform(-15, 15)

        clip = ImageClip(str(source_path)).with_duration(layer_duration)
        clip = clip.resized(width=400)
        clip = clip.rotated(angle)
        clip = clip.with_start(start_t)
        clip = clip.with_position((int(stacked_positions[idx][0]), int(stacked_positions[idx][1])))

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
