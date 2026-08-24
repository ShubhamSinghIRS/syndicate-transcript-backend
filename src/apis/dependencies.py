import hmac
import uuid

from fastapi import Header, HTTPException, Request

from apis.controllers.orders.orders_controller import OrdersController
from apis.controllers.orders.orders_handler import OrdersHandler
from config import get_settings
from services.payment import RazorpayService


def verify_ingest_api_key(x_api_key: str = Header(default="", alias="x-api-key")) -> None:
    """Server-to-server auth for the Infollion transcript-ingest endpoints.

    Compares the `x-api-key` header against SYNDICATE_INBOUND_API_KEY in constant time.
    Fails closed: if the secret is unset, every request is rejected.
    """
    expected = get_settings().ingest.api_key
    if not expected or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_current_user_id(request: Request) -> uuid.UUID:
    """User id attached by the JWT middleware. Use on every protected route."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User identity missing from session.")
    return uuid.UUID(user_id)


def get_current_user_id_optional(request: Request) -> uuid.UUID | None:
    # Like get_current_user_id, but None instead of 401 - for soft-auth routes (e.g. cart).
    user_id = getattr(request.state, "user_id", None)
    return uuid.UUID(user_id) if user_id else None


def get_current_user_email(request: Request) -> str | None:
    """Email claim from the JWT, attached by the JWT middleware."""
    return getattr(request.state, "email", None)


_orders_controller: OrdersController | None = None


def get_orders_controller() -> OrdersController:
    """Lazily-built singleton so RazorpayService's SDK client isn't re-constructed per request."""
    global _orders_controller
    if _orders_controller is None:
        payment_service = RazorpayService(get_settings())
        handler = OrdersHandler(payment_service)
        _orders_controller = OrdersController(handler)
    return _orders_controller
