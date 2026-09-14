import json
from datetime import datetime, timezone

from sqlalchemy import text


def _signup_and_verify(client, monkeypatch, email="reader@example.com", password="s3cret1234", name="Reader"):
    captured = {}

    def fake_send_otp(to_email, otp):
        captured["otp"] = otp

    monkeypatch.setattr("apis.controllers.auth.auth_handler.send_registration_otp", fake_send_otp)

    resp = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "companyName": "Acme Inc"},
    )
    assert resp.status_code == 200, resp.text
    pending_token = resp.json()["data"]["tempToken"]

    verify_resp = client.post(
        "/api/v1/auth/register/verify-otp", json={"tempToken": pending_token, "otp": captured["otp"]}
    )
    assert verify_resp.status_code == 200, verify_resp.text
    body = verify_resp.json()["data"]
    return body["token"], int(body["user"]["id"])


def _seed_author(engine) -> int:
    # experts now come from a separate backend with no local table - any id works here
    return 9001


def _seed_transcript(
    engine,
    author_id: int,
    final_transcript: dict | None = None,
    domain: list[str] | None = None,
    geography: list[str] | None = None,
    topic: str | None = None,
    price: int = 49,
) -> int:
    if final_transcript is None:
        final_transcript = {"url": "s3://bucket/key.pdf", "filename": "transcript.pdf"}
    if domain is None:
        domain = ["Enterprise SaaS"]
    if geography is None:
        geography = ["North America"]
    if topic is None:
        topic = "Enterprise AI Integration"

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO transcripts
                    (fk_expert, expert_name, designation, years_of_experience, topic, domain, geography, preview,
                     key_insight, final_transcript, price, published_at, approved_at, is_active)
                VALUES
                    (:fk_expert, :expert_name, :designation, :years_of_experience, :topic, :domain, :geography,
                     :preview, :key_insight, :final_transcript, :price, :published_at, :approved_at, true)
                RETURNING id
                """
            ),
            {
                "fk_expert": author_id,
                "expert_name": "Sarah Mitchell",
                "designation": "VP of Revenue Operations",
                "years_of_experience": 12,
                "topic": topic,
                "domain": domain,
                "geography": geography,
                "preview": "A short preview of the conversation.",
                "key_insight": ["Budgets are shifting toward consumption pricing", "Vendor lock-in is the top concern"],
                "final_transcript": json.dumps(final_transcript),
                "price": price,
                "published_at": datetime.now(timezone.utc),
                "approved_at": datetime.now(timezone.utc),
            },
        )
        return result.scalar_one()


def _grant_transcript_access(engine, user_id: int, transcript_id: int) -> None:
    with engine.begin() as conn:
        order_id = conn.execute(
            text(
                "INSERT INTO orders (user_id, status, amount, currency, paid_at) "
                "VALUES (:user_id, 'paid', 0, 'INR', now()) RETURNING id"
            ),
            {"user_id": user_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO order_items (order_id, user_id, transcript_id, price, currency, access_permission) "
                "VALUES (:order_id, :user_id, :transcript_id, 0, 'INR', false)"
            ),
            {"order_id": order_id, "user_id": user_id, "transcript_id": transcript_id},
        )


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_list_transcripts_is_public(client):
    resp = client.get("/api/v1/transcripts")
    assert resp.status_code == 200, resp.text


def test_domains_is_public(client):
    resp = client.get("/api/v1/transcripts/domains")
    assert resp.status_code == 200, resp.text


def test_list_transcripts_includes_all_schema_fields(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(
        engine, author_id, final_transcript={"url": "s3://bucket/real.pdf", "filename": "real.pdf"}
    )

    resp = client.get("/api/v1/transcripts?limit=20")
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["data"]["items"] if i["id"] == transcript_id)

    assert "isPurchased" not in item
    assert item["finalTranscript"] == {"url": "s3://bucket/real.pdf", "filename": "real.pdf"}
    assert item["keyInsight"]
    assert item["isActive"] is True
    assert item["publishedAt"] is not None
    assert item["approvedAt"] is not None
    assert item["createdAt"] is not None
    assert item["price"] == 49


def test_detail_is_public(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.get(f"/api/v1/transcripts/{transcript_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "isPurchased" not in data
    assert data["finalTranscript"] == {"url": "s3://bucket/key.pdf", "filename": "transcript.pdf"}


def test_detail_with_invalid_token_still_works(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.get(
        f"/api/v1/transcripts/{transcript_id}", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 200, resp.text


def test_my_purchased_requires_auth(client):
    # Shares the /api/v1/transcripts prefix with the public list/detail routes
    # but must stay hard-protected.
    resp = client.get("/api/v1/transcripts/me/purchased")
    assert resp.status_code == 401


def test_view_and_download_require_auth(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/view")
    assert resp.status_code == 401

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/download")
    assert resp.status_code == 401


def test_view_and_download_require_purchase(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/view", headers=_auth_headers(token))
    assert resp.status_code == 403

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/download", headers=_auth_headers(token))
    assert resp.status_code == 403


# TODO: the signing-service call in handle_get_transcript_access is
# commented out pending that backend being ready (see the TODO in
# transcripts_handler.py). Once uncommented, restore this test to assert a
# 200 + the mocked signed url, like before.
def test_view_still_not_implemented_after_purchase(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)
    _grant_transcript_access(engine, user_id, transcript_id)

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/view", headers=_auth_headers(token))
    assert resp.status_code == 501


def test_full_text_and_download_work_after_purchase(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)
    _grant_transcript_access(engine, user_id, transcript_id)

    full_text_resp = client.get(f"/api/v1/transcripts/{transcript_id}/full-text", headers=_auth_headers(token))
    assert full_text_resp.status_code == 200, full_text_resp.text
    full_text = full_text_resp.json()["data"]["fullText"]
    assert "Enterprise AI Integration" in full_text  # default _seed_transcript topic

    # No signing service configured in tests -> dev-mode placeholder PDF, not a redirect.
    download_resp = client.get(f"/api/v1/transcripts/{transcript_id}/download", headers=_auth_headers(token))
    assert download_resp.status_code == 200, download_resp.text
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content[:4] == b"%PDF"


def test_full_text_and_download_require_purchase(client, monkeypatch, engine):
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/full-text", headers=_auth_headers(token))
    assert resp.status_code == 403

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/download", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_domain_filter_matches_via_array_containment(client, engine):
    author_id = _seed_author(engine)
    multi_domain_id = _seed_transcript(engine, author_id, domain=["Fintech Payments", "Cybersecurity Operations"])
    _seed_transcript(engine, author_id, domain=["Retail Customer Experience"])

    resp = client.get("/api/v1/transcripts?domain=Cybersecurity%20Operations")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == multi_domain_id
    assert body["items"][0]["domain"] == ["Fintech Payments", "Cybersecurity Operations"]


def test_domains_endpoint_returns_flattened_distinct_list(client, engine):
    author_id = _seed_author(engine)
    _seed_transcript(engine, author_id, domain=["Fintech Payments", "Cybersecurity Operations"])
    _seed_transcript(engine, author_id, domain=["Cybersecurity Operations", "Retail Customer Experience"])

    resp = client.get("/api/v1/transcripts/domains")
    assert resp.status_code == 200, resp.text
    domains = resp.json()["data"]
    assert domains == ["Cybersecurity Operations", "Fintech Payments", "Retail Customer Experience"]


def test_my_purchased_only_returns_entitled_transcripts(client, monkeypatch, engine):
    token, user_id = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    purchased_id = _seed_transcript(engine, author_id)
    _seed_transcript(engine, author_id)  # not purchased
    _grant_transcript_access(engine, user_id, purchased_id)

    resp = client.get("/api/v1/transcripts/me/purchased", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == purchased_id


def test_filter_is_public(client):
    resp = client.post("/api/v1/transcripts/filter", json={})
    assert resp.status_code == 200, resp.text


def test_filter_by_domain_matches_via_array_overlap(client, engine):
    author_id = _seed_author(engine)
    match_id = _seed_transcript(engine, author_id, domain=["Fintech Payments", "Cybersecurity Operations"])
    _seed_transcript(engine, author_id, domain=["Retail Customer Experience"])

    resp = client.post("/api/v1/transcripts/filter", json={"domain": ["Fintech Payments", "HR Tech"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == match_id


def test_filter_by_geography(client, engine):
    author_id = _seed_author(engine)
    match_id = _seed_transcript(engine, author_id, geography=["Europe"])
    _seed_transcript(engine, author_id, geography=["South Asia"])

    resp = client.post("/api/v1/transcripts/filter", json={"geography": ["Europe"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == match_id


def test_filter_by_topic_substring_case_insensitive(client, engine):
    author_id = _seed_author(engine)
    match_id = _seed_transcript(engine, author_id, topic="Cloud Cost Optimization deep dive")
    _seed_transcript(engine, author_id, topic="Something unrelated")

    resp = client.post("/api/v1/transcripts/filter", json={"topic": "cloud cost"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == match_id


def test_filter_by_search_matches_topic_or_geography(client, engine):
    author_id = _seed_author(engine)
    topic_match_id = _seed_transcript(engine, author_id, topic="Cloud cost optimization", geography=["Europe"])
    geography_match_id = _seed_transcript(engine, author_id, topic="Unrelated topic", geography=["APAC"])
    _seed_transcript(engine, author_id, topic="Something else", geography=["South Asia"])

    resp = client.post("/api/v1/transcripts/filter", json={"search": "cloud"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == topic_match_id

    resp = client.post("/api/v1/transcripts/filter", json={"search": "APAC"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == geography_match_id


def test_filter_by_price_range(client, engine):
    author_id = _seed_author(engine)
    cheap_id = _seed_transcript(engine, author_id, price=10)
    _seed_transcript(engine, author_id, price=500)

    resp = client.post(
        "/api/v1/transcripts/filter", json={"priceRanges": [{"minPrice": 5, "maxPrice": 50}]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == cheap_id


def test_filter_by_multiple_disjoint_price_ranges_does_not_include_the_gap(client, engine):
    author_id = _seed_author(engine)
    free_id = _seed_transcript(engine, author_id, price=0)
    _seed_transcript(engine, author_id, price=100)  # the gap - must be excluded
    high_id = _seed_transcript(engine, author_id, price=300)

    resp = client.post(
        "/api/v1/transcripts/filter",
        json={"priceRanges": [{"minPrice": 0, "maxPrice": 0}, {"minPrice": 200, "maxPrice": 400}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    returned_ids = {item["id"] for item in body["items"]}
    assert returned_ids == {free_id, high_id}


def test_filter_by_author_id(client, engine):
    author_a = _seed_author(engine)
    author_b = _seed_author(engine)
    match_id = _seed_transcript(engine, author_a)
    _seed_transcript(engine, author_b)

    resp = client.post("/api/v1/transcripts/filter", json={"authorId": author_a})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["items"][0]["id"] == match_id


def test_filter_combines_multiple_criteria_and_paginates(client, engine):
    author_id = _seed_author(engine)
    match_id = _seed_transcript(
        engine, author_id, domain=["Fintech Payments"], geography=["Europe"], price=100
    )
    _seed_transcript(engine, author_id, domain=["Fintech Payments"], geography=["South Asia"], price=100)
    _seed_transcript(engine, author_id, domain=["HR Tech"], geography=["Europe"], price=100)

    resp = client.post(
        "/api/v1/transcripts/filter",
        json={"domain": ["Fintech Payments"], "geography": ["Europe"], "page": 1, "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["meta"]["total"] == 1
    assert body["meta"]["limit"] == 5
    assert body["items"][0]["id"] == match_id
