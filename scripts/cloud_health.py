"""End-to-end cloud reachability probe.

Verifies the three things Phase 3 cloud features depend on:
  1. Supabase REST API is reachable with the configured service-role key.
  2. pgvector is callable (best-effort; skipped if no RPC is wired yet).
  3. Storage bucket round-trip (upload -> download -> bit-compare -> delete).

Exit codes:
  0 — all PASS (pgvector SKIP still counts as success per spec).
  1 — at least one FAIL.
  2 — required env vars missing (cannot even try).

Run with: ``python -m scripts.cloud_health`` or ``python scripts/cloud_health.py``.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Final

import httpx
from foundry_api.cloud import (
    CloudObjectNotFound,
    CloudStorageError,
    SupabaseStorage,
)
from foundry_api.config import settings

_PROBE_PREFIX: Final[str] = "healthcheck"
_HTTP_TIMEOUT: Final[float] = 15.0
_HTTP_OK: Final[int] = 200


def _log(status: str, message: str) -> None:
    """Single output channel — keep it grep-friendly for CI logs."""
    print(f"[{status}] {message}", flush=True)


def _check_env() -> tuple[str, str, str]:
    """Validate required env vars; exit(2) with a clear message if missing."""
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    bucket = settings.supabase_storage_bucket
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_ROLE_KEY", key),
        )
        if not value
    ]
    if missing:
        _log("FAIL", f"missing required env vars: {', '.join(missing)}")
        sys.exit(2)
    # mypy: at this point both are non-None
    assert url is not None
    assert key is not None
    return url, key, bucket


async def _check_rest(url: str, key: str) -> bool:
    """Confirm PostgREST is reachable and the service-role key authenticates."""
    headers = {"Authorization": f"Bearer {key}", "apikey": key}
    rest_url = f"{url.rstrip('/')}/rest/v1/"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(rest_url, headers=headers)
    except httpx.HTTPError as exc:
        _log("FAIL", f"PostgREST transport error: {exc}")
        return False
    # PostgREST returns 200 on root with a service description.
    if resp.status_code == _HTTP_OK:
        server = resp.headers.get("server", "unknown")
        _log("PASS", f"PostgREST reachable at {rest_url} (server={server})")
        return True
    _log("FAIL", f"PostgREST returned HTTP {resp.status_code}: {resp.text[:200]}")
    return False


def _check_pgvector() -> bool:
    """We didn't ship a Postgres RPC for vector ops; skip with a clear note.

    Returns True so the script can still exit 0 — the spec calls this a
    documented SKIP, not a failure.
    """
    _log("SKIP", "pgvector probe: SKIPPED (no RPC endpoint)")
    return True


async def _check_storage_roundtrip(url: str, key: str, bucket: str) -> bool:
    """Upload -> download -> compare -> delete on a unique probe key."""
    probe_key = f"{_PROBE_PREFIX}/probe-{int(time.time())}-{id(object()):x}.txt"
    payload = f"hello-cloud-{time.time_ns()}".encode()

    storage = SupabaseStorage(
        base_url=url,
        service_role_key=key,
        bucket=bucket,
    )
    try:
        try:
            await storage.upload(probe_key, payload, content_type="text/plain")
        except CloudStorageError as exc:
            _log("FAIL", f"storage upload failed: {exc}")
            return False

        try:
            fetched = await storage.download(probe_key)
        except CloudObjectNotFound:
            _log("FAIL", f"storage download 404 immediately after upload: {probe_key}")
            return False
        except CloudStorageError as exc:
            _log("FAIL", f"storage download failed: {exc}")
            return False

        if fetched != payload:
            _log("FAIL", f"storage round-trip mismatch: sent {len(payload)}B, got {len(fetched)}B")
            return False

        try:
            await storage.delete(probe_key)
        except CloudStorageError as exc:
            # Upload+download already passed; deletion failure is still a FAIL
            # because it leaks objects, but we report it precisely.
            _log("FAIL", f"storage delete failed: {exc}")
            return False

        _log("PASS", f"storage round-trip ok on bucket={bucket} key={probe_key}")
        return True
    finally:
        await storage.aclose()


async def main() -> int:
    url, key, bucket = _check_env()

    rest_ok = await _check_rest(url, key)
    vector_ok = _check_pgvector()
    storage_ok = await _check_storage_roundtrip(url, key, bucket)

    overall_ok = rest_ok and vector_ok and storage_ok
    _log(
        "PASS" if overall_ok else "FAIL",
        f"summary: rest={rest_ok} pgvector={vector_ok} storage={storage_ok}",
    )
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
