import uuid

from sqlalchemy import func

from apis.models.order import Order, OrderItem, OrderStatus
from apis.models.transcript import Transcript

from .transcripts_schema import ExpertSummary, TranscriptListItem

# Shared with cart/orders - same slim transcript+expert shape used there too.
SLIM_TRANSCRIPT_COLUMNS = (
    Transcript.id,
    Transcript.topic,
    Transcript.domains,
    Transcript.geographies,
    Transcript.preview,
    Transcript.key_insights,
    Transcript.price,
    Transcript.is_active,
    Transcript.published_at,
    Transcript.fk_expert,
    Transcript.expert_name,
    Transcript.designation,
    Transcript.years_of_experience,
)


def build_transcript_search_vector():
    # transcripts_search_vector is a DB-side function (migration fc4468e7a504)
    # so the GIN index and this query expression can never drift apart.
    # expert_name is deliberately excluded - search doesn't match on it.
    return func.transcripts_search_vector(
        Transcript.topic,
        Transcript.preview,
        Transcript.designation,
        Transcript.domains,
        Transcript.geographies,
    )


def has_transcript_access(session, user_id: uuid.UUID | None, transcript_id: uuid.UUID) -> bool:
    if user_id is None:
        return False
    return (
        session.query(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.user_id == user_id,
            OrderItem.transcript_id == transcript_id,
            OrderItem.access_permission.is_(True),
            Order.status == OrderStatus.PAID.value,
        )
        .first()
        is not None
    )


def row_to_transcript_list_item(row) -> TranscriptListItem:
    (
        transcript_id,
        topic,
        domains,
        geographies,
        preview,
        key_insights,
        price,
        is_active,
        published_at,
        fk_expert,
        expert_name,
        designation,
        years_of_experience,
    ) = row
    expert = ExpertSummary(
        id=fk_expert, name=expert_name, designation=designation, yearsOfExperience=years_of_experience
    )
    return TranscriptListItem(
        id=transcript_id,
        topic=topic,
        domains=domains or [],
        geographies=geographies or [],
        preview=preview,
        keyInsights=key_insights or [],
        price=int(price),
        expert=expert,
        isActive=is_active,
        publishedAt=published_at,
    )
