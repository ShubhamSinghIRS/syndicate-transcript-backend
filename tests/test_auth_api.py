import hashlib
from urllib.parse import parse_qs, urlparse

from sqlalchemy import text

# Matches _TEST_ENV's CORS_ALLOWED_ORIGINS in conftest.py - /refresh and
# /logout now check Origin (CSRF defense), so any test hitting them must send
# what a real browser would.
_ORIGIN_HEADERS = {"Origin": "http://localhost:5173"}


def _signup(client, monkeypatch, email="jane@example.com", password="s3cret1234", name="Jane Doe"):
    captured = {}

    def fake_send_otp(to_email, otp):
        captured["otp"] = otp

    monkeypatch.setattr("apis.controllers.auth.auth_handler.send_registration_otp", fake_send_otp)

    resp = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "companyName": "Acme Inc"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["data"]["tempToken"], captured["otp"]


def _signup_and_verify(client, monkeypatch, email="jane@example.com", password="s3cret1234", name="Jane Doe"):
    pending_token, otp = _signup(client, monkeypatch, email=email, password=password, name=name)
    return client.post("/api/v1/auth/register/verify-otp", json={"tempToken": pending_token, "otp": otp})


def test_docs_are_disabled_by_default(client):
    # ENABLE_DOCS isn't set in the test environment, so these must not serve
    # real Swagger/ReDoc/OpenAPI content - the API surface shouldn't be
    # publicly browsable unless explicitly opted into.
    for path in ("/docs", "/redoc", "/openapi.json"):
        resp = client.get(path)
        assert resp.status_code != 200, f"{path} should not be publicly accessible: {resp.text}"


def test_register_stores_account_before_verification(client, monkeypatch):
    resp = client.post(
        "/api/v1/auth/register",
        json={"name": "Jane Doe", "email": "jane@example.com", "password": "s3cret1234", "companyName": "Acme"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["tempToken"]

    # Not verified yet, so login must be rejected even with the correct password.
    resp = client.post("/api/v1/auth/login", json={"email": "jane@example.com", "password": "s3cret1234"})
    assert resp.status_code == 403
    assert resp.json()["data"]["tempToken"]


def test_register_is_rate_limited_by_ip(client):
    from apis.rate_limiting.limiter import RateLimits

    # No account exists yet for any of these - the limit is keyed by IP (the
    # test client's requests all share one), not by email.
    for i in range(RateLimits.auth.REGISTER_IP.max_attempts):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Rate Limit",
                "email": f"ratelimit{i}@example.com",
                "password": "s3cret1234",
                "companyName": "Acme",
            },
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/auth/register",
        json={"name": "One Too Many", "email": "onetoomany@example.com", "password": "s3cret1234", "companyName": "Acme"},
    )
    assert resp.status_code == 429, resp.text


def test_login_is_rate_limited_by_ip(client):
    from apis.rate_limiting.limiter import RateLimits

    # Wrong credentials against an account that doesn't even exist - the IP
    # counter increments before any account lookup, so this alone proves it.
    for _ in range(RateLimits.auth.LOGIN_IP.max_attempts):
        resp = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
        assert resp.status_code == 401, resp.text

    resp = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 429, resp.text


def test_login_otp_send_is_rate_limited_by_ip(client):
    from apis.rate_limiting.limiter import RateLimits

    for _ in range(RateLimits.auth.LOGIN_OTP_IP.max_attempts):
        resp = client.post("/api/v1/auth/login/otp/send", json={"email": "nobody@example.com"})
        assert resp.status_code == 401, resp.text

    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "nobody@example.com"})
    assert resp.status_code == 429, resp.text


def test_forgot_password_is_rate_limited_by_ip(client):
    from apis.rate_limiting.limiter import RateLimits

    for _ in range(RateLimits.auth.FORGOT_PASSWORD_IP.max_attempts):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200, resp.text

    resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 429, resp.text


