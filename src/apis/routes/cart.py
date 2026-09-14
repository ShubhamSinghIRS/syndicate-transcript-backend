import secrets
import uuid

from fastapi import APIRouter, Depends, Request, Response

from apis.controllers.cart import cart_controller
from apis.controllers.cart.cart_schema import AddCartItemRequest, MergeCartRequest
from apis.dependencies import get_current_user_id, get_current_user_id_optional
from config import get_settings
from utils.cookies import GUEST_CART_COOKIE_NAME, clear_guest_cart_cookie, set_guest_cart_cookie
from utils.csrf import verify_same_origin
from utils.response import success_response

from .paths import P

router = APIRouter(prefix=P.cart.BASE, tags=["Cart"])


def _resolve_guest_id(request: Request, response: Response) -> str:
    # Backend-owned guest cart identity - never trusts a client-supplied id.
    existing = request.cookies.get(GUEST_CART_COOKIE_NAME)
    if existing:
        return existing
    new_id = secrets.token_urlsafe(24)
    set_guest_cart_cookie(response, new_id, get_settings().auth.cookie_secure, P.cart.BASE)
    return new_id


@router.get(P.cart.ROOT)
def get_cart(request: Request, response: Response, user_id: uuid.UUID | None = Depends(get_current_user_id_optional)):
    guest_id = None if user_id else _resolve_guest_id(request, response)
    result = cart_controller.get_cart(user_id, guest_id)
    return success_response(data=result)


@router.post(P.cart.ITEMS)
def add_cart_item(
    body: AddCartItemRequest,
    request: Request,
    response: Response,
    user_id: uuid.UUID | None = Depends(get_current_user_id_optional),
):
    verify_same_origin(request)
    guest_id = None if user_id else _resolve_guest_id(request, response)
    cart_controller.add_item(user_id, guest_id, body.transcriptId)
    return success_response(message="Item added to cart.")


@router.delete(P.cart.ITEM_DETAIL)
def remove_cart_item(
    transcript_id: uuid.UUID,
    request: Request,
    response: Response,
    user_id: uuid.UUID | None = Depends(get_current_user_id_optional),
):
    verify_same_origin(request)
    guest_id = None if user_id else _resolve_guest_id(request, response)
    cart_controller.remove_item(user_id, guest_id, transcript_id)
    return success_response(message="Item removed from cart.")


@router.delete(P.cart.ROOT)
def clear_cart(request: Request, response: Response, user_id: uuid.UUID | None = Depends(get_current_user_id_optional)):
    verify_same_origin(request)
    guest_id = None if user_id else _resolve_guest_id(request, response)
    result = cart_controller.clear_cart(user_id, guest_id)
    return success_response(data=result)


@router.post(P.cart.MERGE)
def merge_cart(
    body: MergeCartRequest,
    request: Request,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    verify_same_origin(request)
    guest_id = request.cookies.get(GUEST_CART_COOKIE_NAME)  # read-only, never created here
    result = cart_controller.merge_cart(user_id, guest_id, body.items)
    if guest_id:
        clear_guest_cart_cookie(response, get_settings().auth.cookie_secure, P.cart.BASE)
    return success_response(data=result)
