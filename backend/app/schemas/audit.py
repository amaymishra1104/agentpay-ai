from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    details: str = Field(min_length=1)


class AuditEventRead(AuditEventCreate):
    id: int
    created_at: datetime