def test_verify_otp_completes_registration_and_returns_token(client, monkeypatch):
    resp = _signup_and_verify(client, monkeypatch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["token"]
    assert body["data"]["user"]["email"] == "jane@example.com"
    assert body["data"]["user"]["companyName"] == "Acme Inc"


def test_verify_otp_with_wrong_code_fails(client, monkeypatch):
    pending_token, _ = _signup(client, monkeypatch, email="bob@example.com")

    resp = client.post("/api/v1/auth/register/verify-otp", json={"tempToken": pending_token, "otp": "000000"})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_verify_otp_with_invalid_pending_token_fails(client):
    resp = client.post("/api/v1/auth/register/verify-otp", json={"tempToken": "not-a-real-token", "otp": "123456"})
    assert resp.status_code == 401


def test_login_succeeds_after_verification(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="login@example.com", password="s3cret1234")

    resp = client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "s3cret1234"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["token"]


def test_login_with_wrong_password_fails(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="wrongpw@example.com", password="s3cret1234")

    resp = client.post("/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "nope"})
    assert resp.status_code == 401


def test_login_with_unknown_email_fails(client):
    resp = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "whatever"})
    assert resp.status_code == 401


def test_login_otp_send_and_verify_succeeds(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="otplogin@example.com", password="s3cret1234")

    captured = {}
    monkeypatch.setattr(
        "apis.controllers.auth.auth_handler.send_login_otp",
        lambda to_email, otp: captured.update(otp=otp),
    )
    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "otplogin@example.com"})
    assert resp.status_code == 200, resp.text
    pending_token = resp.json()["data"]["tempToken"]
    assert "otp" in captured

    resp = client.post(
        "/api/v1/auth/login/otp/verify", json={"tempToken": pending_token, "otp": captured["otp"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["token"]
    assert resp.json()["data"]["user"]["email"] == "otplogin@example.com"


def test_login_otp_send_for_unverified_account_fails(client, monkeypatch):
    _signup(client, monkeypatch, email="unverifiedotp@example.com")

    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "unverifiedotp@example.com"})
    assert resp.status_code == 401


def test_login_otp_send_for_unknown_email_fails(client):
    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "ghost@example.com"})
    assert resp.status_code == 401


def test_login_otp_verify_with_wrong_code_fails(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="otpwrong@example.com", password="s3cret1234")
    monkeypatch.setattr("apis.controllers.auth.auth_handler.send_login_otp", lambda to_email, otp: None)

    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "otpwrong@example.com"})
    pending_token = resp.json()["data"]["tempToken"]

    resp = client.post(
        "/api/v1/auth/login/otp/verify", json={"tempToken": pending_token, "otp": "000000"}
    )
    assert resp.status_code == 400


def test_login_otp_verify_with_invalid_pending_token_fails(client):
    resp = client.post(
        "/api/v1/auth/login/otp/verify", json={"tempToken": "not-a-real-token", "otp": "123456"}
    )
    assert resp.status_code == 401


def test_login_otp_verify_cannot_reuse_registration_pending_token(client, monkeypatch):
    # A registration pending token has a different JWT "purpose" claim and
    # must not be accepted by the OTP-login verify endpoint.
    pending_token, otp = _signup(client, monkeypatch, email="crosstoken@example.com")

    resp = client.post(
        "/api/v1/auth/login/otp/verify", json={"tempToken": pending_token, "otp": otp}
    )
    assert resp.status_code == 401


# Note: there used to be a test here confirming email-verification and
# login OTP rate limits don't interfere with each other. Since OTP fields
# moved onto `users` (one shared field-set, purpose implied by
# email_verified), that scenario is now structurally impossible rather than
# just tested-for: registration-OTP flows only ever touch unverified
# accounts, login-OTP flows only ever touch verified ones, and successful
# verification always clears otp_retry_count/otp_expire_time before the
# account could reach the other flow.


def _max_out_otp(engine, email: str, expiry_minutes: int, max_attempts: int, issued_at):
    from datetime import timedelta

    from sqlalchemy import text

    from services.crypto.email_crypto import hash_email

    expire_time = issued_at + timedelta(minutes=expiry_minutes)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET otp_hash = 'deadbeef', otp_expire_time = :expire_time, "
                "otp_retry_count = :retry_count WHERE email_hash = :email_hash"
            ),
            {"expire_time": expire_time, "retry_count": max_attempts, "email_hash": hash_email(email)},
        )


def test_login_otp_send_is_rate_limited_after_max_attempts(client, monkeypatch, engine):
    from datetime import datetime, timezone

    from apis.controllers.auth.auth_handler import RATE_LIMIT_LOGIN_OTP_MAX_ATTEMPTS, LOGIN_OTP_EXPIRY_MINUTES

    _signup_and_verify(client, monkeypatch, email="loginratelimit@example.com", password="s3cret1234")
    _max_out_otp(
        engine,
        "loginratelimit@example.com",
        LOGIN_OTP_EXPIRY_MINUTES,
        RATE_LIMIT_LOGIN_OTP_MAX_ATTEMPTS,
        datetime.now(timezone.utc),
    )

    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "loginratelimit@example.com"})
    assert resp.status_code == 429, resp.text


