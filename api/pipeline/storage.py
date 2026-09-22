"""Streaming object storage against MinIO's S3-compatible API.

``api/ops/storage.py`` (do1, S2.15) is the eventual home for this — a shared
``put_stream``/``presigned_get``/``exists``/``delete_prefix`` surface that both
backend agents import. It has not landed in this worktree yet, and every S2
story here needs it (upload, fetch-to-parse, page render caching), so this
module is a stopgap with the same four names plus the internal ``get_object``
the ingestion stages need that a browser-facing presigned URL cannot serve.
Swapping the import for ``api.ops.storage`` once it exists should not require
touching a call site — see ``plans/sprint-2/HANDOFF.md``.

No new dependency was added for this: MinIO's API is plain S3 SigV4 over
HTTP, and ``httpx`` is already pulled in transitively by ``fastapi[standard]``.
"""

import hashlib
import hmac
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import anyio
import httpx

from ..config.settings import Settings
from ..config.settings import settings as default_settings

_REGION = "us-east-1"
_SERVICE = "s3"
_ALGORITHM = "AWS4-HMAC-SHA256"
_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"
_READ_CHUNK = 1 << 20


class StorageError(Exception):
    """An object-storage request did not succeed."""


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str) -> bytes:
    key_date = _hmac(f"AWS4{secret_key}".encode(), date_stamp)
    key_region = _hmac(key_date, _REGION)
    key_service = _hmac(key_region, _SERVICE)

    return _hmac(key_service, "aws4_request")


