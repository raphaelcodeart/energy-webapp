"""Object storage for user-uploaded photos (customer/promoter profile photos,
product photos) -- a separate, PUBLIC-read bucket from the private documents
bucket (s3_bucket_documents, reserved for actual identity/contract documents
and never exposed this way). Backed by the MinIO instance already running in
this stack (docker-compose.dev.yml) but previously unused by any application
code -- boto3 was a declared dependency with nothing calling it.

Objects in the media bucket are served to browsers via nginx proxying
directly to MinIO (infrastructure/nginx/nginx.conf `location /media/`), not
through this API -- this module only handles writes (upload/delete); reads
are a static file server, no Python involved.
"""

import mimetypes
import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()

ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB -- profile/product photos, not documents

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
    return _client


class UploadValidationError(Exception):
    pass


def ensure_media_bucket() -> None:
    """Idempotent: creates the public-media bucket and its anonymous-read
    policy if they don't already exist. Called once at API startup (see
    main.py) -- MinIO doesn't auto-create buckets, and there's no separate
    init container in this stack, so the app owns its own bucket setup the
    same way it owns its own schema migrations."""
    client = _get_client()
    bucket = settings.s3_bucket_media
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)

    policy = f"""{{
        "Version": "2012-10-17",
        "Statement": [
            {{
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": ["arn:aws:s3:::{bucket}/*"]
            }}
        ]
    }}"""
    client.put_bucket_policy(Bucket=bucket, Policy=policy)


def upload_media(*, file_bytes: bytes, content_type: str, key_prefix: str) -> str:
    """Uploads to the public bucket under a fresh random key (old uploads for
    the same entity are never overwritten in place -- the caller just points
    its photo_url column at the new key, orphaning the old object; not worth
    a cleanup job for a handful of KB images). Returns the PUBLIC url the
    browser can load directly (through nginx's /media/ proxy, never MinIO's
    internal docker-network address)."""
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("File too large (max 5 MB)")

    extension = mimetypes.guess_extension(content_type) or ".bin"
    key = f"{key_prefix}/{uuid.uuid4().hex}{extension}"

    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket_media, Key=key, Body=file_bytes, ContentType=content_type,
    )
    return f"{settings.public_app_base_url}/media/{key}"
