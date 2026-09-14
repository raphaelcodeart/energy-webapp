import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.integrations import google_drive
from app.domains.integrations.google_drive import GoogleDriveError
from app.domains.integrations.schemas import (
    GoogleDriveAuthorizeUrlRead,
    GoogleDriveCallbackRequest,
    GoogleDriveCredentialsUpdate,
    GoogleDriveStatusRead,
)
from app.domains.organizations.models import Organization

router = APIRouter(prefix="/integrations", tags=["integrations"])


async def _status_read(db: AsyncSession, *, organization_id: uuid.UUID) -> GoogleDriveStatusRead:
    state = await google_drive.get_status(db, organization_id=organization_id)
    return GoogleDriveStatusRead(
        configured=state.configured,
        connected=state.connected,
        account_email=state.account_email,
        connected_at=state.connected_at,
        parent_folder_id=state.parent_folder_id,
        redirect_uri=state.redirect_uri,
        client_id=state.client_id,
        client_secret_configured=state.client_secret_configured,
    )


@router.get("/google-drive", response_model=GoogleDriveStatusRead)
async def get_google_drive_status(
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> GoogleDriveStatusRead:
    return await _status_read(db, organization_id=current_user.organization_id)


@router.patch("/google-drive/credentials", response_model=GoogleDriveStatusRead)
async def update_google_drive_credentials(
    payload: GoogleDriveCredentialsUpdate,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> GoogleDriveStatusRead:
    """Client ID, secret e cartella di destinazione. Come per le chiavi
    Stripe, un campo omesso resta com'era: una PATCH che tocca solo la
    cartella non cancella il secret."""
    org = await db.get(Organization, current_user.organization_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organizzazione non trovata")

    updates = payload.model_dump(exclude_unset=True)
    mapped = {}
    if "client_id" in updates:
        mapped[google_drive.SETTING_CLIENT_ID] = (updates["client_id"] or "").strip() or None
    if "client_secret" in updates:
        mapped[google_drive.SETTING_CLIENT_SECRET] = (updates["client_secret"] or "").strip() or None
    if "parent_folder_id" in updates:
        mapped[google_drive.SETTING_PARENT_FOLDER_ID] = (updates["parent_folder_id"] or "").strip() or None

    org.settings = {**(org.settings or {}), **mapped}
    await db.commit()
    return await _status_read(db, organization_id=current_user.organization_id)


@router.post("/google-drive/authorize-url", response_model=GoogleDriveAuthorizeUrlRead)
async def get_google_drive_authorize_url(
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> GoogleDriveAuthorizeUrlRead:
    try:
        url = await google_drive.build_authorize_url(db, organization_id=current_user.organization_id)
    except GoogleDriveError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return GoogleDriveAuthorizeUrlRead(url=url)


@router.post("/google-drive/callback", response_model=GoogleDriveStatusRead)
async def complete_google_drive_connection(
    payload: GoogleDriveCallbackRequest,
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> GoogleDriveStatusRead:
    try:
        await google_drive.complete_connection(
            db, organization_id=current_user.organization_id, code=payload.code, state=payload.state
        )
    except GoogleDriveError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _status_read(db, organization_id=current_user.organization_id)


@router.delete("/google-drive", response_model=GoogleDriveStatusRead)
async def disconnect_google_drive(
    current_user: CurrentUser = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> GoogleDriveStatusRead:
    await google_drive.disconnect(db, organization_id=current_user.organization_id)
    return await _status_read(db, organization_id=current_user.organization_id)
