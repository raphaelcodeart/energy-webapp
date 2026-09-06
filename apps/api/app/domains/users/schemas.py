import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    status: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fiscal_code: str | None
    residence_street: str | None
    residence_city: str | None
    residence_province: str | None
    residence_postal_code: str | None
    residence_country: str
    is_complete: bool


class ProfileUpdate(BaseModel):
    fiscal_code: str = Field(min_length=11, max_length=16)
    residence_street: str = Field(min_length=1, max_length=255)
    residence_city: str = Field(min_length=1, max_length=100)
    residence_province: str = Field(min_length=2, max_length=2)
    residence_postal_code: str = Field(min_length=1, max_length=10)
    residence_country: str = Field(default="IT", max_length=2)

    @field_validator("fiscal_code", "residence_street", "residence_city", "residence_province", "residence_postal_code", "residence_country", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("fiscal_code")
    @classmethod
    def uppercase_fiscal_code(cls, v: str) -> str:
        return v.upper()
