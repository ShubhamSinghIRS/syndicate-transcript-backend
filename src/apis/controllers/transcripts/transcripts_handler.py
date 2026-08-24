import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import case, desc, func, literal, literal_column, or_, text

from apis.models.order import Order, OrderItem, OrderStatus
from apis.models.transcript import Transcript, TranscriptFilterBounds
from config import get_settings
from services.database.postgres.connection import get_session
from services.storage.signing_client import get_object_bytes
from utils.pagination import Page, PaginationParams, build_page, paginate

from .transcripts_helper import (
    SLIM_TRANSCRIPT_COLUMNS,
    build_transcript_search_vector,
    has_transcript_access,
    row_to_transcript_list_item,
)
from .transcripts_schema import (
    TranscriptDetailResponse,
    TranscriptFilterBoundsResponse,
    TranscriptFilterRequest,
    TranscriptListItem,
)

logger = logging.getLogger(__name__)


def handle_list_transcripts(params: PaginationParams) -> Page:
    session = get_session()
    try:
        query = session.query(*SLIM_TRANSCRIPT_COLUMNS).filter(Transcript.is_active.is_(True))
        query = query.order_by(Transcript.published_at.desc())

        rows, total = paginate(query, params)
        items = [row_to_transcript_list_item(row) for row in rows]
        return build_page(items, total, params)
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to list transcripts")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_filter_transcripts(filters: TranscriptFilterRequest) -> Page:
    session = get_session()
    try:
        query = session.query(*SLIM_TRANSCRIPT_COLUMNS).filter(Transcript.is_active.is_(True))
        if filters.domains:
            query = query.filter(Transcript.domains.overlap(filters.domains))
        if filters.geographies:
            query = query.filter(Transcript.geographies.overlap(filters.geographies))
        if filters.topic:
            query = query.filter(Transcript.topic.ilike(f"%{filters.topic}%"))

        search_rank = None
        if filters.search:
            # Ranked full-text match (topic/preview/designation/domains/
            # geographies - expert_name is deliberately not searched) or'd
            # with trigram similarity on topic so typos still surface a result.
            search_vector = build_transcript_search_vector()
            search_query = func.plainto_tsquery(literal_column("'english'"), filters.search)
            topic_similarity = func.similarity(Transcript.topic, filters.search)

            query = query.filter(
                or_(
                    search_vector.op("@@")(search_query),
                    text("transcripts.topic % :search_term"),
                )
            ).params(search_term=filters.search)
            search_rank = func.greatest(
                func.ts_rank_cd(search_vector, search_query),
                func.coalesce(topic_similarity, 0.0),
            )
        if filters.expertId is not None:
            query = query.filter(Transcript.fk_expert == filters.expertId)
        if filters.minPrice is not None:
            query = query.filter(Transcript.price >= filters.minPrice)
        if filters.maxPrice is not None:
            query = query.filter(Transcript.price <= filters.maxPrice)
        if filters.publishedAfter is not None:
            query = query.filter(Transcript.published_at >= filters.publishedAfter)

        if search_rank is not None:
            query = query.order_by(desc(search_rank), Transcript.published_at.desc())
        else:
            query = query.order_by(Transcript.published_at.desc())

        params = PaginationParams(page=filters.page, limit=filters.limit)
        rows, total = paginate(query, params)
        items = [row_to_transcript_list_item(row) for row in rows]
        return build_page(items, total, params)
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to filter transcripts")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_list_purchased_transcripts(user_id: uuid.UUID, params: PaginationParams) -> Page:
    session = get_session()
    try:
        query = (
            session.query(*SLIM_TRANSCRIPT_COLUMNS)
            .join(OrderItem, OrderItem.transcript_id == Transcript.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                OrderItem.user_id == user_id,
                OrderItem.access_permission.is_(False),
                Order.status == OrderStatus.PAID.value,
            )
            .distinct()
            .order_by(Transcript.published_at.desc())
        )
        rows, total = paginate(query, params)
        items = [row_to_transcript_list_item(row) for row in rows]
        return build_page(items, total, params)
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to list purchased transcripts")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_list_domains() -> list[str]:
    session = get_session()
    try:
        unnested = func.unnest(Transcript.domains).label("domain")
        rows = (
            session.query(unnested)
            .filter(Transcript.is_active.is_(True), Transcript.domains.isnot(None))
            .distinct()
            .order_by(unnested)
            .all()
        )
        return [row[0] for row in rows]
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to list transcript domains")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_get_filter_bounds() -> TranscriptFilterBoundsResponse:
    # Read from the pre-computed table (kept in sync by a DB trigger) rather than
    # aggregating transcripts directly, so this stays a cheap single-row lookup.
    session = get_session()
    try:
        bounds = session.query(TranscriptFilterBounds).get(1)
        return TranscriptFilterBoundsResponse(
            minPrice=bounds.min_price if bounds else None,
            maxPrice=bounds.max_price if bounds else None,
            minPublishedAt=bounds.min_published_at if bounds else None,
            maxPublishedAt=bounds.max_published_at if bounds else None,
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to fetch transcript filter bounds")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_get_transcript_detail(transcript_id: uuid.UUID) -> TranscriptDetailResponse:
    session = get_session()
    try:
        row = (
            session.query(*SLIM_TRANSCRIPT_COLUMNS)
            .filter(Transcript.id == transcript_id, Transcript.is_active.is_(True))
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Transcript not found")

        item = row_to_transcript_list_item(row)
        return TranscriptDetailResponse(**item.model_dump())
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to fetch transcript detail")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_get_similar_transcripts(transcript_id: uuid.UUID, limit: int = 10) -> list[TranscriptListItem]:
    session = get_session()
    try:
        source = (
            session.query(Transcript.domains, Transcript.preview)
            .filter(Transcript.id == transcript_id, Transcript.is_active.is_(True))
            .first()
        )
        if not source:
            raise HTTPException(status_code=404, detail="Transcript not found")
        source_domains, source_preview = source

        query = session.query(*SLIM_TRANSCRIPT_COLUMNS).filter(
            Transcript.is_active.is_(True),
            Transcript.id != transcript_id,
        )

        # Two independent similarity signals, both optional since either field
        # can be missing on a given transcript - rank by whichever data is
        # available rather than requiring both (which would too often leave
        # nothing to show).
        if source_domains:
            domain_match = case((Transcript.domains.overlap(source_domains), 1), else_=0)
        else:
            domain_match = literal(0)

        if source_preview:
            # transcript_preview_tsvector (migration df3b7e404367) is a DB-side
            # function backed by a GIN index - matching it here (instead of
            # inlining to_tsvector) means this scan reuses that index instead
            # of recomputing a tsvector for every active row on every call.
            preview_rank = func.ts_rank_cd(
                func.transcript_preview_tsvector(Transcript.preview),
                func.plainto_tsquery(literal_column("'english'"), source_preview),
            )
        else:
            preview_rank = literal(0.0)

        rows = (
            query.order_by(desc(domain_match), desc(preview_rank), Transcript.published_at.desc())
            .limit(limit)
            .all()
        )
        return [row_to_transcript_list_item(row) for row in rows]
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to fetch similar transcripts for %s", transcript_id)
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()


def handle_get_transcript_file(user_id: uuid.UUID, transcript_id: uuid.UUID) -> bytes:
    """Load a purchased transcript's actual PDF bytes from storage.

    Access-gated (must be a PAID order for this user) and proxied through this
    service: the bytes are fetched from the storage bucket server-side and streamed
    back, so the browser never talks to the bucket directly. The same bytes back
    both the inline viewer (/view) and the download (/download).
    """
    session = get_session()
    try:
        transcript = (
            session.query(Transcript)
            .filter(Transcript.id == transcript_id, Transcript.is_active.is_(True))
            .first()
        )
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")

        if not has_transcript_access(session, user_id, transcript_id):
            raise HTTPException(status_code=403, detail="You do not have access to this transcript.")

        if not transcript.final_transcript:
            raise HTTPException(status_code=404, detail="No file available for this transcript.")

        if not get_settings().storage.is_configured:
            raise HTTPException(status_code=503, detail="Transcript file is not available right now.")

        body, _content_type = get_object_bytes(transcript_id, transcript.final_transcript)
        return body
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to load file for transcript %s", transcript_id)
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()
