import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.storage import UploadValidationError
from app.domains.documentation import service as documentation_service
from app.domains.documentation.schemas import (
    DocumentationPostCreate,
    DocumentationPostRead,
    DocumentationPostUpdate,
)

router = APIRouter(prefix="/documentation", tags=["documentation"])


@router.get("", response_model=list[DocumentationPostRead])
async def get_feed(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentationPostRead]:
    """Published posts visible to the caller's own roles -- the feed a customer
    or promoter sees in their dashboard. Not permission-gated (unlike
    /documentation/admin): every logged-in user can see their own feed, the
    same way GET /network/agents/me needs no network.* permission."""
    audiences = documentation_service.audiences_for_roles(current_user.roles)
    posts = await documentation_service.list_feed(
        db, organization_id=current_user.organization_id, audiences=audiences
    )
    return [DocumentationPostRead.model_validate(p) for p in posts]


@router.get("/admin", response_model=list[DocumentationPostRead])
async def list_all_posts(
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentationPostRead]:
    """Every post regardless of audience/status -- the admin management screen."""
    posts = await documentation_service.list_all(db, organization_id=current_user.organization_id)
    return [DocumentationPostRead.model_validate(p) for p in posts]


@router.post("", response_model=DocumentationPostRead, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: DocumentationPostCreate,
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> DocumentationPostRead:
    if payload.audience not in ("CUSTOMER", "PROMOTER", "BOTH"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "audience must be one of CUSTOMER, PROMOTER, BOTH")
    post = await documentation_service.create_post(
        db,
        organization_id=current_user.organization_id,
        title=payload.title,
        body=payload.body,
        audience=payload.audience,
        video_url=payload.video_url,
        actor_user_id=current_user.user_id,
    )
    return DocumentationPostRead.model_validate(post)


@router.patch("/{post_id}", response_model=DocumentationPostRead)
async def update_post(
    post_id: uuid.UUID,
    payload: DocumentationPostUpdate,
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> DocumentationPostRead:
    if payload.audience is not None and payload.audience not in ("CUSTOMER", "PROMOTER", "BOTH"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "audience must be one of CUSTOMER, PROMOTER, BOTH")
    if payload.status is not None and payload.status not in ("PUBLISHED", "ARCHIVED"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status must be one of PUBLISHED, ARCHIVED")
    post = await documentation_service.update_post(
        db,
        organization_id=current_user.organization_id,
        post_id=post_id,
        title=payload.title,
        body=payload.body,
        audience=payload.audience,
        status_value=payload.status,
        video_url=payload.video_url,
        actor_user_id=current_user.user_id,
    )
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return DocumentationPostRead.model_validate(post)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await documentation_service.delete_post(
        db, organization_id=current_user.organization_id, post_id=post_id, actor_user_id=current_user.user_id
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")


@router.post("/{post_id}/image", response_model=DocumentationPostRead)
async def upload_post_image(
    post_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> DocumentationPostRead:
    file_bytes = await file.read()
    try:
        post = await documentation_service.set_post_image(
            db,
            organization_id=current_user.organization_id,
            post_id=post_id,
            file_bytes=file_bytes,
            content_type=file.content_type or "",
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return DocumentationPostRead.model_validate(post)


@router.post("/{post_id}/pdf", response_model=DocumentationPostRead)
async def upload_post_pdf(
    post_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("documentation.manage")),
    db: AsyncSession = Depends(get_db),
) -> DocumentationPostRead:
    file_bytes = await file.read()
    try:
        post = await documentation_service.set_post_pdf(
            db,
            organization_id=current_user.organization_id,
            post_id=post_id,
            file_bytes=file_bytes,
            content_type=file.content_type or "",
            original_filename=file.filename or "documento.pdf",
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return DocumentationPostRead.model_validate(post)
