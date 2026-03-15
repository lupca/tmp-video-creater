from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

# ---------------------------------------------------------------------------
# Default paths (used by CLI mode)
# ---------------------------------------------------------------------------
IMAGES_DIR = Path("images/1")
MUSIC_FILE = Path("bg_music.mp3")
BLUR_CACHE_DIR = Path(".cache_blur")
TTS_CACHE_DIR = Path(".cache_tts")
FONT_PATH = Path("assets/fonts/BeVietnamPro-Bold.ttf")
DATA_FILE = Path("data/video_content.json")
LOGO_FILE = Path("logo.webp")
ARROW_FILE = Path("arrow.png")

# ---------------------------------------------------------------------------
# Video constants
# ---------------------------------------------------------------------------
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

MIN_PRODUCTS = 2
MAX_PRODUCTS = 10


# ---------------------------------------------------------------------------
# Encoder detection
# ---------------------------------------------------------------------------
def detect_encoder(max_workers: int = 1) -> Tuple[str, int]:
    """Return (codec_name, ffmpeg_threads) based on platform capabilities.

    On macOS with VideoToolbox the hardware encoder offloads CPU so we can
    run more concurrent renders.  Falls back to libx264 with thread count
    scaled to leave room for *max_workers* processes.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        if "h264_videotoolbox" in result.stdout:
            return "h264_videotoolbox", 0  # 0 = auto
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    cpu = os.cpu_count() or 4
    threads = max(2, cpu // max(max_workers, 1))
    return "libx264", threads


def default_max_workers() -> int:
    """Sensible default concurrent workers for this machine."""
    codec, _ = detect_encoder(1)
    if codec == "h264_videotoolbox":
        return 3
    return 2


# ---------------------------------------------------------------------------
# Variant profiles
# ---------------------------------------------------------------------------
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

VARIANT_MAP = {v.name: v for v in VARIANTS}


# ---------------------------------------------------------------------------
# RenderContext — isolated paths for each render job
# ---------------------------------------------------------------------------
@dataclass
class RenderContext:
    """All path / encoding settings for a single render.

    Each worker process gets its own RenderContext so that temp files,
    caches, and outputs never collide between concurrent jobs.
    """
    work_dir: Path
    images_dir: Path
    music_file: Path
    blur_cache_dir: Path
    tts_cache_dir: Path
    font_path: Path
    logo_file: Path
    arrow_file: Path
    output_file: Path
    codec: str = "libx264"
    ffmpeg_threads: int = 4

    # --- factories -----------------------------------------------------------

    @classmethod
    def from_defaults(cls, output_file: str | None = None) -> "RenderContext":
        """Build a context using the module-level constants (CLI mode)."""
        codec, threads = detect_encoder()
        return cls(
            work_dir=Path("."),
            images_dir=IMAGES_DIR,
            music_file=MUSIC_FILE,
            blur_cache_dir=BLUR_CACHE_DIR,
            tts_cache_dir=TTS_CACHE_DIR,
            font_path=FONT_PATH,
            logo_file=LOGO_FILE,
            arrow_file=ARROW_FILE,
            output_file=Path(output_file or VARIANTS[0].output_file),
            codec=codec,
            ffmpeg_threads=threads,
        )

    @classmethod
    def for_job(
        cls,
        job_id: str,
        base_tmp: Path | None = None,
        max_workers: int = 1,
    ) -> "RenderContext":
        """Build an isolated context under a temp directory for a queue job.

        The caller is responsible for populating ``images_dir`` with
        downloaded product images before starting the render.
        """
        base = base_tmp or Path(tempfile.gettempdir()) / "video-jobs"
        job_dir = base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        images = job_dir / "images"
        images.mkdir(exist_ok=True)

        codec, threads = detect_encoder(max_workers)

        # Copy shared default assets into the job dir so each process
        # is fully self-contained.
        font_dst = job_dir / FONT_PATH.name
        if not font_dst.exists() and FONT_PATH.exists():
            font_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(FONT_PATH, font_dst)

        return cls(
            work_dir=job_dir,
            images_dir=images,
            music_file=job_dir / "bg_music.mp3",   # caller must copy/download
            blur_cache_dir=job_dir / ".cache_blur",
            tts_cache_dir=job_dir / ".cache_tts",
            font_path=font_dst if font_dst.exists() else FONT_PATH,
            logo_file=job_dir / "logo.webp",       # caller must copy/download
            arrow_file=job_dir / "arrow.png",      # caller must copy/download
            output_file=job_dir / "output.mp4",
            codec=codec,
            ffmpeg_threads=threads,
        )

    def cleanup(self) -> None:
        """Remove the job work directory (safe for temp dirs only)."""
        if self.work_dir != Path(".") and self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
