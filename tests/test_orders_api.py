import json
import uuid

from sqlalchemy import text

from test_auth_api import _ORIGIN_HEADERS
from test_auth_api import _signup_and_verify as _signup_and_verify_cookie
from test_transcripts_api import (
    _auth_headers,
    _grant_transcript_access,
    _seed_author,
    _seed_transcript,
    _signup_and_verify,
)


class _FakeGateway:
    """Stands in for RazorpayService - no network calls, deterministic signature checks."""

    _counter = 0

    def __init__(self, settings):
        self.settings = settings
        self.currency = settings.payment.currency

    def create_order(self, amount, currency, receipt):
        _FakeGateway._counter += 1
        return {"id": f"order_fake_{_FakeGateway._counter}"}

    def verify_payment_signature(self, order_id, payment_id, signature):
        return signature == "valid-signature"

    def verify_webhook_signature(self, payload, signature):
        return signature == "valid-signature"

    def parse_webhook_event(self, payload):
        data = json.loads(payload)
        return {
            "event_type": data["event"],
            "gateway_order_id": data["gateway_order_id"],
            "gateway_payment_id": data.get("gateway_payment_id"),
            "raw_response": {"id": data.get("gateway_payment_id"), "order_id": data["gateway_order_id"]},
        }


def _use_fake_gateway(monkeypatch):
    monkeypatch.setattr("apis.dependencies.RazorpayService", _FakeGateway)


def _create_order(client, token, transcript_ids, idempotency_key=None, amount=1, currency="USD"):
    headers = _auth_headers(token)
    headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
    return client.post(
        "/api/v1/orders",
        json={"amount": amount, "currency": currency, "transcriptIds": transcript_ids},
        headers=headers,
    )


def _verify(client, token, razorpay_order_id, signature="valid-signature", payment_id="pay_1"):
    return client.post(
        "/api/v1/orders/verify",
        json={
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
        headers=_auth_headers(token),
    )


def _webhook(client, event, gateway_order_id, gateway_payment_id=None, signature="valid-signature", event_id="evt_1"):
    return client.post(
        "/api/orders/webhook/razorpay",  # unversioned - registered directly with the payment gateway
        json={"event": event, "gateway_order_id": gateway_order_id, "gateway_payment_id": gateway_payment_id},
        headers={"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": event_id},
    )


def test_create_order_ignores_client_amount_and_recomputes_from_price(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    t1 = _seed_transcript(engine, author_id, price=49)
    t2 = _seed_transcript(engine, author_id, price=99)

    resp = _create_order(client, token, [t1, t2], amount=1, currency="INR")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["amount"] == 148
    assert data["currency"] == "USD"
    assert sorted(data["transcriptIds"]) == sorted([t1, t2])
    assert data["razorpayOrderId"].startswith("order_fake_")


def test_create_order_requires_idempotency_key_header(client, monkeypatch):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)

    resp = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [1]},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422, resp.text


def test_create_order_same_idempotency_key_returns_same_order(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)
    key = str(uuid.uuid4())

    first = _create_order(client, token, [transcript_id], idempotency_key=key)
    second = _create_order(client, token, [transcript_id], idempotency_key=key)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["orderId"] == second.json()["data"]["orderId"]
    assert first.json()["data"]["razorpayOrderId"] == second.json()["data"]["razorpayOrderId"]

    # list_orders only returns paid orders (see below) - this order was
    # never verified, so it correctly doesn't show up. The real "no
    # duplicate" check is the orderId equality assertion above.
    orders_resp = client.get("/api/v1/orders", headers=_auth_headers(token))
    assert len(orders_resp.json()["data"]) == 0


def test_create_order_same_idempotency_key_across_users_does_not_collide(client, monkeypatch, engine):
    # Regression test: idempotency_key used to be globally unique, so two
    # different users reusing the same literal key would crash the second
    # user's checkout with an unhandled IntegrityError/AttributeError. Now
    # scoped to (user_id, idempotency_key), so this must just work.
    _use_fake_gateway(monkeypatch)
    token_a, _ = _signup_and_verify(client, monkeypatch, email="collide-a@example.com")
    token_b, _ = _signup_and_verify(client, monkeypatch, email="collide-b@example.com")
    author_id = _seed_author(engine)
    transcript_a = _seed_transcript(engine, author_id, topic="Topic A")
    transcript_b = _seed_transcript(engine, author_id, topic="Topic B")
    shared_key = str(uuid.uuid4())

    resp_a = _create_order(client, token_a, [transcript_a], idempotency_key=shared_key)
    resp_b = _create_order(client, token_b, [transcript_b], idempotency_key=shared_key)

    assert resp_a.status_code == 200, resp_a.text
    assert resp_b.status_code == 200, resp_b.text
    assert resp_a.json()["data"]["orderId"] != resp_b.json()["data"]["orderId"]
    assert resp_a.json()["data"]["transcriptIds"] == [transcript_a]
    assert resp_b.json()["data"]["transcriptIds"] == [transcript_b]


