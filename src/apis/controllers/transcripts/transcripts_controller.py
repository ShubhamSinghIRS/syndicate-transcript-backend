import uuid

from utils.pagination import PaginationParams

from . import transcripts_handler as handler
from .transcripts_schema import (
    TranscriptDetailResponse,
    TranscriptFilterBoundsResponse,
    TranscriptFilterRequest,
    TranscriptListItem,
)


def list_transcripts(params: PaginationParams):
    return handler.handle_list_transcripts(params)


def filter_transcripts(filters: TranscriptFilterRequest):
    return handler.handle_filter_transcripts(filters)


def list_purchased_transcripts(user_id: uuid.UUID, params: PaginationParams):
    return handler.handle_list_purchased_transcripts(user_id, params)


def list_domains() -> list[str]:
    return handler.handle_list_domains()


def get_filter_bounds() -> TranscriptFilterBoundsResponse:
    return handler.handle_get_filter_bounds()


def get_transcript_detail(transcript_id: uuid.UUID) -> TranscriptDetailResponse:
    return handler.handle_get_transcript_detail(transcript_id)


def get_similar_transcripts(transcript_id: uuid.UUID, limit: int) -> list[TranscriptListItem]:
    return handler.handle_get_similar_transcripts(transcript_id, limit)


def get_transcript_file(user_id: uuid.UUID, transcript_id: uuid.UUID) -> bytes:
    return handler.handle_get_transcript_file(user_id, transcript_id)
