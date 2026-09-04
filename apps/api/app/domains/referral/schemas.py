import uuid

from pydantic import BaseModel, ConfigDict


class PromoterCodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    personal_link: str
    status: str
    # None on GET /referral/mine (a promoter looking at their own link doesn't
    # need to be told who invited them) -- only set when resolving someone
    # ELSE's link, so the registration page can show "Invitato da ...".
    promoter_display_name: str | None = None
