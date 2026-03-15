from dataclasses import dataclass
from pathlib import Path

# Paths
IMAGES_DIR = Path("images/1")
MUSIC_FILE = Path("bg_music.mp3")
BLUR_CACHE_DIR = Path(".cache_blur")
TTS_CACHE_DIR = Path(".cache_tts")
FONT_PATH = Path("assets/fonts/BeVietnamPro-Bold.ttf")
DATA_FILE = Path("data/video_content.json")
LOGO_FILE = Path("logo.webp")
ARROW_FILE = Path("arrow.png")

# Video config
W, H = 1080, 1920
FPS = 30
CROSSFADE_SEC = 0.5
HOOK_DURATION = 0.8
MIN_SLIDE_DUR = 3.2
MAX_SLIDE_DUR = 6.2
INTRO_DURATION = 4.0
OUTRO_DURATION = 3.8
INTRO_TTS_START = 0.12
INTRO_MUSIC_VOLUME = 0.18
BODY_MUSIC_VOLUME = 1.0
INTRO_TTS_VOLUME = 1.55
TTS_VOICE = "vi-VN-HoaiMyNeural"
TTS_RATE = "+35%"


@dataclass(frozen=True)
class VariantProfile:
    name: str
    seed: int
    hook_color: str
    hook_stroke: int
    motion_intensity: float
    output_file: str


VARIANTS = [
    VariantProfile(
        name="A",
        seed=2026,
        hook_color="#FFE500",
        hook_stroke=6,
        motion_intensity=1.00,
        output_file="slideshow_sanpham_A.mp4",
    ),
    # VariantProfile(
    #     name="B",
    #     seed=2027,
    #     hook_color="#FF3B30",
    #     hook_stroke=7,
    #     motion_intensity=1.15,
    #     output_file="slideshow_sanpham_B.mp4",
    # ),
    # VariantProfile(
    #     name="C",
    #     seed=2028,
    #     hook_color="#00E5FF",
    #     hook_stroke=6,
    #     motion_intensity=0.90,
    #     output_file="slideshow_sanpham_C.mp4",
    # ),
]
