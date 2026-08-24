import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.hybrid import hybrid_property

from services.crypto.email_crypto import decrypt_email, encrypt_email, hash_email
from services.database.postgres.connection import Base

from .schema import RequestStatus


# user_id is set only if the submitter was logged in - this endpoint is public.
# email is never stored in plaintext - use the `email` property, not email_encrypted directly.
class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_status", "status"),
        Index("ix_support_tickets_user_id", "user_id"),
        Index("ix_support_tickets_email_hash", "email_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email_encrypted = Column(String, nullable=False)
    email_hash = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, default=RequestStatus.OPEN.value, server_default=RequestStatus.OPEN.value)
    created_at = Column(DateTime, server_default=text("now()"), nullable=True)

    @hybrid_property
    def email(self) -> str:
        return decrypt_email(self.email_encrypted)

    @email.setter
    def email(self, value: str) -> None:
        self.email_encrypted = encrypt_email(value)
        self.email_hash = hash_email(value)


# email is optional - anonymous requesters may omit it, logged-in users are
# reachable via their account instead. Never stored in plaintext when present.
class TopicRequest(Base):
    __tablename__ = "topic_requests"
    __table_args__ = (
        Index("ix_topic_requests_status", "status"),
        Index("ix_topic_requests_user_id", "user_id"),
        Index("ix_topic_requests_email_hash", "email_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=True)
    email_encrypted = Column(String, nullable=True)
    email_hash = Column(String, nullable=True)
    domains = Column(ARRAY(String), nullable=False)
    topic = Column(String, nullable=True)
    remark = Column(Text, nullable=True)
    suggested_expert_name = Column(String, nullable=True)
    suggested_expert_linkedin = Column(String, nullable=True)
    status = Column(String, nullable=False, default=RequestStatus.OPEN.value, server_default=RequestStatus.OPEN.value)
    created_at = Column(DateTime, server_default=text("now()"), nullable=True)

    @hybrid_property
    def email(self) -> str | None:
        return decrypt_email(self.email_encrypted) if self.email_encrypted else None

    @email.setter
    def email(self, value: str | None) -> None:
        if value:
            self.email_encrypted = encrypt_email(value)
            self.email_hash = hash_email(value)
        else:
            self.email_encrypted = None
            self.email_hash = None
