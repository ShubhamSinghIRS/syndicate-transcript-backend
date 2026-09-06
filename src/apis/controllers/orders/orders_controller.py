import uuid

from fastapi import BackgroundTasks

from .orders_handler import OrdersHandler
from .orders_schema import (
    CreateOrderRequest,
    CreateOrderResponse,
    FreeOrderResponse,
    OrderSummary,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)


class OrdersController:
    def __init__(self, handler: OrdersHandler):
        self.handler = handler

    def create_order(
        self, user_id: uuid.UUID, body: CreateOrderRequest, idempotency_key: str, background_tasks: BackgroundTasks
    ) -> CreateOrderResponse | FreeOrderResponse:
        return self.handler.create_order(user_id, body.transcriptIds, idempotency_key, background_tasks)

    def verify_payment(
        self, user_id: uuid.UUID, body: VerifyPaymentRequest, background_tasks: BackgroundTasks
    ) -> VerifyPaymentResponse:
        return self.handler.verify_payment(
            user_id, body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature, background_tasks
        )

    def list_orders(self, user_id: uuid.UUID) -> list[OrderSummary]:
        return self.handler.list_orders(user_id)

    def get_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> OrderSummary:
        return self.handler.get_order(user_id, order_id)

    def get_receipt_pdf(self, user_id: uuid.UUID, order_id: uuid.UUID) -> bytes:
        return self.handler.get_receipt_pdf(user_id, order_id)

    def handle_webhook(
        self, gateway: str, raw_body: bytes, signature: str, event_id: str, background_tasks: BackgroundTasks
    ) -> None:
        self.handler.handle_webhook(gateway, raw_body, signature, event_id, background_tasks)