class ObjectStore:
    """A minimal async S3-compatible client, scoped to one bucket.

    Args:
        settings: Source of the endpoint, credentials and bucket. Defaults to
            the process-wide settings so call sites do not have to thread one
            through everywhere.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings

    @property
    def _base_url(self) -> str:
        scheme = "https" if self.settings.minio_secure else "http"

        return f"{scheme}://{self.settings.minio_endpoint}"

    def _host(self) -> str:
        return self.settings.minio_endpoint

    def _canonical_request(
        self,
        method: str,
        path: str,
        query: str,
        headers: dict[str, str],
        payload_hash: str,
    ) -> tuple[str, str]:
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(
            f"{key}:{headers[key]}\n" for key in sorted(headers)
        )
        canonical_request = "\n".join(
            [
                method,
                quote(path, safe="/"),
                query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )

        return canonical_request, signed_headers

    def _authorization(
        self,
        *,
        method: str,
        path: str,
        query: str = "",
        headers: dict[str, str],
        payload_hash: str,
        amz_date: str,
        date_stamp: str,
    ) -> str:
        canonical_request, signed_headers = self._canonical_request(
            method, path, query, headers, payload_hash
        )
        credential_scope = f"{date_stamp}/{_REGION}/{_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                _ALGORITHM,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            self._signing_key(date_stamp), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        access_key = self.settings.minio_access_key

        return (
            f"{_ALGORITHM} Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def _signing_key(self, date_stamp: str) -> bytes:
        return _signing_key(
            self.settings.minio_secret_key.get_secret_value(), date_stamp
        )

    def _signed_headers(
        self,
        method: str,
        path: str,
        payload_hash: str,
        extra: dict[str, str],
        *,
        query: str = "",
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        headers = {
            "host": self._host(),
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            **extra,
        }
        headers["authorization"] = self._authorization(
            method=method,
            path=path,
            query=query,
            headers=headers,
            payload_hash=payload_hash,
            amz_date=amz_date,
            date_stamp=date_stamp,
        )

        return headers

    def _object_path(self, key: str) -> str:
        return f"/{self.settings.minio_bucket}/{key}"

    async def put_stream(
        self, key: str, source: Path, *, content_type: str = "application/octet-stream"
    ) -> None:
        """Upload a local file to ``key``, streaming it in fixed-size chunks.

        Args:
            key: Object key, relative to the configured bucket.
            source: Local file to upload. Never loaded into memory whole.
            content_type: MIME type recorded on the object.

        Raises:
            StorageError: If the upload does not succeed.
        """
        path = self._object_path(key)
        length = source.stat().st_size
        headers = self._signed_headers(
            "PUT",
            path,
            _UNSIGNED_PAYLOAD,
            {"content-type": content_type, "content-length": str(length)},
        )

        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.put(
                f"{self._base_url}{path}",
                content=_read_in_chunks(source),
                headers=headers,
            )

        if response.status_code >= 300:
            raise StorageError(
                f"PUT {key} failed: {response.status_code} {response.text[:200]}"
            )

    async def put_bytes(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> None:
        """Upload an in-memory payload to ``key``.

        For objects small enough that a temp file would be pure overhead — a
        rendered page PNG or its span-metadata sidecar (S2.6), not a 200 MB
        source PDF; see ``put_stream`` for that.

        Raises:
            StorageError: If the upload does not succeed.
        """
        path = self._object_path(key)
        headers = self._signed_headers(
            "PUT",
            path,
            _UNSIGNED_PAYLOAD,
            {"content-type": content_type, "content-length": str(len(data))},
        )

        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.put(
                f"{self._base_url}{path}", content=data, headers=headers
            )

        if response.status_code >= 300:
            raise StorageError(
                f"PUT {key} failed: {response.status_code} {response.text[:200]}"
            )

    async def get_object(self, key: str, dest: Path) -> None:
        """Download ``key`` to a local path, streaming the response body.

        Raises:
            StorageError: If the object does not exist or the request fails.
        """
        path = self._object_path(key)
        headers = self._signed_headers("GET", path, _UNSIGNED_PAYLOAD, {})

        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "GET", f"{self._base_url}{path}", headers=headers
            ) as response,
        ):
            if response.status_code >= 300:
                body = await response.aread()
                raise StorageError(
                    f"GET {key} failed: {response.status_code} {body[:200]!r}"
                )

            def _open() -> object:
                return dest.open("wb")

            handle = await anyio.to_thread.run_sync(_open)
            try:
                async for part in response.aiter_bytes(_READ_CHUNK):
                    await anyio.to_thread.run_sync(handle.write, part)
            finally:
                await anyio.to_thread.run_sync(handle.close)

    async def get_bytes(self, key: str) -> bytes:
        """Download ``key`` fully into memory.

        For small cached objects only (see ``put_bytes``) — a page render's
        span metadata, not the source PDF.

        Raises:
            StorageError: If the object does not exist or the request fails.
        """
        path = self._object_path(key)
        headers = self._signed_headers("GET", path, _UNSIGNED_PAYLOAD, {})

        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.get(f"{self._base_url}{path}", headers=headers)

        if response.status_code >= 300:
            raise StorageError(
                f"GET {key} failed: {response.status_code} {response.text[:200]!r}"
            )

        return response.content

    async def exists(self, key: str) -> bool:
        """Return whether ``key`` is present in the bucket."""
        path = self._object_path(key)
        headers = self._signed_headers("HEAD", path, _UNSIGNED_PAYLOAD, {})

        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.head(f"{self._base_url}{path}", headers=headers)

        return response.status_code == 200

    def presigned_get(self, key: str, *, expires_in: int = 900) -> str:
        """Return a time-limited, browser-usable GET URL for ``key``.

        Args:
            key: Object key.
            expires_in: Seconds until the URL stops working. MinIO's own
                ceiling is seven days; the page-render use case wants minutes,
                not days, since the URL reaches the browser (S2.6).
        """
        path = self._object_path(key)
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        credential_scope = f"{date_stamp}/{_REGION}/{_SERVICE}/aws4_request"
        access_key = self.settings.minio_access_key
        query_pairs = [
            ("X-Amz-Algorithm", _ALGORITHM),
            ("X-Amz-Credential", f"{access_key}/{credential_scope}"),
            ("X-Amz-Date", amz_date),
            ("X-Amz-Expires", str(expires_in)),
            ("X-Amz-SignedHeaders", "host"),
        ]
        canonical_query = "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(query_pairs)
        )
        canonical_request, _ = self._canonical_request(
            "GET", path, canonical_query, {"host": self._host()}, _UNSIGNED_PAYLOAD
        )
        string_to_sign = "\n".join(
            [
                _ALGORITHM,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            self._signing_key(date_stamp), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        query_pairs.append(("X-Amz-Signature", signature))
        final_query = "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in query_pairs
        )

        return f"{self._base_url}{path}?{final_query}"

    async def delete_prefix(self, prefix: str) -> None:
        """Delete every object whose key starts with ``prefix``."""
        keys = await self._list_prefix(prefix)

        async with httpx.AsyncClient(timeout=None) as client:
            for key in keys:
                path = self._object_path(key)
                headers = self._signed_headers("DELETE", path, _UNSIGNED_PAYLOAD, {})
                response = await client.delete(
                    f"{self._base_url}{path}", headers=headers
                )
                if response.status_code >= 300 and response.status_code != 404:
                    raise StorageError(f"DELETE {key} failed: {response.status_code}")

    async def _list_prefix(self, prefix: str) -> list[str]:
        import xml.etree.ElementTree as ElementTree

        path = f"/{self.settings.minio_bucket}"
        keys: list[str] = []
        continuation: str | None = None

        async with httpx.AsyncClient(timeout=None) as client:
            while True:
                query_pairs = [("list-type", "2"), ("prefix", prefix)]
                if continuation:
                    query_pairs.append(("continuation-token", continuation))
                canonical_query = "&".join(
                    f"{quote(k, safe='')}={quote(v, safe='')}"
                    for k, v in sorted(query_pairs)
                )
                headers = self._signed_headers(
                    "GET", path, _UNSIGNED_PAYLOAD, {}, query=canonical_query
                )
                response = await client.get(
                    f"{self._base_url}{path}?{canonical_query}",
                    headers=headers,
                )
                if response.status_code >= 300:
                    raise StorageError(f"LIST {prefix} failed: {response.status_code}")

                root = ElementTree.fromstring(response.text)
                ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
                keys.extend(
                    element.text or ""
                    for element in root.findall(".//s3:Contents/s3:Key", ns)
                )
                truncated = root.findtext(
                    "s3:IsTruncated", default="false", namespaces=ns
                )
                if truncated != "true":
                    break
                continuation = root.findtext("s3:NextContinuationToken", namespaces=ns)
                if not continuation:
                    break

        return keys


def _read_in_chunks(path: Path, chunk_size: int = _READ_CHUNK) -> AsyncIterator[bytes]:
    async def _iterate() -> AsyncIterator[bytes]:
        def _open_and_read_first() -> tuple[object, bytes]:
            handle = path.open("rb")

            return handle, handle.read(chunk_size)

        handle, data = await anyio.to_thread.run_sync(_open_and_read_first)
        try:
            while data:
                yield data
                data = await anyio.to_thread.run_sync(handle.read, chunk_size)
        finally:
            await anyio.to_thread.run_sync(handle.close)

    return _iterate()


store = ObjectStore()
