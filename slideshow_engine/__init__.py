"""Slideshow engine package."""

from .config import RenderContext, VariantProfile, detect_encoder
from .hook_outro import create_intro_hook, create_outro_cta
from .pipeline import render_all_variants, render_single_variant

__all__ = [
    "RenderContext",
    "VariantProfile",
    "create_intro_hook",
    "create_outro_cta",
    "detect_encoder",
    "render_all_variants",
    "render_single_variant",
]
