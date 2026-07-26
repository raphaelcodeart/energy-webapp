from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v
