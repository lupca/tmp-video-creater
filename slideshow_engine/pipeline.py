from pathlib import Path
from typing import Callable, List, Optional

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    afx,
    concatenate_videoclips,
    vfx,
)

from .audio_sync import analyze_strong_beats, compute_beat_synced_durations, estimate_copy_duration
from .config import (
    ARROW_FILE,
    FONT_PATH,
    FPS,
    IMAGES_DIR,
    INTRO_DURATION,
    INTRO_MUSIC_VOLUME,
    INTRO_TTS_START,
    INTRO_TTS_VOLUME,
    LOGO_FILE,
    MIN_SLIDE_DUR,
    MUSIC_FILE,
    OUTRO_DURATION,
    BODY_MUSIC_VOLUME,
    W,
    H,
    VARIANTS,
    RenderContext,
    VariantProfile,
)
from .data_input import ProductContent, VideoContent, load_video_content, validate_input_data
from .hook_outro import create_intro_hook, create_outro_cta
from .tts import synthesize_intro_tts
from .visuals import (
    create_bottom_text_overlay,
    create_hook_overlay,
    create_image_layers,
    ensure_vietnamese_font,
    make_motion_plan,
)

ProgressCallback = Callable[[int, str], None]


def _tiktok_flash_whip(clip: CompositeVideoClip) -> CompositeVideoClip:
    """Fast TikTok-like transition feel: white flash + whip slide-in from right."""
    flashed = clip.with_effects([vfx.SlideIn(0.20, "right"), vfx.CrossFadeIn(0.25)])

    flash = ColorClip(size=(W, H), color=(255, 255, 255)).with_duration(0.12)
    flash = flash.with_opacity(0.26)
    flash = flash.with_effects([vfx.FadeOut(0.12)])

    return CompositeVideoClip([flashed, flash], size=(W, H)).with_duration(clip.duration)


