from sqlalchemy import text

from services.crypto.email_crypto import decrypt_email
from test_auth_api import _ORIGIN_HEADERS
from test_auth_api import _signup_and_verify as _signup_and_verify_cookie
from test_transcripts_api import _auth_headers, _signup_and_verify


def _valid_support_payload(**overrides):
    payload = {"name": "Jane Doe", "email": "jane@example.com", "message": "How do I download a transcript?"}
    payload.update(overrides)
    return payload


def _valid_topic_payload(**overrides):
    payload = {"topic": "AI in Healthcare", "domains": ["Healthcare"]}
    payload.update(overrides)
    return payload


def test_submit_support_message_stores_row(client, engine):
    resp = client.post("/api/v1/support", json=_valid_support_payload())
    assert resp.status_code == 200, resp.text

    with engine.begin() as conn:
        row = conn.execute(text("SELECT name, email_encrypted, message, user_id FROM support_tickets")).fetchone()
    assert row is not None
    assert row.name == "Jane Doe"
    assert decrypt_email(row.email_encrypted) == "jane@example.com"
    assert row.user_id is None


def test_submit_support_message_requires_no_auth(client, engine):
    # No Authorization header at all - must not 401.
    resp = client.post("/api/v1/support", json=_valid_support_payload())
    assert resp.status_code == 200, resp.text


def test_submit_support_message_captures_user_id_when_logged_in(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch)

    resp = client.post("/api/v1/support", json=_valid_support_payload(), headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    with engine.begin() as conn:
        row = conn.execute(text("SELECT user_id FROM support_tickets")).fetchone()
    assert row.user_id == user_id


def test_submit_support_message_validates_fields(client, engine):
    resp = client.post("/api/v1/support", json=_valid_support_payload(email="not-an-email"))
    assert resp.status_code == 422, resp.text

    resp = client.post("/api/v1/support", json=_valid_support_payload(name=""))
    assert resp.status_code == 422, resp.text

    resp = client.post("/api/v1/support", json=_valid_support_payload(message="x" * 5001))
    assert resp.status_code == 422, resp.text


def test_submit_support_message_is_rate_limited_by_ip(client, engine):
    from apis.rate_limiting.limiter import RateLimits

    for _ in range(RateLimits.inquiries.SUPPORT_MESSAGE.max_attempts):
        resp = client.post("/api/v1/support", json=_valid_support_payload())
        assert resp.status_code == 200, resp.text

    resp = client.post("/api/v1/support", json=_valid_support_payload())
    assert resp.status_code == 429, resp.text


def test_submit_topic_request_stores_row(client, engine):
    resp = client.post(
        "/api/v1/topics/request",
        json=_valid_topic_payload(
            email="requester@example.com",
            remark="Please prioritize this",
            suggestedExpertName="Dr. Smith",
            suggestedExpertLinkedin="linkedin.com/in/drsmith",
        ),
    )
    assert resp.status_code == 200, resp.text

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT topic, domains, email_encrypted, remark, suggested_expert_name, suggested_expert_linkedin, "
                "user_id FROM topic_requests"
            )
        ).fetchone()
    assert row is not None
    assert row.topic == "AI in Healthcare"
    assert row.domains == ["Healthcare"]
    assert decrypt_email(row.email_encrypted) == "requester@example.com"
    assert row.suggested_expert_name == "Dr. Smith"
    assert row.user_id is None


def test_submit_topic_request_only_requires_topic_and_domains(client, engine):
    # email/remark/suggestedExpert* are optional client-side too.
    resp = client.post("/api/v1/topics/request", json=_valid_topic_payload())
    assert resp.status_code == 200, resp.text


def test_submit_topic_request_captures_user_id_when_logged_in(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch, email="topicrequester@example.com")

    resp = client.post("/api/v1/topics/request", json=_valid_topic_payload(), headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    with engine.begin() as conn:
        row = conn.execute(text("SELECT user_id FROM topic_requests")).fetchone()
    assert row.user_id == user_id


def test_submit_topic_request_validates_fields(client, engine):
    resp = client.post("/api/v1/topics/request", json=_valid_topic_payload(topic=""))
    assert resp.status_code == 422, resp.text

    resp = client.post("/api/v1/topics/request", json=_valid_topic_payload(email="not-an-email"))
    assert resp.status_code == 422, resp.text


def test_submit_topic_request_is_rate_limited_by_ip(client, engine):
    from apis.rate_limiting.limiter import RateLimits

    for _ in range(RateLimits.inquiries.TOPIC_REQUEST.max_attempts):
        resp = client.post("/api/v1/topics/request", json=_valid_topic_payload())
        assert resp.status_code == 200, resp.text

    resp = client.post("/api/v1/topics/request", json=_valid_topic_payload())
    assert resp.status_code == 429, resp.text


# _signup_and_verify_cookie (test_auth_api's, cookie-based) is used here
# instead of this file's usual _signup_and_verify/_auth_headers (Bearer-token
# style, test_transcripts_api's) - that helper expects a `token` field the
# response no longer returns and casts the UUID user id with int(), both
# pre-existing breakage unrelated to this endpoint.
def test_get_topic_request_detail_returns_submitted_fields(client, monkeypatch):
    _signup_and_verify_cookie(client, monkeypatch, email="topicdetail-owner@example.com")

    submit = client.post(
        "/api/v1/topics/request",
        headers=_ORIGIN_HEADERS,
        json=_valid_topic_payload(
            domains=["Healthcare", "Fintech Payments"],
            remark="Looking for a VP-level practitioner",
            suggestedExpertName="Jane Doe",
            suggestedExpertLinkedin="https://linkedin.com/in/janedoe",
        ),
    )
    assert submit.status_code == 200, submit.text

    listed = client.get("/api/v1/topics/my-requests")
    request_id = listed.json()["data"]["items"][0]["id"]

    detail = client.get(f"/api/v1/topics/{request_id}")
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["topic"] == "AI in Healthcare"
    assert data["domains"] == ["Healthcare", "Fintech Payments"]
    assert data["remark"] == "Looking for a VP-level practitioner"
    assert data["suggestedExpertName"] == "Jane Doe"
    assert data["suggestedExpertLinkedin"] == "https://linkedin.com/in/janedoe"


def test_get_topic_request_detail_hides_other_users_request(client, monkeypatch):
    _signup_and_verify_cookie(client, monkeypatch, email="topicdetail-owner2@example.com")
    submit = client.post(
        "/api/v1/topics/request",
        headers=_ORIGIN_HEADERS,
        json=_valid_topic_payload(domains=["Healthcare", "Fintech Payments"]),
    )
    assert submit.status_code == 200, submit.text
    request_id = client.get("/api/v1/topics/my-requests").json()["data"]["items"][0]["id"]

    client.post("/api/v1/auth/logout", headers=_ORIGIN_HEADERS)
    _signup_and_verify_cookie(client, monkeypatch, email="topicdetail-attacker@example.com")

    resp = client.get(f"/api/v1/topics/{request_id}")
    assert resp.status_code == 404, resp.text


def test_get_topic_request_detail_requires_auth(client):
    resp = client.get("/api/v1/topics/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401, resp.text
