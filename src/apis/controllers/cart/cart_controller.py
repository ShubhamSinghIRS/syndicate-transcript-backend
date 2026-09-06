import uuid

from . import cart_handler as handler
from .cart_schema import CartResponse


def get_cart(user_id: uuid.UUID | None, guest_id: str | None) -> CartResponse:
    return handler.handle_get_cart(user_id, guest_id)


def add_item(user_id: uuid.UUID | None, guest_id: str | None, transcript_id: uuid.UUID) -> None:
    handler.handle_add_item(user_id, guest_id, transcript_id)


def remove_item(user_id: uuid.UUID | None, guest_id: str | None, transcript_id: uuid.UUID) -> None:
    handler.handle_remove_item(user_id, guest_id, transcript_id)


def clear_cart(user_id: uuid.UUID | None, guest_id: str | None) -> CartResponse:
    return handler.handle_clear_cart(user_id, guest_id)


def merge_cart(user_id: uuid.UUID, guest_id: str | None, item_ids: list[uuid.UUID]) -> CartResponse:
    return handler.handle_merge_cart(user_id, guest_id, item_ids)
