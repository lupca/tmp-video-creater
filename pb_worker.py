#!/usr/bin/env python3
"""PocketBase video-jobs worker.

Polls the ``video_jobs`` collection and renders videos concurrently
using ``ProcessPoolExecutor``.  Each render runs in an isolated temp
directory so multiple jobs never conflict.

Usage:
    PB_URL=http://localhost:8090 \
    PB_ADMIN_EMAIL=admin@example.com \
    PB_ADMIN_PASSWORD=secret \
    python pb_worker.py

Environment variables:
    PB_URL              PocketBase base URL (required)
    PB_ADMIN_EMAIL      Admin email (required)
    PB_ADMIN_PASSWORD   Admin password (required)
    MAX_WORKERS         Concurrent renders (default: auto-detect 2-3)
    POLL_INTERVAL       Seconds between polling (default: 5)
    LEASE_SECONDS       Lease duration per job (default: 600)
    BASE_TMP            Temp directory root (default: /tmp/video-jobs)
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import platform
import shutil
import signal
import sys
import time
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configure logging before anything else
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pb_worker")

# ---------------------------------------------------------------------------
# Imports from the slideshow engine (heavy — moviepy, PIL, etc.)
# Only imported in the *child* process via _render_in_process().
# ---------------------------------------------------------------------------
# Lazy to avoid loading heavy libs in the coordinator process.

from pb_client import PBClient  # noqa: E402 — lives next to this file

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
PB_URL = os.environ.get("PB_URL", "http://localhost:8090")
PB_ADMIN_EMAIL = os.environ.get("PB_ADMIN_EMAIL", "")
PB_ADMIN_PASSWORD = os.environ.get("PB_ADMIN_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
LEASE_SECONDS = int(os.environ.get("LEASE_SECONDS", "600"))
BASE_TMP = Path(os.environ.get("BASE_TMP", "/tmp/video-jobs"))

# Default assets (copy into each job dir if job doesn't supply its own)
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MUSIC = PROJECT_ROOT / "bg_music.mp3"
DEFAULT_LOGO = PROJECT_ROOT / "logo.webp"
DEFAULT_ARROW = PROJECT_ROOT / "arrow.png"
DEFAULT_FONT = PROJECT_ROOT / "assets" / "fonts" / "BeVietnamPro-Bold.ttf"

_shutdown_requested = False


def _signal_handler(signum: int, _frame: Any) -> None:
    global _shutdown_requested
    logger.info("Shutdown requested (signal %d) — finishing active renders …", signum)
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# Worker ID
# ---------------------------------------------------------------------------
def _worker_id() -> str:
    return f"{platform.node()}:{os.getpid()}"


# ---------------------------------------------------------------------------
# Thumbnail extraction — first frame via ffmpeg
# ---------------------------------------------------------------------------
def _extract_thumbnail(video_path: Path) -> Path | None:
    """Extract first frame of video as JPEG.  Returns path or None."""
    import subprocess
    thumb = video_path.with_suffix(".thumb.jpg")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-frames:v", "1", "-q:v", "2",
                str(thumb),
            ],
            capture_output=True,
            timeout=30,
        )
        return thumb if thumb.exists() else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Child-process render function
# ---------------------------------------------------------------------------
def _render_in_process(
    job_id: str,
    job_data: dict[str, Any],
    work_dir: str,
    max_workers: int,
    progress_queue_name: str | None = None,
) -> dict[str, Any]:
    """Run inside a child process via ProcessPoolExecutor.

    Returns a dict with ``output_path`` on success or ``error`` on failure.
    All heavy imports happen here so the coordinator stays lightweight.
    """
    try:
        from slideshow_engine.config import (
            ARROW_FILE,
            FONT_PATH,
            LOGO_FILE,
            MUSIC_FILE,
            RenderContext,
            VARIANT_MAP,
            VARIANTS,
            VariantProfile,
        )
        from slideshow_engine.data_input import VideoContent, load_from_dict
        from slideshow_engine.pipeline import render_single_variant

        wd = Path(work_dir)

        # Resolve variant profile
        variant_name = job_data.get("variant_name", "A") or "A"
        profile = VARIANT_MAP.get(variant_name, VARIANTS[0])

        # Build RenderContext for this job
        ctx = RenderContext.for_job(job_id, base_tmp=wd.parent, max_workers=max_workers)

        # Parse content from input_json
        input_json = job_data.get("input_json", {})
        if isinstance(input_json, str):
            input_json = json.loads(input_json)
        content: VideoContent = load_from_dict(input_json)

        # Render
        t0 = time.monotonic()
        output = render_single_variant(content, profile, ctx)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        return {
            "output_path": str(output),
            "render_duration_ms": elapsed_ms,
            "work_dir": str(ctx.work_dir),
        }

    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Job preparation — download files from PB into the job work dir
# ---------------------------------------------------------------------------
def _prepare_job_dir(
    client: PBClient,
    job: dict[str, Any],
    job_dir: Path,
) -> None:
    """Download input files from PB and copy default assets."""

    images_dir = job_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    record_id = job["id"]
    collection = "video_jobs"

    # Download product images
    input_images = job.get("input_images") or []
    if isinstance(input_images, str):
        input_images = [input_images]
    for filename in input_images:
        client.download_file(collection, record_id, filename, images_dir / filename)

    # Download optional music or copy default
    input_music = job.get("input_music")
    music_dst = job_dir / "bg_music.mp3"
    if input_music:
        client.download_file(collection, record_id, input_music, music_dst)
    elif DEFAULT_MUSIC.exists():
        shutil.copy2(DEFAULT_MUSIC, music_dst)

    # Download optional logo or copy default
    input_logo = job.get("input_logo")
    logo_dst = job_dir / "logo.webp"
    if input_logo:
        client.download_file(collection, record_id, input_logo, logo_dst)
    elif DEFAULT_LOGO.exists():
        shutil.copy2(DEFAULT_LOGO, logo_dst)

    # Copy default arrow
    arrow_dst = job_dir / "arrow.png"
    if DEFAULT_ARROW.exists() and not arrow_dst.exists():
        shutil.copy2(DEFAULT_ARROW, arrow_dst)

    # Copy default font
    font_dst = job_dir / "BeVietnamPro-Bold.ttf"
    if DEFAULT_FONT.exists() and not font_dst.exists():
        shutil.copy2(DEFAULT_FONT, font_dst)

    # Remap image filenames in input_json to match downloaded names
    input_json = job.get("input_json", {})
    if isinstance(input_json, str):
        input_json = json.loads(input_json)
    products = input_json.get("products", [])
    for i, prod in enumerate(products):
        if i < len(input_images):
            prod["image"] = input_images[i]


# ---------------------------------------------------------------------------
# Main coordinator loop
# ---------------------------------------------------------------------------
def main() -> None:
    if not PB_ADMIN_EMAIL or not PB_ADMIN_PASSWORD:
        logger.error("PB_ADMIN_EMAIL and PB_ADMIN_PASSWORD must be set")
        sys.exit(1)

    # Detect concurrency
    from slideshow_engine.config import default_max_workers, detect_encoder
    max_workers = int(os.environ.get("MAX_WORKERS", "0")) or default_max_workers()
    codec, threads = detect_encoder(max_workers)
    logger.info(
        "Starting worker  workers=%d  codec=%s  ffmpeg_threads=%d  poll=%ds",
        max_workers, codec, threads, POLL_INTERVAL,
    )

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    client = PBClient(PB_URL, PB_ADMIN_EMAIL, PB_ADMIN_PASSWORD)

    # Fail fast on auth/config errors instead of looping indefinitely.
    try:
        client.list_queued_jobs(limit=1)
    except Exception as exc:
        logger.error(
            "Worker startup failed: cannot authenticate or query video_jobs (PB_URL=%s, PB_ADMIN_EMAIL=%s). Error: %s",
            PB_URL,
            PB_ADMIN_EMAIL,
            exc,
        )
        client.close()
        sys.exit(1)

    # Track in-flight jobs: job_id → Future
    in_flight: dict[str, Future[dict[str, Any]]] = {}
    # Track work dirs for cleanup
    work_dirs: dict[str, str] = {}
    # Counter for periodic stale-dir cleanup
    poll_count = 0
    CLEANUP_EVERY = max(1, 300 // POLL_INTERVAL)  # ~every 5 minutes

    # Use 'spawn' to avoid fork issues with MoviePy/numpy on macOS
    mp_ctx = mp.get_context("spawn")
    executor = ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=mp_ctx,
    )

    wid = _worker_id()
    logger.info("Worker ID: %s", wid)

    try:
        while not _shutdown_requested:
            # ----------------------------------------------------------
            # 1. Collect completed futures
            # ----------------------------------------------------------
            done_ids = [jid for jid, fut in in_flight.items() if fut.done()]
            for job_id in done_ids:
                fut = in_flight.pop(job_id)
                try:
                    result = fut.result()
                    if "error" in result:
                        logger.error("Job %s failed: %s", job_id, result["error"])
                        client.fail_job(job_id, result["error"])
                    else:
                        output_path = Path(result["output_path"])
                        duration_ms = result.get("render_duration_ms", 0)
                        logger.info(
                            "Job %s done in %ds — uploading %s",
                            job_id, duration_ms // 1000, output_path.name,
                        )
                        client.update_progress(job_id, 95, "uploading", status="uploading")
                        client.upload_output(job_id, output_path, duration_ms)
                        # Extract and upload thumbnail
                        thumb = _extract_thumbnail(output_path)
                        if thumb:
                            client.upload_thumbnail(job_id, thumb)
                        logger.info("Job %s uploaded successfully", job_id)
                except Exception as exc:
                    logger.exception("Job %s post-processing error", job_id)
                    client.fail_job(job_id, f"post-processing: {exc}")
                finally:
                    # Cleanup work dir
                    wd = work_dirs.pop(job_id, None)
                    if wd:
                        shutil.rmtree(wd, ignore_errors=True)

            # ----------------------------------------------------------
            # 2. Reclaim expired leases
            # ----------------------------------------------------------
            try:
                expired = client.list_expired_leases()
                for job in expired:
                    jid = job["id"]
                    if jid not in in_flight:
                        logger.warning("Reclaiming expired lease: %s", jid)
                        client.reclaim_expired(jid)
            except Exception:
                logger.debug("Lease reclaim check failed", exc_info=True)

            # ----------------------------------------------------------
            # 3. Claim new jobs if we have capacity
            # ----------------------------------------------------------
            available_slots = max_workers - len(in_flight)
            if available_slots > 0 and not _shutdown_requested:
                try:
                    queued = client.list_queued_jobs(limit=available_slots)
                except Exception:
                    logger.warning("Failed to poll jobs", exc_info=True)
                    queued = []

                for job in queued:
                    if _shutdown_requested:
                        break
                    job_id = job["id"]
                    if job_id in in_flight:
                        continue

                    if not client.claim_job(job_id, wid, LEASE_SECONDS):
                        logger.debug("Job %s already claimed", job_id)
                        continue

                    logger.info("Claimed job %s", job_id)

                    # Prepare work dir + download files
                    job_dir = BASE_TMP / job_id
                    try:
                        _prepare_job_dir(client, job, job_dir)
                    except Exception as exc:
                        logger.error("Failed to prepare job %s: %s", job_id, exc)
                        client.fail_job(job_id, f"prepare: {exc}")
                        shutil.rmtree(job_dir, ignore_errors=True)
                        continue

                    client.update_progress(job_id, 1, "starting", status="rendering")

                    # Submit render to process pool
                    fut = executor.submit(
                        _render_in_process,
                        job_id=job_id,
                        job_data=job,
                        work_dir=str(job_dir),
                        max_workers=max_workers,
                    )
                    in_flight[job_id] = fut
                    work_dirs[job_id] = str(job_dir)

            # ----------------------------------------------------------
            # 4. Heartbeat for active jobs
            # ----------------------------------------------------------
            for job_id in list(in_flight.keys()):
                try:
                    client.update_progress(
                        job_id, -1, "",  # -1 = don't change progress
                        status="rendering",
                        lease_seconds=LEASE_SECONDS,
                    )
                except Exception:
                    pass  # best-effort

            # ----------------------------------------------------------
            # 5. Periodic cleanup of stale temp dirs (>24h old)
            # ----------------------------------------------------------
            poll_count += 1
            if poll_count % CLEANUP_EVERY == 0 and BASE_TMP.exists():
                cutoff = time.time() - 86400  # 24 hours
                for entry in BASE_TMP.iterdir():
                    if not entry.is_dir():
                        continue
                    if entry.name in in_flight:
                        continue
                    try:
                        if entry.stat().st_mtime < cutoff:
                            logger.info("Cleaning stale dir: %s", entry.name)
                            shutil.rmtree(entry, ignore_errors=True)
                    except OSError:
                        pass

            # ----------------------------------------------------------
            # 6. Sleep
            # ----------------------------------------------------------
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    finally:
        logger.info("Shutting down executor (waiting for %d active jobs) …", len(in_flight))
        executor.shutdown(wait=True, cancel_futures=False)
        # Final upload for anything that completed during shutdown
        for job_id, fut in in_flight.items():
            try:
                result = fut.result(timeout=5)
                if "error" not in result:
                    output_path = Path(result["output_path"])
                    client.upload_output(
                        job_id, output_path,
                        result.get("render_duration_ms", 0),
                    )
            except Exception:
                logger.warning("Could not finalize job %s during shutdown", job_id)
            finally:
                wd = work_dirs.pop(job_id, None)
                if wd:
                    shutil.rmtree(wd, ignore_errors=True)
        client.close()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    main()
