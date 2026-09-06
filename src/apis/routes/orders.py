import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request

from apis.controllers.orders.orders_controller import OrdersController
from apis.controllers.orders.orders_schema import CreateOrderRequest, VerifyPaymentRequest
from apis.dependencies import get_current_user_id, get_orders_controller
from apis.rate_limiting.dependencies import rate_limit_create_order
from utils.response import pdf_response, success_response

from .paths import P

router = APIRouter(prefix=P.orders.BASE, tags=["Orders"])
# Separate, unversioned router: this URL is already registered in the payment
# gateway's dashboard, so it can't move when the rest of the API is versioned.
webhook_router = APIRouter(prefix=P.orders_webhook.BASE, tags=["Orders"])


@router.post(P.orders.ROOT, dependencies=[Depends(rate_limit_create_order)])
def create_order(
    body: CreateOrderRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    controller: OrdersController = Depends(get_orders_controller),
):
    result = controller.create_order(user_id, body, idempotency_key, background_tasks)
    return success_response(data=result)


@router.post(P.orders.VERIFY)
def verify_payment(
    body: VerifyPaymentRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    controller: OrdersController = Depends(get_orders_controller),
):
    result = controller.verify_payment(user_id, body, background_tasks)
    return success_response(data=result)


@router.get(P.orders.ROOT)
def list_orders(
    user_id: uuid.UUID = Depends(get_current_user_id),
    controller: OrdersController = Depends(get_orders_controller),
):
    result = controller.list_orders(user_id)
    return success_response(data=result)


@router.get(P.orders.DETAIL)
def get_order(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    controller: OrdersController = Depends(get_orders_controller),
):
    result = controller.get_order(user_id, order_id)
    return success_response(data=result)


@router.get(P.orders.RECEIPT)
def get_receipt(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    controller: OrdersController = Depends(get_orders_controller),
):
    pdf_bytes = controller.get_receipt_pdf(user_id, order_id)
    return pdf_response(pdf_bytes, f"receipt-{order_id}.pdf")


@webhook_router.post(P.orders_webhook.WEBHOOK)
async def payment_webhook(
    gateway: str,
    request: Request,
    background_tasks: BackgroundTasks,
    controller: OrdersController = Depends(get_orders_controller),
):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    controller.handle_webhook(gateway, raw_body, signature, event_id, background_tasks)
    return success_response(data=None)
