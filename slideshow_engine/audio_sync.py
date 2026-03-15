from typing import Dict, List

import librosa
import numpy as np

from .config import MAX_SLIDE_DUR, MIN_SLIDE_DUR


def estimate_copy_duration(text: str, minimum: float) -> float:
    """Estimate readable on-screen duration from Vietnamese copy length."""
    words = [word for word in text.replace("\n", " ").split(" ") if word.strip()]
    # Around 2.6 words/sec plus a visual buffer so viewers can both read and inspect product.
    estimated = 1.15 + (len(words) / 2.6)
    return max(minimum, min(MAX_SLIDE_DUR, estimated))


def analyze_strong_beats(music_path: str) -> List[float]:
    """Extract strong beat timestamps for cut points using librosa."""
    audio, sr = librosa.load(music_path, sr=None, mono=True)
    onset_env = librosa.onset.onset_strength(y=audio, sr=sr)

    _, beat_frames = librosa.beat.beat_track(y=audio, sr=sr, onset_envelope=onset_env)
    if len(beat_frames) == 0:
        return []

    strengths = onset_env[beat_frames]
    threshold = float(np.percentile(strengths, 65))

    # Keep only stronger beats (proxy for downbeats) and thin to avoid overcutting.
    strong_frames = [int(f) for f in beat_frames if onset_env[f] >= threshold]
    if len(strong_frames) >= 8:
        strong_frames = strong_frames[::2]

    beat_times = librosa.frames_to_time(strong_frames, sr=sr).tolist()
    return [float(t) for t in beat_times if t >= 0.4]


def compute_beat_synced_durations(
    beat_times: List[float],
    items: List[Dict[str, str]],
    audio_duration: float,
) -> List[float]:
    """Snap slide boundaries to strong beats while respecting readable duration per slide."""
    clip_count = len(items)
    if clip_count <= 0:
        raise ValueError("clip_count phai > 0")

    desired_durations = []
    for item in items:
        title_duration = estimate_copy_duration(item.get("text", ""), MIN_SLIDE_DUR)
        hook_duration = estimate_copy_duration(item.get("hook", ""), MIN_SLIDE_DUR - 0.2)
        desired_durations.append(min(MAX_SLIDE_DUR, max(title_duration, hook_duration) + 0.35))

    if not beat_times:
        return desired_durations

    boundaries = [0.0]
    cursor = 0.0

    for i, desired_duration in enumerate(desired_durations, start=1):
        remaining_slides = clip_count - i
        target_end = cursor + desired_duration
        min_end = cursor + max(MIN_SLIDE_DUR, desired_duration - 0.35)
        max_end = cursor + MAX_SLIDE_DUR

        # Reserve enough room for the remaining slides so late clips do not collapse.
        latest_safe_end = audio_duration - (remaining_slides * MIN_SLIDE_DUR) - 0.05
        earliest_safe_end = cursor + MIN_SLIDE_DUR

        max_end = min(max_end, latest_safe_end)
        min_end = min(min_end, max_end)
        target_end = min(max(target_end, earliest_safe_end), max_end)

        candidates = [b for b in beat_times if min_end <= b <= max_end]
        if candidates:
            # Prefer the next strong beat near the readable target end.
            end_t = min(candidates, key=lambda b: abs(b - target_end))
        else:
            end_t = min(max(target_end, min_end), max_end)

        end_t = min(end_t, latest_safe_end)
        boundaries.append(end_t)
        cursor = end_t

    return [max(1.2, boundaries[i + 1] - boundaries[i]) for i in range(clip_count)]
