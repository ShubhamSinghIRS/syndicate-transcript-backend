import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_

from apis.models.inquiries import SupportTicket, TopicRequest
from services.crypto.email_crypto import hash_email
from services.database.postgres.connection import get_session
from utils.pagination import Page, PaginationParams, build_page, paginate

from .inquiries_schema import SupportMessagePayload, TopicRequestListItem, TopicRequestPayload

logger = logging.getLogger(__name__)


def handle_submit_support_message(
    data: SupportMessagePayload, user_id: uuid.UUID | None, ip_address: str | None
) -> None:
    # ip_address is unused here now (rate limiting moved to jwt_middleware).
    session = get_session()
    try:
        ticket = SupportTicket(
            name=data.name,
            message=data.message,
            user_id=user_id,
        )
        ticket.email = data.email
        session.add(ticket)
        session.commit()
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to store support message")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_submit_topic_request(
    data: TopicRequestPayload, user_id: uuid.UUID | None, ip_address: str | None
) -> None:
    # ip_address is unused here now (rate limiting moved to jwt_middleware).
    session = get_session()
    try:
        request = TopicRequest(
            name=data.name,
            topic=data.topic,
            domains=data.domains,
            remark=data.remark,
            suggested_expert_name=data.suggestedExpertName,
            suggested_expert_linkedin=data.suggestedExpertLinkedin,
            user_id=user_id,
        )
        request.email = data.email
        session.add(request)
        session.commit()
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to store topic request")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_list_my_topic_requests(
    user_id: uuid.UUID, email: str | None, params: PaginationParams, search: str | None
) -> Page:
    session = get_session()
    try:
        # Also match by email so a request made anonymously (before signing up
        # or while logged out) shows up once the same email is logged in.
        owner_match = TopicRequest.user_id == user_id
        if email:
            owner_match = or_(owner_match, TopicRequest.email_hash == hash_email(email))
        query = session.query(TopicRequest).filter(owner_match)
        if search:
            term = f"%{search}%"
            domains_text = func.array_to_string(TopicRequest.domains, ", ")
            query = query.filter((TopicRequest.topic.ilike(term)) | (domains_text.ilike(term)))
        query = query.order_by(TopicRequest.created_at.desc())

        rows, total = paginate(query, params)
        items = [
            TopicRequestListItem(
                id=row.id,
                topic=row.topic,
                domains=row.domains,
                status=row.status,
                createdAt=row.created_at,
            )
            for row in rows
        ]
        return build_page(items, total, params)
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to list topic requests")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()