def _build_single_variant(
    items: List[ProductContent],
    profile: VariantProfile,
    intro_text: str,
    outro_text: str,
    ctx: Optional[RenderContext] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    """Core render pipeline.  When *ctx* is ``None`` the legacy module-level
    constants are used (CLI backward compat).  When provided, every path
    comes from *ctx* so concurrent workers never collide.
    """

    # Resolve paths ---------------------------------------------------------
    images_dir = ctx.images_dir if ctx else IMAGES_DIR
    music_file = ctx.music_file if ctx else MUSIC_FILE
    font_path_cfg = ctx.font_path if ctx else FONT_PATH
    logo_file = ctx.logo_file if ctx else LOGO_FILE
    arrow_file = ctx.arrow_file if ctx else ARROW_FILE
    blur_cache = ctx.blur_cache_dir if ctx else None  # None → default in visuals
    tts_cache = ctx.tts_cache_dir if ctx else None
    codec = ctx.codec if ctx else "libx264"
    ffmpeg_threads = ctx.ffmpeg_threads if ctx else 4
    output_file = str(ctx.output_file) if ctx else profile.output_file

    def _progress(pct: int, stage: str) -> None:
        if on_progress:
            on_progress(pct, stage)

    validate_input_data(items, images_dir=images_dir)
    font_path = ensure_vietnamese_font(font_path_cfg)

    if not Path(music_file).exists():
        raise FileNotFoundError(f"Khong tim thay file nhac: {music_file}")

    music_probe = AudioFileClip(str(music_file))
    audio_duration = float(music_probe.duration)
    music_probe.close()

    _progress(5, "tts")
    tts_kwargs = {"cache_dir": tts_cache} if tts_cache else {}
    tts_path = synthesize_intro_tts(intro_text, **tts_kwargs)
    tts_probe = AudioFileClip(str(tts_path))
    tts_duration = float(tts_probe.duration)
    tts_probe.close()

    intro_duration = max(INTRO_DURATION, min(6.0, tts_duration + INTRO_TTS_START + 0.45))
    outro_duration = max(OUTRO_DURATION, min(5.4, estimate_copy_duration(outro_text, OUTRO_DURATION)))

    body_audio_budget = max(len(items) * MIN_SLIDE_DUR, audio_duration - intro_duration - outro_duration)

    _progress(10, "beat_analysis")
    beat_times = analyze_strong_beats(str(music_file))
    durations = compute_beat_synced_durations(beat_times, items, body_audio_budget)
    motion_plan = make_motion_plan(len(items), seed=profile.seed)

    clips = []
    num_items = len(items)
    for idx, item in enumerate(items):
        image_path = images_dir / item["image"]
        slide_duration = durations[idx]

        cache_kwargs = {"cache_dir": blur_cache} if blur_cache else {}
        layers = create_image_layers(
            image_path=image_path,
            duration=slide_duration,
            motion_mode=motion_plan[idx],
            motion_intensity=profile.motion_intensity,
            **cache_kwargs,
        )

        text_overlay = create_bottom_text_overlay(item["text"], slide_duration, font_path)
        hook_overlay = create_hook_overlay(
            item["hook"],
            font_path=font_path,
            hook_color=profile.hook_color,
            hook_stroke=profile.hook_stroke,
        )

        slide = CompositeVideoClip(
            [*layers, text_overlay, hook_overlay],
            size=(W, H),
        ).with_duration(slide_duration)
        clips.append(slide)

        # Progress: slides span 10% → 75%
        slide_pct = 10 + int(65 * (idx + 1) / num_items)
        _progress(slide_pct, f"slide_{idx + 1}")

    for idx in range(1, len(clips)):
        clips[idx] = _tiktok_flash_whip(clips[idx])

    body_video = concatenate_videoclips(clips, method="compose", padding=-0.20)

    intro_images = [str(images_dir / item["image"]) for item in items]
    intro = create_intro_hook(intro_images, duration=intro_duration, intro_text=intro_text)
    body_video = _tiktok_flash_whip(body_video)

    outro = create_outro_cta(
        str(logo_file),
        str(arrow_file),
        duration=outro_duration,
        cta_text=outro_text,
    )
    outro = _tiktok_flash_whip(outro)

    final_video = concatenate_videoclips(
        [intro, body_video, outro],
        method="compose",
        padding=-0.20,
    )

    music = AudioFileClip(str(music_file)).subclipped(0, final_video.duration)

    intro_music = music.subclipped(0, min(intro_duration, final_video.duration))
    intro_music = intro_music.with_volume_scaled(INTRO_MUSIC_VOLUME)

    audio_layers = [intro_music]
    if final_video.duration > intro_duration:
        body_music = music.subclipped(intro_duration, final_video.duration)
        body_music = body_music.with_start(intro_duration)
        body_music = body_music.with_volume_scaled(BODY_MUSIC_VOLUME)
        body_music = body_music.with_effects([afx.AudioFadeOut(2)])
        audio_layers.append(body_music)

    intro_voice = AudioFileClip(str(tts_path))
    intro_voice = intro_voice.subclipped(
        0,
        min(intro_voice.duration, max(0.3, intro_duration - INTRO_TTS_START - 0.08)),
    )
    intro_voice = intro_voice.with_start(INTRO_TTS_START)
    intro_voice = intro_voice.with_volume_scaled(INTRO_TTS_VOLUME)
    audio_layers.append(intro_voice)

    mixed_audio = CompositeAudioClip(audio_layers).with_duration(final_video.duration)
    final_video = final_video.with_audio(mixed_audio)

    _progress(80, "encoding")
    final_video.write_videofile(
        output_file,
        fps=FPS,
        codec=codec,
        audio_codec="aac",
        threads=ffmpeg_threads,
    )

    _progress(100, "done")
    return output_file


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_single_variant(
    content: VideoContent,
    profile: VariantProfile,
    ctx: RenderContext,
    on_progress: Optional[ProgressCallback] = None,
) -> Path:
    """Render one variant using an isolated *RenderContext*.

    This is the primary entry point for the worker queue.  Each call is
    self-contained: all file paths come from *ctx*, so multiple calls can
    run concurrently in separate processes without conflicts.
    """
    out = _build_single_variant(
        items=content["products"],
        profile=profile,
        intro_text=content["intro_text"],
        outro_text=content["outro_text"],
        ctx=ctx,
        on_progress=on_progress,
    )
    return Path(out)


def render_all_variants(items: List[ProductContent] | None = None) -> List[str]:
    """CLI entry point — renders every active variant sequentially."""
    content: VideoContent = load_video_content()
    source_data = items if items is not None else content["products"]
    intro_text = content["intro_text"]
    outro_text = content["outro_text"]
    outputs: List[str] = []

    for profile in VARIANTS:
        ctx = RenderContext.from_defaults(output_file=profile.output_file)
        full_content = VideoContent(
            intro_text=intro_text,
            outro_text=outro_text,
            products=source_data,
        )
        out = render_single_variant(full_content, profile, ctx)
        outputs.append(str(out))

    return outputs