def test_login_otp_send_allowed_again_after_cooldown_expires(client, monkeypatch, engine):
    from datetime import datetime, timedelta, timezone

    from apis.controllers.auth.auth_handler import (
        RATE_LIMIT_LOGIN_OTP_MAX_ATTEMPTS,
        RATE_LIMIT_LOGIN_OTP_COOLDOWN_MINUTES,
        LOGIN_OTP_EXPIRY_MINUTES,
    )

    _signup_and_verify(client, monkeypatch, email="logincooldownover@example.com", password="s3cret1234")
    monkeypatch.setattr("apis.controllers.auth.auth_handler.send_login_otp", lambda to_email, otp: None)
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_LOGIN_OTP_COOLDOWN_MINUTES + 1)
    _max_out_otp(engine, "logincooldownover@example.com", LOGIN_OTP_EXPIRY_MINUTES, RATE_LIMIT_LOGIN_OTP_MAX_ATTEMPTS, long_ago)

    resp = client.post("/api/v1/auth/login/otp/send", json={"email": "logincooldownover@example.com"})
    assert resp.status_code == 200, resp.text


def test_registration_otp_resend_is_rate_limited_after_max_attempts(client, monkeypatch, engine):
    from datetime import datetime, timezone

    from apis.controllers.auth.auth_handler import (
        RATE_LIMIT_EMAIL_VERIFICATION_MAX_ATTEMPTS,
        EMAIL_VERIFICATION_OTP_EXPIRY_MINUTES,
    )

    pending_token, _ = _signup(client, monkeypatch, email="regratelimit@example.com")
    _max_out_otp(
        engine,
        "regratelimit@example.com",
        EMAIL_VERIFICATION_OTP_EXPIRY_MINUTES,
        RATE_LIMIT_EMAIL_VERIFICATION_MAX_ATTEMPTS,
        datetime.now(timezone.utc),
    )

    resp = client.post("/api/v1/auth/register/resend-otp", json={"tempToken": pending_token})
    assert resp.status_code == 429, resp.text


