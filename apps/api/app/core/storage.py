"""Object storage, two buckets with deliberately different access models:

- "lial-media" (s3_bucket_media): PUBLIC-read, profile/product photos. Served
  to browsers via nginx proxying directly to MinIO
  (infrastructure/nginx/nginx.conf `location /media/`) -- not sensitive, meant
  to be trivially embeddable as `<img src>`.
- "lial-documents" (s3_bucket_documents): PRIVATE, real customer documents
  (identity, fiscal code, utility bills, chamber-of-commerce registration).
  No bucket policy grants anonymous access -- the ONLY way to read an object
  is a short-lived presigned URL minted server-side after an authorization
  check (see documents/service.py), and even that presigned URL is proxied
  through nginx's `location /lial-documents/` (Session 14), which forwards
  to MinIO with a fixed internal Host header so the signature (computed
  against the internal endpoint) still validates -- see
  server-migration-guide.md §8 for why that Host rewrite is necessary. A
  presigned URL expires in minutes and is never linked from anywhere a
  search engine could crawl, so it is never indexable.

Backed by the MinIO instance already running in this stack
(docker-compose.dev.yml) but previously unused by any application code --
boto3 was a declared dependency with nothing calling it until Session 13.
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


def ensure_documents_bucket() -> None:
    """Idempotent, mirrors ensure_media_bucket() but DELIBERATELY sets no
    bucket policy at all -- MinIO buckets are private by default (no
    anonymous access of any kind) until a policy explicitly grants it, so
    "do nothing" IS the correct private configuration. Called once at API
    startup alongside ensure_media_bucket()."""
    client = _get_client()
    bucket = settings.s3_bucket_documents
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def upload_document(*, file_bytes: bytes, content_type: str, key_prefix: str) -> str:
    """Uploads to the PRIVATE documents bucket. Returns only the opaque
    storage key -- never a URL -- callers persist the key and mint a
    presigned URL on demand via generate_presigned_document_url(), never
    construct a URL themselves."""
    from app.domains.documents.models import ALLOWED_DOCUMENT_CONTENT_TYPES, MAX_DOCUMENT_BYTES

    if content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_DOCUMENT_BYTES:
        raise UploadValidationError("File too large (max 15 MB)")

    extension = mimetypes.guess_extension(content_type) or ".bin"
    key = f"{key_prefix}/{uuid.uuid4().hex}{extension}"

    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket_documents, Key=key, Body=file_bytes, ContentType=content_type,
    )
    return key


def generate_presigned_document_url(*, storage_key: str, expires_in_seconds: int = 300) -> str:
    """A time-limited, cryptographically signed URL good for exactly one
    object, expiring in `expires_in_seconds` (default 5 minutes) -- the only
    way anything ever reads from the private documents bucket. The client is
    configured with the INTERNAL endpoint_url (http://minio:9000), so the
    signature nginx must validate is computed against Host: minio:9000 --
    nginx's `location /lial-documents/` forces that exact Host header
    regardless of what the public domain's hostname is, which is why this
    works at all through a reverse proxy. Only the scheme+host of the
    returned URL are rewritten to the public domain; path and query
    (including the signature) are left byte-for-byte untouched."""
    client = _get_client()
    internal_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_documents, "Key": storage_key},
        ExpiresIn=expires_in_seconds,
    )
    return internal_url.replace(settings.s3_endpoint_url, settings.public_app_base_url, 1)