# _signup_and_verify_cookie/direct SQL insert used here instead of this
# file's usual _signup_and_verify/_seed_transcript - see the comment on
# test_verify_payment_schedules_invoice_email_as_background_task below.
def test_create_order_rejects_reused_idempotency_key_for_different_items(client, monkeypatch, engine):
    # Regression test: a stale idempotency key (e.g. left over in
    # sessionStorage from an earlier checkout whose /verify call timed out
    # client-side before it could be cleared - see the invoice-email
    # background-task fix) used to silently return the *old* order's data -
    # wrong items, wrong amount - if reused later for an unrelated purchase.
    # Reusing a key must mean "the same request, retried," never "whatever
    # order this key was last used for."
    _use_fake_gateway(monkeypatch)
    _signup_and_verify_cookie(client, monkeypatch, email="idempotency-conflict@example.com", password="s3cret1234")

    transcript_a = uuid.uuid4()
    transcript_b = uuid.uuid4()
    with engine.begin() as conn:
        for tid, topic, price in [(transcript_a, "Topic A", 90), (transcript_b, "Topic B", 98)]:
            conn.execute(
                text(
                    """
                    INSERT INTO transcripts (id, fk_expert, topic, domains, geographies, price, is_active)
                    VALUES (:id, 9001, :topic, ARRAY['Enterprise SaaS'], ARRAY['North America'], :price, true)
                    """
                ),
                {"id": str(tid), "topic": topic, "price": price},
            )

    shared_key = str(uuid.uuid4())
    first = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [str(transcript_a)]},
        headers={**_ORIGIN_HEADERS, "Idempotency-Key": shared_key},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["transcriptIds"] == [str(transcript_a)]

    # Same key, different item - must conflict, not silently return order A's data.
    second = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [str(transcript_b)]},
        headers={**_ORIGIN_HEADERS, "Idempotency-Key": shared_key},
    )
    assert second.status_code == 409, second.text

    # The same key with the *same* item as the original request must still
    # work as a normal idempotent retry - only a mismatch is a conflict.
    retry = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [str(transcript_a)]},
        headers={**_ORIGIN_HEADERS, "Idempotency-Key": shared_key},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["data"]["orderId"] == first.json()["data"]["orderId"]


def test_create_order_reuses_open_order_for_same_items_with_different_idempotency_key(client, monkeypatch, engine):
    # Regression test: the frontend used to mint a fresh idempotency key on
    # every page load (component state, not persisted) - a page refresh mid
    # checkout followed by clicking Pay again sent a different key for the
    # exact same cart, creating a second Order + a second Razorpay order for
    # items the user hadn't paid for yet. The backend must recognize "same
    # user, same items, still unpaid" and reuse the existing order regardless
    # of the idempotency key sent.
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    first = _create_order(client, token, [transcript_id])
    second = _create_order(client, token, [transcript_id])  # fresh idempotency_key, same items

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["orderId"] == second.json()["data"]["orderId"]
    assert first.json()["data"]["razorpayOrderId"] == second.json()["data"]["razorpayOrderId"]

    # list_orders only returns paid orders - this one was never verified.
    orders_resp = client.get("/api/v1/orders", headers=_auth_headers(token))
    assert len(orders_resp.json()["data"]) == 0


