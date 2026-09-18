from datetime import datetime

from apis.models.cart import Cart, CartItem
from apis.models.order import Order, OrderItem, OrderStatus
from apis.models.payment import Payment, PaymentStatus
from apis.models.receipt import Receipt


def create_receipt(session, order: Order, paid_at: datetime) -> Receipt:
    # order.id is a UUID, not a zero-padded int - use a short hex segment instead
    # of the old `:05d` numeric formatting.
    receipt = Receipt(
        order_id=order.id,
        invoice_number=f"INV-{paid_at:%Y%m%d}-{order.id.hex[:8].upper()}",
        amount=order.amount,
        currency=order.currency,
    )
    session.add(receipt)
    session.flush()
    return receipt


# The cart row itself is never deleted or recreated - just emptied of whatever
# was just bought, so it's ready to refill on the next add-to-cart.
def clear_purchased_cart_items(session, order: Order) -> None:
    cart = session.query(Cart).filter(Cart.user_id == order.user_id).first()
    if cart is None:
        return
    purchased_ids = {
        row[0] for row in session.query(OrderItem.transcript_id).filter(OrderItem.order_id == order.id).all()
    }
    if not purchased_ids:
        return
    session.query(CartItem).filter(
        CartItem.cart_id == cart.id, CartItem.transcript_id.in_(purchased_ids)
    ).delete(synchronize_session=False)


def transition_to_paid(
    session,
    order: Order,
    payment: Payment,
    gateway_payment_id: str,
    provider_signature: str | None = None,
) -> bool:
    # Guarded UPDATE, only if still 'created' - lets verify and the webhook race safely.
    paid_at = datetime.utcnow()
    rowcount = (
        session.query(Order)
        .filter(Order.id == order.id, Order.status == OrderStatus.CREATED.value)
        .update({"status": OrderStatus.PAID.value, "paid_at": paid_at})
    )
    if rowcount:
        session.query(Payment).filter(Payment.id == payment.id).update(
            {
                "status": PaymentStatus.PAID.value,
                "provider_payment_id": gateway_payment_id,
                "provider_signature": provider_signature,
                "paid_at": paid_at,
            }
        )
        session.query(OrderItem).filter(OrderItem.order_id == order.id).update({"access_permission": True})
        create_receipt(session, order, paid_at)
        clear_purchased_cart_items(session, order)
    return bool(rowcount)


def transition_to_failed(session, order: Order, payment: Payment) -> None:
    rowcount = session.query(Order).filter(Order.id == order.id, Order.status == OrderStatus.CREATED.value).update(
        {"status": OrderStatus.FAILED.value}
    )
    if rowcount:
        session.query(Payment).filter(Payment.id == payment.id).update({"status": PaymentStatus.FAILED.value})
