import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_access_token
from app.domains.rbac.service import get_permission_codes_for_user


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    roles: list[str]


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return auth_header.removeprefix("Bearer ")


async def get_current_user(request: Request) -> CurrentUser:
    token = _extract_bearer_token(request)
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    return CurrentUser(
        user_id=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["org_id"]),
        roles=payload.get("roles", []),
    )


def require_permission(permission_code: str):
    """FastAPI dependency factory: `Depends(require_permission("contracts.approve"))`.

    This is the single enforcement point for RBAC -- routers never re-implement
    their own permission logic. ABAC (branch/ownership) checks happen in the
    relevant domain's service layer, since only that layer has the entity loaded.
    """

    async def _checker(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        granted = await get_permission_codes_for_user(
            db, user_id=current_user.user_id, organization_id=current_user.organization_id
        )
        if permission_code not in granted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission_code}")
        return current_user

    return _checker
