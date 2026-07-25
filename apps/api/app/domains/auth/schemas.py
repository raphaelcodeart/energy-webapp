from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
