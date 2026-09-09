from pydantic import BaseModel, EmailStr, field_validator

from app.core.normalization import normalize_email, normalize_person_name


def _strip(v: object) -> object:
    """A stray leading/trailing space from copy-pasting a password is not a
    real credential mismatch -- strip it before any further validation (a
    padded password would otherwise just silently fail to match the real
    one). Email fields use normalize_email instead (strip + lowercase), see
    below."""
    return v.strip() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeRead(BaseModel):
    roles: list[str]
    # Live account-gate flags -- read by the dashboard shell to decide whether
    # to show the blocking email-verification / profile-completion popups
    # (see docs/business-rules.md#account-gates). Unlike `roles`, these were
    # never baked into the access token at all, so there's no "stale until
    # next refresh" concern to worry about.
    email_verified: bool
    profile_complete: bool
    privacy_accepted: bool


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
    # Mandatory: the registration form has a single privacy-policy checkbox
    # that must be ticked before the submit button is even enabled -- this is
    # the server-side backstop, see auth/service.py::register_with_referral.
    accept_privacy: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("password", "referral_code", "company_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("accept_privacy")
    @classmethod
    def validate_accept_privacy(cls, v: bool) -> bool:
        if not v:
            raise ValueError("privacy policy must be accepted to register")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    pass


class ForgotPasswordRequest(BaseModel):
    organization_id: str
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v


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
