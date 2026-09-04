import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import rate_limit
from app.domains.auth import service as auth_service
from app.domains.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MeRead,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "lial_refresh_token"


@router.get("/me", response_model=MeRead)
async def get_me(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeRead:
    """Live roles for the current user -- unlike the access token's own baked-in
    roles (set once at login/refresh, see authenticate()), this always reflects
    the current DB state. Needed for anything that can change roles mid-session
    without forcing a re-login: 'lavora con noi' auto-activation grants
    PROMOTER immediately, and an admin deactivating a promoter revokes it --
    the customer/promoter area switcher (app-shell.tsx) reads this so it
    appears/disappears right away instead of waiting for the 15-minute access
    token to naturally expire and refresh."""
    from app.domains.rbac.service import get_roles_for_user

    roles = await get_roles_for_user(db, user_id=current_user.user_id, organization_id=current_user.organization_id)
    return MeRead(roles=roles)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/auth",
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", max_requests=10, window_seconds=60))])
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    try:
        access_token, refresh_token = await auth_service.authenticate(
            db,
            organization_id=uuid.UUID(payload.organization_id),
            email=payload.email,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.AccountLockedError as exc:
        raise HTTPException(status.HTTP_423_LOCKED, str(exc)) from exc
    except auth_service.AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", max_requests=5, window_seconds=60))],
)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Public, invite-only self-registration -- a referral_code (from a promoter's
    shared link) is required, no exceptions. Does not auto-login: the customer is
    redirected to /login to authenticate normally, consistent with every other
    account in this system."""
    try:
        await auth_service.register_with_referral(
            db, organization_id=uuid.UUID(payload.organization_id), payload=payload
        )
    except auth_service.RegistrationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    organization_id: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    try:
        access_token, new_refresh_token = await auth_service.rotate_refresh_token(
            db, organization_id=uuid.UUID(organization_id), refresh_token=refresh_token
        )
    except auth_service.AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        await auth_service.revoke_session(db, refresh_token=refresh_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("forgot-password", max_requests=5, window_seconds=300))],
)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Always returns 202 regardless of whether the email exists -- see
    auth_service.request_password_reset for why."""
    await auth_service.request_password_reset(
        db,
        organization_id=uuid.UUID(payload.organization_id),
        email=payload.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True}


@router.post(
    "/reset-password",
    dependencies=[Depends(rate_limit("reset-password", max_requests=10, window_seconds=300))],
)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    except auth_service.PasswordResetError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}
