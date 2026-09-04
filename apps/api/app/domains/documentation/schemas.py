import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentationPostCreate(BaseModel):
    title: str
    body: str | None = None
    audience: str = "BOTH"
    video_url: str | None = None


class DocumentationPostUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    audience: str | None = None
    status: str | None = None
    video_url: str | None = None


class DocumentationPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str | None
    audience: str
    status: str
    image_url: str | None
    pdf_url: str | None
    pdf_filename: str | None
    video_url: str | None
    created_at: datetime
