import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    entity_type: str
    entity_id: str
    title: str
    body: str | None
    is_read: bool
    created_at: datetime