def test_login_blocked_then_resend_otp_then_verify_flow(client, monkeypatch):
    # Sign up but never verify - simulates the OTP window lapsing, and the
    # user closing the tab before completing verification.
    _signup(client, monkeypatch, email="lapsed@example.com", password="s3cret1234", name="Lapsed User")

    login_resp = client.post(
        "/api/v1/auth/login", json={"email": "lapsed@example.com", "password": "s3cret1234"}
    )
    assert login_resp.status_code == 403
    pending_token = login_resp.json()["data"]["tempToken"]

    captured = {}
    monkeypatch.setattr(
        "apis.controllers.auth.auth_handler.send_registration_otp",
        lambda to_email, otp: captured.update(otp=otp),
    )
    # The scenario is "comes back later", but the test runs both calls
    # milliseconds apart - clear the in-memory OTP-generation counters so the
    # 45s resend cooldown (meant for *rapid* resend clicks) doesn't fire here.
    from apis.rate_limiting.limiter import reset_rate_limits

    reset_rate_limits()
    resp = client.post("/api/v1/auth/register/resend-otp", json={"tempToken": pending_token})
    assert resp.status_code == 200, resp.text
    assert "otp" in captured
    refreshed_pending_token = resp.json()["data"]["tempToken"]

    resp = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"tempToken": refreshed_pending_token, "otp": captured["otp"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["token"]

    resp = client.post("/api/v1/auth/login", json={"email": "lapsed@example.com", "password": "s3cret1234"})
    assert resp.status_code == 200


def test_resend_otp_with_invalid_pending_token_fails(client):
    resp = client.post("/api/v1/auth/register/resend-otp", json={"tempToken": "not-a-real-token"})
    assert resp.status_code == 401


def test_resend_otp_for_already_verified_account_fails(client, monkeypatch):
    pending_token, otp = _signup(client, monkeypatch, email="alreadyverified@example.com", password="s3cret1234")
    client.post("/api/v1/auth/register/verify-otp", json={"tempToken": pending_token, "otp": otp})

    resp = client.post("/api/v1/auth/register/resend-otp", json={"tempToken": pending_token})
    assert resp.status_code == 409


def test_me_requires_auth(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["success"] is False


def test_me_returns_profile_with_valid_token(client, monkeypatch):
    verify_resp = _signup_and_verify(client, monkeypatch, email="profile@example.com")
    token = verify_resp.json()["data"]["token"]

    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["email"] == "profile@example.com"


def test_logout_without_cookie_still_succeeds(client):
    # Logout doesn't require a Bearer token (access tokens are short-lived,
    # logout must still work if it already expired) and is a no-op-but-200
    # even with nothing to revoke.
    resp = client.post("/api/v1/auth/logout", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_login_sets_refresh_cookie(client, monkeypatch):
    verify_resp = _signup_and_verify(client, monkeypatch, email="cookie@example.com")
    assert verify_resp.status_code == 200, verify_resp.text
    assert "refresh_token" in verify_resp.cookies


def test_logout_revokes_session_so_refresh_then_fails(client, monkeypatch):
    verify_resp = _signup_and_verify(client, monkeypatch, email="logout@example.com")
    assert "refresh_token" in verify_resp.cookies

    resp = client.post("/api/v1/auth/logout", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 401


def test_refresh_issues_new_access_token_and_rotates_cookie(client, monkeypatch):
    verify_resp = _signup_and_verify(client, monkeypatch, email="refresh@example.com")
    old_refresh_token = verify_resp.cookies["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["token"]
    # The rotated refresh token must differ from the one just used - that's
    # the actual rotation guarantee (two JWTs signed within the same second
    # with identical claims are legitimately byte-identical, so comparing
    # access tokens here wouldn't test anything meaningful).
    assert resp.cookies["refresh_token"] != old_refresh_token


def test_refresh_without_cookie_fails(client):
    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 401


def test_refresh_blocks_cross_site_origin(client, monkeypatch):
    # CSRF regression: a real refresh cookie is present (so this isn't just
    # test_refresh_without_cookie_fails in disguise), but the Origin is a
    # completely unrelated site - simulates a malicious page's blind POST.
    verify_resp = _signup_and_verify(client, monkeypatch, email="csrf-refresh@example.com")
    assert "refresh_token" in verify_resp.cookies

    resp = client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403, resp.text


def test_refresh_blocks_missing_origin_and_referer(client, monkeypatch):
    # Deliberately strict: no Origin and no Referer at all is also rejected,
    # not treated as same-site-by-default.
    verify_resp = _signup_and_verify(client, monkeypatch, email="csrf-noorigin@example.com")
    assert "refresh_token" in verify_resp.cookies

    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 403, resp.text


def test_refresh_accepts_matching_referer_without_origin(client, monkeypatch):
    # Origin is what real browsers send on POST, but the fallback to Referer
    # must also work for a legitimate same-site request that happens to omit it.
    verify_resp = _signup_and_verify(client, monkeypatch, email="csrf-referer@example.com")
    assert "refresh_token" in verify_resp.cookies

    resp = client.post("/api/v1/auth/refresh", headers={"Referer": "http://localhost:5173/checkout"})
    assert resp.status_code == 200, resp.text


def test_logout_blocks_cross_site_origin(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="csrf-logout@example.com")

    resp = client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403, resp.text


def test_refresh_reuse_of_rotated_out_token_revokes_whole_chain(client, monkeypatch):
    verify_resp = _signup_and_verify(client, monkeypatch, email="reuse@example.com")
    old_refresh_token = verify_resp.cookies["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 200, resp.text
    new_refresh_token = resp.cookies["refresh_token"]

    # Replay the original (now rotated-out) token - simulates a stolen token
    # being used after the legitimate client already rotated past it.
    client.cookies.set("refresh_token", old_refresh_token)
    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 401, resp.text

    # The legitimately-rotated token must now be revoked too - reuse
    # detection nukes the whole chain, not just the replayed token.
    client.cookies.set("refresh_token", new_refresh_token)
    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 401, resp.text


def test_refresh_with_expired_session_fails(client, monkeypatch, engine):
    from datetime import datetime, timedelta, timezone

    verify_resp = _signup_and_verify(client, monkeypatch, email="expiredsession@example.com")
    raw_token = verify_resp.cookies["refresh_token"]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET expires_at = :expires_at WHERE refresh_token_hash = :token_hash"),
            {"expires_at": datetime.now(timezone.utc) - timedelta(days=1), "token_hash": token_hash},
        )

    resp = client.post("/api/v1/auth/refresh", headers=_ORIGIN_HEADERS)
    assert resp.status_code == 401, resp.text


def test_forgot_password_then_reset_password_flow(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="reset@example.com", password="oldpass123")

    captured = {}
    monkeypatch.setattr(
        "apis.controllers.auth.auth_handler.send_password_reset_link",
        lambda to_email, reset_link: captured.update(reset_link=reset_link),
    )

    resp = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert resp.status_code == 200
    assert "reset_link" in captured

    token = parse_qs(urlparse(captured["reset_link"]).query)["token"][0]

    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "newpass123"})
    assert resp.status_code == 200, resp.text

    resp = client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "oldpass123"})
    assert resp.status_code == 401

    resp = client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "newpass123"})
    assert resp.status_code == 200


