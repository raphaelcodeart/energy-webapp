import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

settings = get_settings()
password_hasher = PasswordHash.recommended()  # Argon2id by default


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_hasher.verify(plain_password, password_hash)


def create_access_token(*, subject: str, organization_id: str, roles: list[str]) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "org_id": organization_id,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": secrets.token_urlsafe(16),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_refresh_token() -> str:
    """Opaque random token handed to the client; only its hash is ever persisted."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


def generate_password_reset_token() -> str:
    """Same shape as a refresh token (opaque, high-entropy, hashed at rest) --
    separate function only so call sites read clearly, not because the
    underlying mechanism differs."""
    return secrets.token_urlsafe(32)


def hash_password_reset_token(token: str) -> str:
    return hash_refresh_token(token)
