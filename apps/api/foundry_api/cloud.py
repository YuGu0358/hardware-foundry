"""Supabase Storage adapter for the `components` bucket.

Why httpx, not supabase-py: supabase-py drags realtime + websockets which we
don't need for the simple upload/download/delete path. A thin REST wrapper
keeps the dependency surface — and audit story — minimal.

Auth model: Storage REST requires BOTH `Authorization: Bearer <key>` and an
`apikey: <key>` header. We use the service-role key so the adapter can read
and write to private buckets server-side; never expose this key to clients.
"""

from __future__ import annotations

from typing import Final

import httpx
import structlog

from foundry_api.config import Settings, settings

_LOG = structlog.get_logger(__name__)

# Supabase Storage REST path under SUPABASE_URL.
_STORAGE_PATH: Final[str] = "/storage/v1/object"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

# HTTP status helpers — declared as named constants to satisfy strict lint
# (no magic numbers) and to keep status checks self-documenting.
_HTTP_OK: Final[int] = 200
_HTTP_NOT_FOUND: Final[int] = 404
_HTTP_CLIENT_ERROR_FLOOR: Final[int] = 400


class CloudStorageError(RuntimeError):
    """Base class for cloud storage failures surfaced to callers."""


class CloudObjectNotFound(CloudStorageError):
    """Raised when the requested object key does not exist (HTTP 404)."""


class SupabaseStorage:
    """Thin async wrapper over Supabase Storage REST for one bucket.

    Constructed via :func:`get_cloud_storage` so callers share a single
    underlying ``httpx.AsyncClient`` (connection pool reuse). All operations
    raise :class:`CloudStorageError` (or its subclass) on failure — no silent
    fallbacks.
    """

    def __init__(
        self,
        *,
        base_url: str,
        service_role_key: str,
        bucket: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bucket = bucket
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }
        # Allow injection for tests; otherwise own a long-lived client.
        self._client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS)
        self._owns_client = client is None

    @property
    def bucket(self) -> str:
        return self._bucket

    def _object_url(self, key: str) -> str:
        # Storage REST: /storage/v1/object/<bucket>/<key>
        return f"{self._base_url}{_STORAGE_PATH}/{self._bucket}/{key}"

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload bytes under ``key``; returns the same key on success.

        Uses POST with ``x-upsert: true`` so re-uploading the same key
        overwrites instead of 409-ing — simpler semantics for our healthcheck
        and supplier-adapter retry loops.
        """
        headers = {**self._headers, "Content-Type": content_type, "x-upsert": "true"}
        try:
            resp = await self._client.post(self._object_url(key), content=data, headers=headers)
        except httpx.HTTPError as exc:
            raise CloudStorageError(f"upload transport error for {key}: {exc}") from exc
        if resp.status_code >= _HTTP_CLIENT_ERROR_FLOOR:
            raise CloudStorageError(
                f"upload failed for {key}: HTTP {resp.status_code} {resp.text}"
            )
        _LOG.debug("cloud.upload", bucket=self._bucket, key=key, bytes=len(data))
        return key

    async def download(self, key: str) -> bytes:
        """Fetch object bytes; raises :class:`CloudObjectNotFound` on 404."""
        try:
            resp = await self._client.get(self._object_url(key), headers=self._headers)
        except httpx.HTTPError as exc:
            raise CloudStorageError(f"download transport error for {key}: {exc}") from exc
        if resp.status_code == _HTTP_NOT_FOUND:
            raise CloudObjectNotFound(f"no such object: {self._bucket}/{key}")
        if resp.status_code >= _HTTP_CLIENT_ERROR_FLOOR:
            raise CloudStorageError(
                f"download failed for {key}: HTTP {resp.status_code} {resp.text}"
            )
        return resp.content

    async def delete(self, key: str) -> None:
        """Delete object; treats 404 as success (idempotent cleanup)."""
        try:
            resp = await self._client.delete(self._object_url(key), headers=self._headers)
        except httpx.HTTPError as exc:
            raise CloudStorageError(f"delete transport error for {key}: {exc}") from exc
        if resp.status_code == _HTTP_NOT_FOUND:
            return
        if resp.status_code >= _HTTP_CLIENT_ERROR_FLOOR:
            raise CloudStorageError(
                f"delete failed for {key}: HTTP {resp.status_code} {resp.text}"
            )

    async def exists(self, key: str) -> bool:
        """Return True iff the object exists.

        Supabase Storage's HEAD endpoint is flaky for some bucket configs, so
        we issue a small GET and inspect the status. 200 = present, 404 =
        absent; anything else is propagated as :class:`CloudStorageError`.
        """
        try:
            resp = await self._client.get(self._object_url(key), headers=self._headers)
        except httpx.HTTPError as exc:
            raise CloudStorageError(f"exists transport error for {key}: {exc}") from exc
        if resp.status_code == _HTTP_OK:
            return True
        if resp.status_code == _HTTP_NOT_FOUND:
            return False
        raise CloudStorageError(
            f"exists check failed for {key}: HTTP {resp.status_code} {resp.text}"
        )

    async def aclose(self) -> None:
        """Close the owned ``httpx.AsyncClient`` if we created it."""
        if self._owns_client:
            await self._client.aclose()


# Cache held in a single-element list to avoid `global` in get_cloud_storage
# (ruff PLW0603) while still memoizing across calls.
_cached_storage: list[SupabaseStorage] = []


def get_cloud_storage(cfg: Settings | None = None) -> SupabaseStorage:
    """Return a process-wide :class:`SupabaseStorage` for the configured bucket.

    Fails loudly when the required Supabase env vars are missing — the
    contract is "if you ask for cloud storage, you must have configured it".
    """
    if _cached_storage:
        return _cached_storage[0]

    s = cfg or settings
    if not s.supabase_url or not s.supabase_service_role_key:
        raise CloudStorageError(
            "Supabase not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
        )

    storage = SupabaseStorage(
        base_url=s.supabase_url,
        service_role_key=s.supabase_service_role_key,
        bucket=s.supabase_storage_bucket,
    )
    _cached_storage.append(storage)
    return storage


def _reset_cached_storage_for_tests() -> None:
    """Test hook to drop the module-level singleton between cases."""
    _cached_storage.clear()
