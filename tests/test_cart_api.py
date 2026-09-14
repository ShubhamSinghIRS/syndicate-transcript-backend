from test_transcripts_api import _auth_headers, _seed_author, _seed_transcript, _signup_and_verify
from utils.cookies import GUEST_CART_COOKIE_NAME


def test_get_empty_cart_for_new_guest(client):
    resp = client.get("/api/v1/cart")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []
    assert GUEST_CART_COOKIE_NAME in resp.cookies


def test_add_item_to_guest_cart_then_fetch(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    add_resp = client.post("/api/v1/cart/items", json={"transcriptId": transcript_id})
    assert add_resp.status_code == 200, add_resp.text
    assert [i["id"] for i in add_resp.json()["data"]["items"]] == [transcript_id]

    get_resp = client.get("/api/v1/cart")
    assert get_resp.status_code == 200, get_resp.text
    items = get_resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == transcript_id
    assert items[0]["price"]
    assert items[0]["author"] is not None


def test_add_same_item_twice_is_idempotent(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    client.post("/api/v1/cart/items", json={"transcriptId": transcript_id})
    resp = client.post("/api/v1/cart/items", json={"transcriptId": transcript_id})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]["items"]) == 1


def test_add_item_rejects_missing_or_inactive_transcript(client, engine):
    resp = client.post("/api/v1/cart/items", json={"transcriptId": 999999})
    assert resp.status_code == 404, resp.text


def test_remove_item_from_guest_cart(client, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)
    client.post("/api/v1/cart/items", json={"transcriptId": transcript_id})

    resp = client.delete(f"/api/v1/cart/items/{transcript_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []

    # Removing again is a no-op, not a 404.
    resp = client.delete(f"/api/v1/cart/items/{transcript_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []


def test_clear_guest_cart(client, engine):
    author_id = _seed_author(engine)
    t1 = _seed_transcript(engine, author_id, topic="Topic A")
    t2 = _seed_transcript(engine, author_id, topic="Topic B")
    client.post("/api/v1/cart/items", json={"transcriptId": t1})
    client.post("/api/v1/cart/items", json={"transcriptId": t2})

    resp = client.delete("/api/v1/cart")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []

    resp = client.get("/api/v1/cart")
    assert resp.json()["data"]["items"] == []


def test_add_item_as_authenticated_user_lands_in_user_cart(client, monkeypatch, engine):
    token, _ = _signup_and_verify(client, monkeypatch)
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    resp = client.post(
        "/api/v1/cart/items", json={"transcriptId": transcript_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert [i["id"] for i in resp.json()["data"]["items"]] == [transcript_id]
    # No guest cookie should be involved for an authenticated request.
    assert GUEST_CART_COOKIE_NAME not in resp.cookies

    get_resp = client.get("/api/v1/cart", headers=_auth_headers(token))
    assert [i["id"] for i in get_resp.json()["data"]["items"]] == [transcript_id]


def test_merge_requires_auth(client):
    resp = client.post("/api/v1/cart/merge", json={"items": []})
    assert resp.status_code == 401


def test_merge_combines_guest_and_body_items_into_user_cart(client, monkeypatch, engine):
    author_id = _seed_author(engine)
    guest_item_id = _seed_transcript(engine, author_id, topic="Guest item")
    body_item_id = _seed_transcript(engine, author_id, topic="Body item")

    # Shop as a guest first - this sets the guest cart cookie on `client`.
    add_resp = client.post("/api/v1/cart/items", json={"transcriptId": guest_item_id})
    assert GUEST_CART_COOKIE_NAME in add_resp.cookies

    # Now register/verify using the SAME client, so the guest cookie is still attached.
    token, _ = _signup_and_verify(client, monkeypatch)

    merge_resp = client.post(
        "/api/v1/cart/merge", json={"items": [body_item_id]}, headers=_auth_headers(token)
    )
    assert merge_resp.status_code == 200, merge_resp.text
    merged_ids = {i["id"] for i in merge_resp.json()["data"]["items"]}
    assert merged_ids == {guest_item_id, body_item_id}

    # Guest cookie should be cleared after a successful merge.
    assert merge_resp.cookies.get(GUEST_CART_COOKIE_NAME) is None


def test_merge_dedupes_against_existing_user_cart_item(client, monkeypatch, engine):
    author_id = _seed_author(engine)
    shared_item_id = _seed_transcript(engine, author_id, topic="Shared item")

    token, _ = _signup_and_verify(client, monkeypatch)
    client.post("/api/v1/cart/items", json={"transcriptId": shared_item_id}, headers=_auth_headers(token))

    merge_resp = client.post(
        "/api/v1/cart/merge", json={"items": [shared_item_id]}, headers=_auth_headers(token)
    )
    assert merge_resp.status_code == 200, merge_resp.text
    assert [i["id"] for i in merge_resp.json()["data"]["items"]] == [shared_item_id]


def test_merge_with_no_guest_cookie_still_applies_body_items(client, monkeypatch, engine):
    author_id = _seed_author(engine)
    transcript_id = _seed_transcript(engine, author_id)

    token, _ = _signup_and_verify(client, monkeypatch)
    merge_resp = client.post(
        "/api/v1/cart/merge", json={"items": [transcript_id]}, headers=_auth_headers(token)
    )
    assert merge_resp.status_code == 200, merge_resp.text
    assert [i["id"] for i in merge_resp.json()["data"]["items"]] == [transcript_id]
