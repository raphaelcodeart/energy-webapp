import uuid

from pydantic import BaseModel, ConfigDict


class PromoterCodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    personal_link: str
    status: str
