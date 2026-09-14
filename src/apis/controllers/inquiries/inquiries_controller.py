import uuid

from utils.pagination import Page, PaginationParams

from .inquiries_handler import (
    handle_get_my_topic_request_detail,
    handle_list_my_topic_requests,
    handle_submit_support_message,
    handle_submit_topic_request,
)
from .inquiries_schema import SupportMessagePayload, TopicRequestDetailResponse, TopicRequestPayload


def submit_support_message(data: SupportMessagePayload, user_id: uuid.UUID | None, ip_address: str | None) -> None:
    handle_submit_support_message(data, user_id, ip_address)


def submit_topic_request(data: TopicRequestPayload, user_id: uuid.UUID | None, ip_address: str | None) -> None:
    handle_submit_topic_request(data, user_id, ip_address)


def list_my_topic_requests(
    user_id: uuid.UUID, email: str | None, params: PaginationParams, search: str | None
) -> Page:
    return handle_list_my_topic_requests(user_id, email, params, search)


def get_my_topic_request_detail(
    user_id: uuid.UUID, email: str | None, request_id: uuid.UUID
) -> TopicRequestDetailResponse:
    return handle_get_my_topic_request_detail(user_id, email, request_id)
