import uuid

from fastapi import APIRouter, Depends, Request

from apis.controllers.inquiries import inquiries_controller
from apis.controllers.inquiries.inquiries_schema import SupportMessagePayload, TopicRequestPayload
from apis.dependencies import get_current_user_email, get_current_user_id, get_current_user_id_optional
from apis.rate_limiting.dependencies import rate_limit_support, rate_limit_topic_request
from utils.pagination import PaginationParams
from utils.request_meta import get_ip_address
from utils.response import success_response

from .paths import P

support_router = APIRouter(prefix=P.support.BASE, tags=["Support"])
topics_router = APIRouter(prefix=P.topics.BASE, tags=["Topics"])


@support_router.post(P.support.ROOT, dependencies=[Depends(rate_limit_support)])
def submit_support_message(
    body: SupportMessagePayload,
    request: Request,
    user_id: uuid.UUID | None = Depends(get_current_user_id_optional),
):
    inquiries_controller.submit_support_message(body, user_id, get_ip_address(request))
    return success_response(message="Your message has been sent.")


@topics_router.post(P.topics.REQUEST, dependencies=[Depends(rate_limit_topic_request)])
def submit_topic_request(
    body: TopicRequestPayload,
    request: Request,
    user_id: uuid.UUID | None = Depends(get_current_user_id_optional),
):
    inquiries_controller.submit_topic_request(body, user_id, get_ip_address(request))
    return success_response(message="Your topic request has been submitted.")


@topics_router.get(P.topics.MY_REQUESTS)
def list_my_topic_requests(
    search: str | None = None,
    params: PaginationParams = Depends(),
    user_id: uuid.UUID = Depends(get_current_user_id),
    email: str | None = Depends(get_current_user_email),
):
    result = inquiries_controller.list_my_topic_requests(user_id, email, params, search)
    return success_response(data=result)