def test_forgot_password_for_unknown_email_still_returns_success(client):
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_reset_password_with_invalid_token_fails(client):
    resp = client.post("/api/v1/auth/reset-password", json={"token": "not-a-real-token", "password": "newpass123"})
    assert resp.status_code == 400


def test_reset_password_link_cannot_be_reused(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="reusereset@example.com", password="oldpass123")

    captured = {}
    monkeypatch.setattr(
        "apis.controllers.auth.auth_handler.send_password_reset_link",
        lambda to_email, reset_link: captured.update(reset_link=reset_link),
    )
    client.post("/api/v1/auth/forgot-password", json={"email": "reusereset@example.com"})
    token = parse_qs(urlparse(captured["reset_link"]).query)["token"][0]

    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "firstnewpass"})
    assert resp.status_code == 200, resp.text

    # Same link used again must fail - single-use enforced by nulling reset_token_hash.
    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "secondnewpass"})
    assert resp.status_code == 400, resp.text


def test_reset_password_revokes_existing_sessions(client, monkeypatch):
    _signup_and_verify(client, monkeypatch, email="revoke@example.com", password="oldpass123")
    old_refresh_token = client.cookies.get("refresh_token")
    assert old_refresh_token

    captured = {}
    monkeypatch.setattr(
        "apis.controllers.auth.auth_handler.send_password_reset_link",
        lambda to_email, reset_link: captured.update(reset_link=reset_link),
    )
    client.post("/api/v1/auth/forgot-password", json={"email": "revoke@example.com"})
    token = parse_qs(urlparse(captured["reset_link"]).query)["token"][0]

    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "newpass1234"})
    assert resp.status_code == 200, resp.text

    # A password reset is often a compromise response - the session from
    # before the reset must be dead even if an attacker still holds its
    # refresh-token cookie, not just the browser that performed the reset.
    resp = client.post(
        "/api/v1/auth/refresh", headers=_ORIGIN_HEADERS, cookies={"refresh_token": old_refresh_token}
    )
    assert resp.status_code == 401, resp.text


def test_login_locks_account_after_max_failed_attempts(client, monkeypatch):
    from apis.controllers.auth.auth_handler import RATE_LIMIT_LOGIN_LOCKOUT_MAX_ATTEMPTS

    _signup_and_verify(client, monkeypatch, email="lockout@example.com", password="correctpass123")

    for _ in range(RATE_LIMIT_LOGIN_LOCKOUT_MAX_ATTEMPTS):
        resp = client.post("/api/v1/auth/login", json={"email": "lockout@example.com", "password": "wrongpass"})
        assert resp.status_code == 401

    # Locked now - even the correct password is rejected until locked_until passes.
    resp = client.post("/api/v1/auth/login", json={"email": "lockout@example.com", "password": "correctpass123"})
    assert resp.status_code == 401, resp.text


def test_login_lockout_clears_after_successful_login(client, monkeypatch, engine):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from services.crypto.email_crypto import hash_email

    _signup_and_verify(client, monkeypatch, email="lockoutclears@example.com", password="correctpass123")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET failed_login_attempts = 4, "
                "locked_until = :locked_until WHERE email_hash = :email_hash"
            ),
            {
                "locked_until": datetime.now(timezone.utc) - timedelta(minutes=1),
                "email_hash": hash_email("lockoutclears@example.com"),
            },
        )

    resp = client.post(
        "/api/v1/auth/login", json={"email": "lockoutclears@example.com", "password": "correctpass123"}
    )
    assert resp.status_code == 200, resp.text

    with engine.begin() as conn:
        attempts = conn.execute(
            text("SELECT failed_login_attempts FROM users WHERE email_hash = :email_hash"),
            {"email_hash": hash_email("lockoutclears@example.com")},
        ).scalar_one()
    assert attempts == 0
