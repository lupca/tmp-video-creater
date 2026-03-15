"""Render demo outputs for intro hook and outro CTA functions."""

from pathlib import Path

from PIL import Image, ImageDraw

from moviepy import CompositeVideoClip, ImageClip, concatenate_videoclips

from slideshow_engine.config import ARROW_FILE, H, IMAGES_DIR, LOGO_FILE, W
from slideshow_engine.data_input import load_video_content
from slideshow_engine.hook_outro import create_intro_hook, create_outro_cta


def ensure_arrow_icon(path: Path) -> Path:
    """Create a simple down arrow icon if not present."""
    if path.exists():
        return path

    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White arrow with black outline for visibility.
    points = [(128, 220), (38, 110), (85, 110), (85, 36), (171, 36), (171, 110), (218, 110)]
    draw.polygon(points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))

    img.save(path)
    return path


def main() -> None:
    root = Path(__file__).parent
    logo_path = root / LOGO_FILE
    arrow_path = ensure_arrow_icon(root / ARROW_FILE)
    content = load_video_content()

    images = [str(IMAGES_DIR / product["image"]) for product in content["products"]]
    intro = create_intro_hook(images=images, duration=3.0, intro_text=content["intro_text"])
    intro.write_videofile(
        str(root / "intro_hook_demo.mp4"),
        fps=30,
        codec="libx264",
        audio=False,
        threads=4,
    )

    # Build a background frame from last image so outro overlay can be previewed clearly.
    preview_bg = ImageClip(str(images[-1])).with_duration(3.0)
    preview_bg = preview_bg.resized(height=H).with_position(("center", "center"))

    outro_overlay = create_outro_cta(
        str(logo_path),
        str(arrow_path),
        duration=3.0,
        cta_text=content["outro_text"],
    )
    outro = CompositeVideoClip([preview_bg, outro_overlay], size=(W, H)).with_duration(3.0)

    outro.write_videofile(
        str(root / "outro_cta_demo.mp4"),
        fps=30,
        codec="libx264",
        audio=False,
        threads=4,
    )

    combined = concatenate_videoclips([intro, outro], method="compose")
    combined.write_videofile(
        str(root / "hook_outro_combined_demo.mp4"),
        fps=30,
        codec="libx264",
        audio=False,
        threads=4,
    )


if __name__ == "__main__":
    main()
