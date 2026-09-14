"""Cross-cutting regression test: proves a random authenticated user cannot
see or act on another user's data through any ID-taking endpoint. Individual
endpoints already have their own narrower tests elsewhere; this test exists
to check the boundary holistically, in one place, the way an attacker
actually would - by taking one victim's real IDs and hitting every
ownership-sensitive route with a different user's token.
"""
from test_orders_api import _create_order, _use_fake_gateway, _verify
from test_transcripts_api import _auth_headers, _seed_author, _seed_transcript, _signup_and_verify


def test_random_user_cannot_access_another_users_data(client, monkeypatch, engine):
    _use_fake_gateway(monkeypatch)

    # Victim: signs up, buys a transcript, has a real paid order + entitlement.
    victim_token, victim_user_id = _signup_and_verify(client, monkeypatch, email="victim@example.com")
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    create_resp = _create_order(client, victim_token, [transcript_id])
    assert create_resp.status_code == 200, create_resp.text
    razorpay_order_id = create_resp.json()["data"]["razorpayOrderId"]
    victim_order_id = create_resp.json()["data"]["orderId"]

    verify_resp = _verify(client, victim_token, razorpay_order_id)
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["data"]["status"] == "paid"

    # Attacker: a completely unrelated, real, logged-in user - not an anonymous
    # caller, since that's a weaker test (this proves auth alone isn't enough,
    # ownership must also be checked).
    attacker_token, attacker_user_id = _signup_and_verify(client, monkeypatch, email="attacker@example.com")
    assert attacker_user_id != victim_user_id
    attacker_headers = _auth_headers(attacker_token)

    # 1. Transcript content - attacker never purchased this, must be blocked
    # even though they have a completely valid token for their own account.
    resp = client.get(f"/api/v1/transcripts/{transcript_id}/full-text", headers=attacker_headers)
    assert resp.status_code == 403, resp.text

    resp = client.get(f"/api/v1/transcripts/{transcript_id}/download", headers=attacker_headers)
    assert resp.status_code == 403, resp.text

    # 2. Victim's order - by ID, list, and receipt.
    resp = client.get(f"/api/v1/orders/{victim_order_id}", headers=attacker_headers)
    assert resp.status_code == 404, resp.text

    resp = client.get(f"/api/v1/orders/{victim_order_id}/receipt", headers=attacker_headers)
    assert resp.status_code == 404, resp.text

    resp = client.get("/api/v1/orders", headers=attacker_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []  # attacker's own order list, not the victim's

    # 3. Victim's purchase can't be verified again by the attacker to try to
    # confirm/hijack it onto their own account.
    resp = client.post(
        "/api/v1/orders/verify",
        json={
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "valid-signature",
        },
        headers=attacker_headers,
    )
    assert resp.status_code == 404, resp.text

    # 4. "My purchased" must reflect the attacker's own entitlements only.
    resp = client.get("/api/v1/transcripts/me/purchased", headers=attacker_headers)
    assert resp.status_code == 200, resp.text
    purchased_ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert transcript_id not in purchased_ids

    # Sanity check the other direction too - the victim really can do all of
    # this for their own data, so the blocks above are ownership checks, not
    # some unrelated failure making every one of these calls fail for anyone.
    victim_headers = _auth_headers(victim_token)
    assert client.get(f"/api/v1/transcripts/{transcript_id}/full-text", headers=victim_headers).status_code == 200
    assert client.get(f"/api/v1/orders/{victim_order_id}", headers=victim_headers).status_code == 200
    assert client.get(f"/api/v1/orders/{victim_order_id}/receipt", headers=victim_headers).status_code == 200
    victim_purchased = client.get("/api/v1/transcripts/me/purchased", headers=victim_headers)
    assert transcript_id in [item["id"] for item in victim_purchased.json()["data"]["items"]]
