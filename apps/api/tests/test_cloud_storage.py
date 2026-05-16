"""Phase 3 unit tests for the Supabase Storage adapter.

Network is stubbed end-to-end with pytest-httpx so these run in CI without
any live Supabase project.
"""

from __future__ import annotations

import httpx
import pytest
from foundry_api.cloud import (
    CloudObjectNotFound,
    CloudStorageError,
    SupabaseStorage,
)
from pytest_httpx import HTTPXMock

_BASE_URL = "https://project.supabase.co"
_KEY = "sb_secret_test_only_not_real"
_BUCKET = "components"


def _make_storage(client: httpx.AsyncClient) -> SupabaseStorage:
    return SupabaseStorage(
        base_url=_BASE_URL,
        service_role_key=_KEY,
        bucket=_BUCKET,
        client=client,
    )


@pytest.mark.phase3
async def test_upload_sends_service_role_headers_and_returns_key(httpx_mock: HTTPXMock) -> None:
    # Arrange
    object_key = "datasheets/lm317.pdf"
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{object_key}",
        status_code=200,
        json={"Key": object_key},
    )
    async with httpx.AsyncClient() as client:
        storage = _make_storage(client)

        # Act
        returned = await storage.upload(
            object_key, b"%PDF-1.4\n...", content_type="application/pdf"
        )

    # Assert
    assert returned == object_key
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    assert request.headers["apikey"] == _KEY
    assert request.headers["Content-Type"] == "application/pdf"
    assert request.headers["x-upsert"] == "true"


@pytest.mark.phase3
async def test_download_returns_body_bytes(httpx_mock: HTTPXMock) -> None:
    # Arrange
    object_key = "datasheets/lm317.pdf"
    payload = b"\x00\x01\x02binary-payload\xff"
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{object_key}",
        status_code=200,
        content=payload,
    )

    # Act
    async with httpx.AsyncClient() as client:
        storage = _make_storage(client)
        fetched = await storage.download(object_key)

    # Assert
    assert fetched == payload


@pytest.mark.phase3
async def test_download_raises_on_404(httpx_mock: HTTPXMock) -> None:
    # Arrange
    object_key = "datasheets/missing.pdf"
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{object_key}",
        status_code=404,
        json={"message": "not found"},
    )

    # Act / Assert
    async with httpx.AsyncClient() as client:
        storage = _make_storage(client)
        with pytest.raises(CloudObjectNotFound):
            await storage.download(object_key)


@pytest.mark.phase3
async def test_exists_true_false(httpx_mock: HTTPXMock) -> None:
    # Arrange
    present_key = "datasheets/present.pdf"
    absent_key = "datasheets/absent.pdf"
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{present_key}",
        status_code=200,
        content=b"ok",
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{absent_key}",
        status_code=404,
        json={"message": "not found"},
    )

    # Act
    async with httpx.AsyncClient() as client:
        storage = _make_storage(client)
        present = await storage.exists(present_key)
        absent = await storage.exists(absent_key)

    # Assert
    assert present is True
    assert absent is False


@pytest.mark.phase3
async def test_upload_non_2xx_raises_cloud_storage_error(httpx_mock: HTTPXMock) -> None:
    # Arrange
    object_key = "datasheets/broken.pdf"
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/storage/v1/object/{_BUCKET}/{object_key}",
        status_code=500,
        text="boom",
    )

    # Act / Assert
    async with httpx.AsyncClient() as client:
        storage = _make_storage(client)
        with pytest.raises(CloudStorageError):
            await storage.upload(object_key, b"x", content_type="application/pdf")
