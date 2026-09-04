import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import ALLOWED_IMAGE_CONTENT_TYPES, upload_documentation_attachment
from app.domains.audit import service as audit_service
from app.domains.documentation.models import DocumentationPost


class DocumentationError(Exception):
    pass


def audiences_for_roles(roles: list[str]) -> list[str]:
    """Which audiences a feed reader should see, from their own roles -- a
    plain CUSTOMER sees CUSTOMER+BOTH, a PROMOTER sees PROMOTER+BOTH, and
    someone holding both roles (e.g. a customer approved as a promoter, see
    network/service.py apply_as_promoter) sees everything meant for either."""
    audiences: set[str] = {"BOTH"}
    if "CUSTOMER" in roles:
        audiences.add("CUSTOMER")
    if "PROMOTER" in roles:
        audiences.add("PROMOTER")
    return list(audiences)


async def list_feed(db: AsyncSession, *, organization_id: uuid.UUID, audiences: list[str]) -> list[DocumentationPost]:
    stmt = (
        select(DocumentationPost)
        .where(
            DocumentationPost.organization_id == organization_id,
            DocumentationPost.status == "PUBLISHED",
            DocumentationPost.audience.in_(audiences),
        )
        .order_by(DocumentationPost.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_all(db: AsyncSession, *, organization_id: uuid.UUID) -> list[DocumentationPost]:
    """Unfiltered by audience/status -- the admin management list."""
    stmt = (
        select(DocumentationPost)
        .where(DocumentationPost.organization_id == organization_id)
        .order_by(DocumentationPost.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_post(db: AsyncSession, *, organization_id: uuid.UUID, post_id: uuid.UUID) -> DocumentationPost | None:
    post = await db.get(DocumentationPost, post_id)
    if post is None or post.organization_id != organization_id:
        return None
    return post


async def create_post(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    body: str | None,
    audience: str,
    video_url: str | None,
    actor_user_id: uuid.UUID,
) -> DocumentationPost:
    post = DocumentationPost(
        organization_id=organization_id,
        title=title,
        body=body,
        audience=audience,
        video_url=video_url,
        created_by_user_id=actor_user_id,
    )
    db.add(post)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="documentation.post_created", entity_type="documentation_post", entity_id=str(post.id),
        new_value={"title": title, "audience": audience},
    )
    await db.commit()
    await db.refresh(post)
    return post


async def update_post(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    post_id: uuid.UUID,
    title: str | None,
    body: str | None,
    audience: str | None,
    status_value: str | None,
    video_url: str | None,
    actor_user_id: uuid.UUID,
) -> DocumentationPost | None:
    post = await get_post(db, organization_id=organization_id, post_id=post_id)
    if post is None:
        return None

    previous = {"title": post.title, "audience": post.audience, "status": post.status}
    if title is not None:
        post.title = title
    if body is not None:
        post.body = body
    if audience is not None:
        post.audience = audience
    if status_value is not None:
        post.status = status_value
    if video_url is not None:
        post.video_url = video_url or None

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="documentation.post_updated", entity_type="documentation_post", entity_id=str(post_id),
        previous_value=previous,
        new_value={"title": post.title, "audience": post.audience, "status": post.status},
    )
    await db.commit()
    await db.refresh(post)
    return post


async def delete_post(db: AsyncSession, *, organization_id: uuid.UUID, post_id: uuid.UUID, actor_user_id: uuid.UUID) -> bool:
    post = await get_post(db, organization_id=organization_id, post_id=post_id)
    if post is None:
        return False
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="documentation.post_deleted", entity_type="documentation_post", entity_id=str(post_id),
        previous_value={"title": post.title},
    )
    await db.delete(post)
    await db.commit()
    return True


async def set_post_image(
    db: AsyncSession, *, organization_id: uuid.UUID, post_id: uuid.UUID, file_bytes: bytes, content_type: str
) -> DocumentationPost | None:
    post = await get_post(db, organization_id=organization_id, post_id=post_id)
    if post is None:
        return None
    post.image_url = upload_documentation_attachment(
        file_bytes=file_bytes, content_type=content_type, key_prefix="documentation/images",
        allowed_content_types=ALLOWED_IMAGE_CONTENT_TYPES,
    )
    await db.commit()
    await db.refresh(post)
    return post


async def set_post_pdf(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    post_id: uuid.UUID,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
) -> DocumentationPost | None:
    post = await get_post(db, organization_id=organization_id, post_id=post_id)
    if post is None:
        return None
    post.pdf_url = upload_documentation_attachment(
        file_bytes=file_bytes, content_type=content_type, key_prefix="documentation/pdfs",
        allowed_content_types={"application/pdf"},
    )
    post.pdf_filename = original_filename
    await db.commit()
    await db.refresh(post)
    return post
