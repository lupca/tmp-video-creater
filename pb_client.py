"""Thin PocketBase REST client for the video-jobs worker.

Uses httpx (sync) to keep things simple — the worker main loop is
synchronous and renders are CPU-bound anyway.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("pb_client")

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class PBClient:
    """Minimal PocketBase admin client for the ``video_jobs`` collection."""

    def __init__(self, base_url: str, admin_email: str, admin_password: str) -> None:
        self._base = base_url.rstrip("/")
        self._email = admin_email
        self._password = admin_password
        self._token: str | None = None
        self._client = httpx.Client(timeout=_TIMEOUT)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            self._authenticate()
        return {"Authorization": self._token or ""}

    def _authenticate(self) -> None:
        resp = self._client.post(
            f"{self._base}/api/collections/_superusers/auth-with-password",
            json={"identity": self._email, "password": self._password},
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        logger.debug("PB admin auth OK")

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated request, refreshing the token on 401."""
        url = f"{self._base}{path}"
        headers = {**kwargs.pop("headers", {}), **self._auth_headers()}
        resp = self._client.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 401:
            self._token = None
            headers.update(self._auth_headers())
            resp = self._client.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Job operations
    # ------------------------------------------------------------------

    def list_queued_jobs(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return up to *limit* queued jobs sorted by priority desc, created asc."""
        resp = self._request(
            "GET",
            "/api/collections/video_jobs/records",
            params={
                "filter": "status='queued'",
                # Use id as secondary key because some legacy collections
                # don't expose created/updated as sortable fields.
                "sort": "-priority,-id",
                "perPage": limit,
            },
        )
        return resp.json().get("items", [])

    def list_expired_leases(self) -> list[dict[str, Any]]:
        """Return jobs whose lease has expired (worker crashed)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        resp = self._request(
            "GET",
            "/api/collections/video_jobs/records",
            params={
                "filter": f"(status='claimed' || status='rendering') && lease_until<'{now}'",
                "perPage": 50,
            },
        )
        return resp.json().get("items", [])

    def claim_job(self, job_id: str, worker_id: str, lease_seconds: int = 300) -> bool:
        """Atomically claim a queued job.  Returns ``False`` on conflict."""
        lease = _utc_plus(lease_seconds)
        try:
            self._request(
                "PATCH",
                f"/api/collections/video_jobs/records/{job_id}",
                json={
                    "status": "claimed",
                    "worker_id": worker_id,
                    "lease_until": lease,
                },
            )
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 409):
                return False
            raise

    def update_progress(
        self,
        job_id: str,
        progress: int,
        stage: str,
        status: str = "rendering",
        lease_seconds: int = 300,
    ) -> None:
        """Update progress + extend lease for a running job.

        Pass *progress* < 0 to only extend the lease without changing progress.
        """
        payload: dict[str, Any] = {
            "status": status,
            "lease_until": _utc_plus(lease_seconds),
        }
        if progress >= 0:
            payload["progress"] = progress
            payload["progress_stage"] = stage
        self._request(
            "PATCH",
            f"/api/collections/video_jobs/records/{job_id}",
            json=payload,
        )

    def upload_output(self, job_id: str, video_path: Path, duration_ms: int) -> None:
        """Upload the rendered MP4 and mark the job as done."""
        with video_path.open("rb") as f:
            self._request(
                "PATCH",
                f"/api/collections/video_jobs/records/{job_id}",
                data={
                    "status": "done",
                    "progress": "100",
                    "progress_stage": "done",
                    "render_duration_ms": str(duration_ms),
                },
                files={"output_video": (video_path.name, f, "video/mp4")},
            )

    def upload_thumbnail(self, job_id: str, thumb_path: Path) -> None:
        """Upload a thumbnail image for a completed job."""
        with thumb_path.open("rb") as f:
            self._request(
                "PATCH",
                f"/api/collections/video_jobs/records/{job_id}",
                files={"thumbnail": (thumb_path.name, f, "image/jpeg")},
            )

    def fail_job(self, job_id: str, error_message: str) -> None:
        """Increment attempt_count and optionally mark as failed."""
        rec = self.get_record(job_id)
        attempt = int(rec.get("attempt_count") or 0) + 1
        max_att = int(rec.get("max_attempts") or 3)
        new_status = "failed" if attempt >= max_att else "queued"
        self._request(
            "PATCH",
            f"/api/collections/video_jobs/records/{job_id}",
            json={
                "status": new_status,
                "attempt_count": attempt,
                "error_message": error_message[:5000],
                "worker_id": "",
                "lease_until": "",
            },
        )

    def reclaim_expired(self, job_id: str) -> None:
        """Reset an expired-lease job back to queued (or failed)."""
        self.fail_job(job_id, "lease expired — worker presumed dead")

    def get_record(self, job_id: str) -> dict[str, Any]:
        resp = self._request(
            "GET",
            f"/api/collections/video_jobs/records/{job_id}",
        )
        return resp.json()

    # ------------------------------------------------------------------
    # File download
    # ------------------------------------------------------------------

    def download_file(
        self,
        collection: str,
        record_id: str,
        filename: str,
        dest: Path,
    ) -> Path:
        """Download a PB file field attachment to *dest*."""
        url = f"{self._base}/api/files/{collection}/{record_id}/{filename}"
        with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(65536):
                    f.write(chunk)
        return dest

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PBClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _utc_plus(seconds: int) -> str:
    """ISO timestamp *seconds* from now (UTC)."""
    dt = datetime.fromtimestamp(time.time() + seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.000Z")
