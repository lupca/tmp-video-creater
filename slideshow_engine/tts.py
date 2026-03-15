import asyncio
import hashlib
from pathlib import Path

import edge_tts

from .config import TTS_CACHE_DIR, TTS_RATE, TTS_VOICE


def _tts_cache_path(text: str, voice: str, rate: str, cache_dir: Path = TTS_CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()
    return cache_dir / f"intro_tts_{digest}.mp3"


async def _save_tts(text: str, output_path: Path, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_path))


def synthesize_intro_tts(
    text: str,
    voice: str = TTS_VOICE,
    rate: str = TTS_RATE,
    cache_dir: Path = TTS_CACHE_DIR,
) -> Path:
    """Generate cached Vietnamese neural TTS for intro text only."""
    output_path = _tts_cache_path(text=text, voice=voice, rate=rate, cache_dir=cache_dir)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    asyncio.run(_save_tts(text=text, output_path=output_path, voice=voice, rate=rate))
    return output_path