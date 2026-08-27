import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

_DomainItem = Annotated[str, Field(min_length=1, max_length=100)]


class SupportMessagePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)


class TopicRequestPayload(BaseModel):
    name: str | None = Field(default=None, max_length=400)
    topic: str = Field(min_length=1, max_length=300)
    domains: list[_DomainItem] = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    remark: str | None = Field(default=None, max_length=2000)
    suggestedExpertName: str | None = Field(default=None, max_length=200)
    suggestedExpertLinkedin: str | None = Field(default=None, max_length=500)

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_to_none(cls, value: str | None) -> str | None:
        # The form leaves email optional for logged-out users and sends "" rather
        # than omitting the key - EmailStr rejects "" as malformed, not "absent".
        return value or None


class TopicRequestListItem(BaseModel):
    id: uuid.UUID
    topic: str | None
    domains: list[str]
    status: str
    createdAt: datetime | None