def test_create_order_does_not_reuse_open_order_for_different_items(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    t1 = _seed_transcript(engine, author_id, topic="Topic A")
    t2 = _seed_transcript(engine, author_id, topic="Topic B")

    first = _create_order(client, token, [t1])
    second = _create_order(client, token, [t2])

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["orderId"] != second.json()["data"]["orderId"]

    # list_orders only returns paid orders - neither of these was verified,
    # so the real "two distinct orders" proof is the orderId inequality above.
    orders_resp = client.get("/api/v1/orders", headers=_auth_headers(token))
    assert len(orders_resp.json()["data"]) == 0


def test_create_order_does_not_reuse_paid_order_for_same_items(client, monkeypatch, engine):
    # A previously paid order for the same items must never be "reused" -
    # only still-open (created) orders are deduped this way.
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    _verify(client, token, razorpay_order_id)

    resp = _create_order(client, token, [transcript_id])
    assert resp.status_code == 400, resp.text


def test_create_order_is_rate_limited_per_user_not_globally(client, monkeypatch, engine):
    from apis.rate_limiting.limiter import RateLimits

    _use_fake_gateway(monkeypatch)
    token_a, _ = _signup_and_verify(client, monkeypatch, email="ratelimit-orders-a@example.com")
    token_b, _ = _signup_and_verify(client, monkeypatch, email="ratelimit-orders-b@example.com")
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    for _ in range(RateLimits.orders.CREATE_ORDER.max_attempts):
        resp = _create_order(client, token_a, [transcript_id])
        assert resp.status_code == 200, resp.text

    # User A has now hit their own limit...
    resp = _create_order(client, token_a, [transcript_id])
    assert resp.status_code == 429, resp.text

    # ...but a completely different user is unaffected - the counter is keyed
    # by user_id, not shared/global.
    resp = _create_order(client, token_b, [transcript_id])
    assert resp.status_code == 200, resp.text


def test_create_order_rejects_inactive_or_missing_transcript(client, monkeypatch):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)

    resp = _create_order(client, token, [999999])
    assert resp.status_code == 400, resp.text


def test_create_order_rejects_already_owned_transcript(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, user_id = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)
    _grant_transcript_access(engine, user_id, transcript_id)

    resp = _create_order(client, token, [transcript_id])
    assert resp.status_code == 400, resp.text


def test_create_order_requires_auth(client, monkeypatch):
    _use_fake_gateway(monkeypatch)
    resp = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [1]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 401, resp.text


def test_verify_payment_valid_signature_marks_paid_and_grants_entitlement(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]

    verify_resp = _verify(client, token, razorpay_order_id)
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["data"]["status"] == "paid"

    purchased = client.get("/api/v1/transcripts/me/purchased", headers=_auth_headers(token))
    assert transcript_id in [item["id"] for item in purchased.json()["data"]["items"]]


def test_verify_payment_creates_invoice(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id, price=49)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    order_id = int(create_resp.json()["data"]["orderId"])

    verify_resp = _verify(client, token, razorpay_order_id)
    assert verify_resp.status_code == 200, verify_resp.text

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT order_id, amount, currency, invoice_number FROM receipts WHERE order_id = :order_id"),
            {"order_id": order_id},
        ).fetchone()
    assert row is not None
    assert row.amount == 49
    assert row.currency == "USD"
    assert row.invoice_number.startswith("INV-")


def test_verify_payment_invalid_signature_marks_failed(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]

    verify_resp = _verify(client, token, razorpay_order_id, signature="bad-signature")
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["data"]["status"] == "failed"


def test_webhook_after_verify_does_not_double_grant(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]

    _verify(client, token, razorpay_order_id)

    webhook_resp = _webhook(client, "payment.captured", razorpay_order_id, "pay_1")
    assert webhook_resp.status_code == 200, webhook_resp.text

    purchased = client.get("/api/v1/transcripts/me/purchased", headers=_auth_headers(token))
    purchased_ids = [item["id"] for item in purchased.json()["data"]["items"]]
    assert purchased_ids.count(transcript_id) == 1


def test_duplicate_webhook_event_id_is_noop(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]

    first = _webhook(client, "payment.captured", razorpay_order_id, "pay_1", event_id="evt_dup")
    assert first.status_code == 200, first.text

    second = _webhook(client, "payment.captured", razorpay_order_id, "pay_1", event_id="evt_dup")
    assert second.status_code == 200, second.text

    purchased = client.get("/api/v1/transcripts/me/purchased", headers=_auth_headers(token))
    purchased_ids = [item["id"] for item in purchased.json()["data"]["items"]]
    assert purchased_ids.count(transcript_id) == 1


