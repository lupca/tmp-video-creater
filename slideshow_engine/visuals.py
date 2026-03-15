import math
import random
from pathlib import Path
from typing import List

from PIL import Image, ImageFilter

from moviepy import ColorClip, CompositeVideoClip, ImageClip, TextClip, vfx

from .config import BLUR_CACHE_DIR, H, HOOK_DURATION, W


def ensure_vietnamese_font(font_path: Path) -> Path:
    if not font_path.exists():
        raise FileNotFoundError(
            "Khong tim thay font tieng Viet tai FONT_PATH. "
            "Hay doi FONT_PATH sang file .ttf ho tro UTF-8 tren may ban."
        )
    return font_path


def generate_blurred_background(image_path: Path) -> Path:
    BLUR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_file = BLUR_CACHE_DIR / f"{image_path.stem}_blur.jpg"
    if cached_file.exists():
        return cached_file

    with Image.open(image_path).convert("RGB") as img:
        src_w, src_h = img.size
        scale = max(W / src_w, H / src_h)
        resized_w = int(src_w * scale)
        resized_h = int(src_h * scale)
        resized = img.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

        left = (resized_w - W) // 2
        top = (resized_h - H) // 2
        cropped = resized.crop((left, top, left + W, top + H))
        blurred = cropped.filter(ImageFilter.GaussianBlur(radius=22))
        blurred.save(cached_file, format="JPEG", quality=95)

    return cached_file


def make_motion_plan(count: int, seed: int) -> List[str]:
    modes = ["zoom_in", "pan_left", "pan_right", "zoom_out"]
    rng = random.Random(seed)
    return [rng.choice(modes) for _ in range(count)]


def apply_motion(clip: ImageClip, mode: str, duration: float, intensity: float) -> ImageClip:
    safe_duration = max(duration, 0.1)

    if mode == "zoom_in":
        moved = clip.with_effects(
            [vfx.Resize(lambda t: 1 + (0.05 * intensity) * (t / safe_duration))]
        )
        return moved.with_position(("center", "center"))

    if mode == "pan_left":
        base_x = (W - clip.w) / 2
        base_y = (H - clip.h) / 2
        offset = 80 * intensity
        return clip.with_position(lambda t: (base_x - offset * (t / safe_duration), base_y))

    if mode == "pan_right":
        base_x = (W - clip.w) / 2
        base_y = (H - clip.h) / 2
        offset = 80 * intensity
        return clip.with_position(lambda t: (base_x + offset * (t / safe_duration), base_y))

    moved = clip.with_effects(
        [vfx.Resize(lambda t: 1.10 - (0.08 * intensity) * (t / safe_duration))]
    )
    return moved.with_position(("center", "center"))


def create_image_layers(
    image_path: Path,
    duration: float,
    motion_mode: str,
    motion_intensity: float,
) -> List[ImageClip]:
    bg_path = generate_blurred_background(image_path)
    bg = ImageClip(str(bg_path)).with_duration(duration)
    bg = bg.with_effects([vfx.Resize(lambda t: 1 + 0.006 * t)])
    bg = bg.with_position(("center", "center"))

    fg = ImageClip(str(image_path)).with_duration(duration)
    fit_scale = min((W * 0.9) / fg.w, (H * 0.78) / fg.h)
    fg = fg.resized(new_size=(int(fg.w * fit_scale), int(fg.h * fit_scale)))
    fg = fg.resized(new_size=(int(fg.w * 1.08), int(fg.h * 1.08)))
    fg = apply_motion(fg, mode=motion_mode, duration=duration, intensity=motion_intensity)

    return [bg, fg]


def create_bottom_text_overlay(text: str, duration: float, font_path: Path) -> CompositeVideoClip:
    show_duration = max(0.2, duration - HOOK_DURATION)

    txt = TextClip(
        text=text,
        font=str(font_path),
        font_size=66,
        color="#FFD400",
        stroke_color="black",
        stroke_width=3,
        method="caption",
        size=(int(W * 0.88), None),
        margin=(24, 28),
        interline=8,
        text_align="center",
        duration=show_duration,
    )

    panel = ColorClip(
        size=(int(W * 0.92), int(txt.h + 38)),
        color=(0, 0, 0),
    ).with_duration(show_duration)
    panel = panel.with_opacity(0.5)

    base_y = int(H * 0.72)
    panel = panel.with_position(("center", base_y))
    txt = txt.with_position(("center", base_y + 19))

    # Animate panel + text as a single block to avoid desync/misalignment.
    block = CompositeVideoClip([panel, txt], size=(W, H)).with_duration(show_duration)
    block = block.with_effects([vfx.FadeIn(0.35), vfx.SlideIn(0.35, "bottom")])
    block = block.with_start(HOOK_DURATION)

    return CompositeVideoClip([block], size=(W, H)).with_duration(duration)


def create_hook_overlay(
    hook_text: str,
    font_path: Path,
    hook_color: str,
    hook_stroke: int,
) -> CompositeVideoClip:
    # Add margin/interline to avoid glyph clipping at descenders.
    hook = TextClip(
        text=hook_text,
        font=str(font_path),
        font_size=92,
        color=hook_color,
        stroke_color="black",
        stroke_width=hook_stroke,
        method="caption",
        size=(int(W * 0.93), None),
        margin=(30, 44),
        interline=10,
        text_align="center",
        duration=HOOK_DURATION,
    )

    base_x = (W - hook.w) / 2
    base_y = int(H * 0.43)

    def hook_pos(t: float):
        decay = math.exp(-5.2 * t)
        shake_x = 14 * math.sin(38 * t) * decay
        bounce_y = -20 * abs(math.sin(20 * t)) * decay
        return base_x + shake_x, base_y + bounce_y

    hook = hook.with_position(hook_pos).with_effects([vfx.FadeIn(0.12)])

    # Background panel follows hook motion so text and highlight stay locked together.
    hook_panel = ColorClip(
        size=(min(W - 60, int(hook.w + 24)), int(hook.h + 12)),
        color=(0, 0, 0),
    ).with_duration(HOOK_DURATION)
    hook_panel = hook_panel.with_opacity(0.46)
    hook_panel = hook_panel.with_position(lambda t: (hook_pos(t)[0] - 12, hook_pos(t)[1] + 8))
    hook_panel = hook_panel.with_effects([vfx.FadeIn(0.08)])

    return CompositeVideoClip([hook_panel, hook], size=(W, H)).with_duration(HOOK_DURATION)
