from pydantic import BaseModel, EmailStr, field_validator


def _strip(v: object) -> object:
    """A stray leading/trailing space from copy-pasting an email or password is
    not a real credential mismatch -- strip it before any further validation
    (EmailStr would otherwise reject " foo@bar.com" outright, and a padded
    password would just silently fail to match the real one)."""
    return v.strip() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str

    @field_validator("email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeRead(BaseModel):
    roles: list[str]


class RegisterRequest(BaseModel):
    organization_id: str
    # Closed circuit: registration is invite-only, every new customer must come
    # through a promoter's referral link (docs/business-rules.md intent --
    # "nessuno può stare senza promoter che lo invita").
    referral_code: str
    email: EmailStr
    password: str
    kind: str  # PRIVATE / SOLE_PROPRIETOR / COMPANY / CONDOMINIUM
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    phone: str | None = None

    @field_validator("email", "password", "referral_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class ForgotPasswordRequest(BaseModel):
    organization_id: str
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v