def test_list_orders_returns_only_own_orders(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token_a, _ = _signup_and_verify(client, monkeypatch, email="a@example.com")
    token_b, _ = _signup_and_verify(client, monkeypatch, email="b@example.com")
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    # list_orders only returns paid orders, so this order is actually paid
    # (not just created) - otherwise this test wouldn't exercise the
    # ownership scoping it's meant to check at all.
    created = _create_order(client, token_a, [transcript_id])
    _verify(client, token_a, created.json()["data"]["razorpayOrderId"])

    resp_a = client.get("/api/v1/orders", headers=_auth_headers(token_a))
    resp_b = client.get("/api/v1/orders", headers=_auth_headers(token_b))
    assert len(resp_a.json()["data"]) == 1
    assert len(resp_b.json()["data"]) == 0


def test_receipt_404_for_unpaid_order(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    order_id = create_resp.json()["data"]["orderId"]

    resp = client.get(f"/api/v1/orders/{order_id}/receipt", headers=_auth_headers(token))
    assert resp.status_code == 404, resp.text


def test_receipt_404_for_other_users_order(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token_a, _ = _signup_and_verify(client, monkeypatch, email="owner@example.com")
    token_b, _ = _signup_and_verify(client, monkeypatch, email="other@example.com")
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token_a, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    order_id = create_resp.json()["data"]["orderId"]

    _verify(client, token_a, razorpay_order_id)

    resp = client.get(f"/api/v1/orders/{order_id}/receipt", headers=_auth_headers(token_b))
    assert resp.status_code == 404, resp.text


def test_receipt_returns_pdf_for_paid_order(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    order_id = create_resp.json()["data"]["orderId"]

    _verify(client, token, razorpay_order_id)

    resp = client.get(f"/api/v1/orders/{order_id}/receipt", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_receipt_survives_malformed_markup_in_user_name(client, monkeypatch, engine):
    # Regression test: an unclosed/mismatched tag in the user's name used to
    # crash ReportLab's Paragraph parser with an unhandled ValueError - see
    # receipt_generator.py's escape() call and get_receipt_pdf's except Exception.
    _use_fake_gateway(monkeypatch)
    token, _ = _signup_and_verify(client, monkeypatch, name="Bob <b>unclosed bold")
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, token, [transcript_id])
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    order_id = create_resp.json()["data"]["orderId"]

    _verify(client, token, razorpay_order_id)

    resp = client.get(f"/api/v1/orders/{order_id}/receipt", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"


# _signup_and_verify_cookie (test_auth_api's, cookie-based) and a direct SQL
# insert are used here instead of this file's usual _signup_and_verify/
# _seed_transcript (test_transcripts_api's) - those expect a `token` field
# the response no longer returns and a schema (authors table, singular
# domain/geography/key_insight columns) that predates the current transcripts
# table, both pre-existing breakage unrelated to this test.
def test_verify_payment_schedules_invoice_email_as_background_task(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)
    _signup_and_verify_cookie(client, monkeypatch, email="bgemail@example.com", password="s3cret1234")

    transcript_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transcripts (id, fk_expert, topic, domains, geographies, price, is_active)
                VALUES (:id, 9001, 'Enterprise AI Integration', ARRAY['Enterprise SaaS'], ARRAY['North America'], 49, true)
                """
            ),
            {"id": str(transcript_id)},
        )

    call_log = []
    monkeypatch.setattr(
        "apis.controllers.orders.orders_handler.generate_receipt_pdf",
        lambda *args, **kwargs: b"%PDF-fake",
    )
    monkeypatch.setattr(
        "apis.controllers.orders.orders_handler.send_invoice_email",
        lambda *args, **kwargs: call_log.append(True),
    )

    create_resp = client.post(
        "/api/v1/orders",
        json={"amount": 1, "currency": "USD", "transcriptIds": [str(transcript_id)]},
        headers={**_ORIGIN_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert create_resp.status_code == 200, create_resp.text
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]

    verify_resp = client.post(
        "/api/v1/orders/verify",
        json={
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "valid-signature",
        },
        headers=_ORIGIN_HEADERS,
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["data"]["status"] == "paid"

    # The order transitions to paid regardless of whether the invoice email
    # goes out - that's the whole point of scheduling it as a background
    # task (FastAPI's BackgroundTasks) instead of sending it inline before
    # returning the response, which used to make this endpoint wait on a
    # receipt-PDF-generation-plus-SendGrid round trip that has nothing to do
    # with whether the payment itself was actually verified.
    with engine.begin() as conn:
        status = conn.execute(
            text("SELECT status FROM orders WHERE id = :id"), {"id": verify_resp.json()["data"]["orderId"]}
        ).scalar()
    assert status == "paid"
    assert call_log == [True]
