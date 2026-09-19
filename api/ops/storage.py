"""MinIO/S3 object storage. Owned by devops engineer 1 — be1 imports this for
book uploads and page renders (S2.6); `delete_prefix` is ETH-2's deletion
primitive.

``boto3`` is not in ``api/pyproject.toml`` (orchestrator-owned; see SCR in
plans/sprint-2/SCR.md) so it is installed straight into the runtime venv in
``api/Dockerfile``, the same stopgap already used there for the test stage's
``pytest``. Delete that layer once the dependency lands at a freeze.
"""

import asyncio
import os
from collections.abc import Iterable
from typing import IO

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from ..config import settings

# The URL reaches the browser, so it must not be permanent.
DEFAULT_PRESIGN_TTL_S = 15 * 60

# Keeps `put_stream` at flat memory regardless of object size, instead of
# buffering the whole upload before sending. Measured against a 200MB file:
# boto3's *threaded* transfer manager holds a working set of tens of MB per
# in-flight part even at concurrency=1 (its queue reads ahead); switching to
# `use_threads=False` — a plain sequential multipart upload in the one worker
# thread `put_stream` already runs on via `asyncio.to_thread` — measured ~9MB
# resident above baseline regardless of file size. Throughput is secondary to
# the flat-memory acceptance criterion here.
MULTIPART_CHUNK_BYTES = 8 * 1024 * 1024


def _scheme() -> str:
    return "https" if settings.minio_secure else "http"


def _endpoint_url() -> str:
    return f"{_scheme()}://{settings.minio_endpoint}"


def _public_endpoint_url() -> str:
    """Where a browser can reach MinIO, for presigning only.

    Not in settings.py (orchestrator-owned); read straight from the
    environment like probes.py's HEALTH_REQUIRED_DEPS. Defaults to the
    in-network endpoint, which is correct for tests/CI where nothing outside
    the compose network ever follows the URL.
    """
    raw = os.environ.get("MINIO_PUBLIC_ENDPOINT")
    if raw:
        return f"{_scheme()}://{raw}"
    return _endpoint_url()


def _make_client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
        # MinIO does not support virtual-hosted-style (bucket.host) addressing
        # by default; path-style (host/bucket) is what both the internal and
        # presigned-for-the-browser clients need.
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


_client = None
_public_client = None


def _internal() -> "boto3.client":
    global _client
    if _client is None:
        _client = _make_client(_endpoint_url())
    return _client


def _public() -> "boto3.client":
    global _public_client
    if _public_client is None:
        _public_client = _make_client(_public_endpoint_url())
    return _public_client


async def put_stream(
    key: str, fileobj: IO[bytes], *, content_type: str | None = None
) -> None:
    """Upload ``fileobj`` (e.g. ``UploadFile.file``) without buffering it whole.

    ``upload_fileobj`` reads in ``MULTIPART_CHUNK_BYTES`` pieces and streams
    each part to MinIO, so a 200MB upload holds flat memory rather than one
    buffer the size of the file.
    """
    extra_args = {"ContentType": content_type} if content_type else None

    def _upload() -> None:
        from boto3.s3.transfer import TransferConfig

        transfer_config = TransferConfig(
            multipart_chunksize=MULTIPART_CHUNK_BYTES,
            use_threads=False,
        )
        _internal().upload_fileobj(
            fileobj,
            settings.minio_bucket,
            key,
            ExtraArgs=extra_args,
            Config=transfer_config,
        )

    await asyncio.to_thread(_upload)


async def exists(key: str) -> bool:
    def _head() -> bool:
        try:
            _internal().head_object(Bucket=settings.minio_bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey"):
                return False
            raise

    return await asyncio.to_thread(_head)


async def presigned_get(key: str, *, expires_in: int = DEFAULT_PRESIGN_TTL_S) -> str:
    """A time-limited GET URL, signed against the browser-reachable endpoint."""

    def _sign() -> str:
        return _public().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.minio_bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    return await asyncio.to_thread(_sign)


async def delete_prefix(prefix: str) -> int:
    """Delete every object under ``prefix``. Returns the count removed."""

    def _delete() -> int:
        client = _internal()
        paginator = client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=settings.minio_bucket, Prefix=prefix):
            objects: Iterable[dict] = page.get("Contents", [])
            batch = [{"Key": obj["Key"]} for obj in objects]
            if not batch:
                continue
            client.delete_objects(
                Bucket=settings.minio_bucket, Delete={"Objects": batch}
            )
            deleted += len(batch)
        return deleted

    return await asyncio.to_thread(_delete)
