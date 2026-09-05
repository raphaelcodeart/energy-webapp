import uuid

from pydantic import BaseModel, ConfigDict, Field


class PartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    logo_url: str | None
    is_active: bool


class PartnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    logo_url: str | None = None


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    logo_url: str | None = None
    is_active: bool | None = None
