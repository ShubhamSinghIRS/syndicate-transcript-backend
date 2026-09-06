import re

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from apis.rate_limiting.limiter import RateLimitPolicy, RateLimits
from apis.routes.paths import P
from apis.security import decode_access_token
from config import get_settings
from utils.cookies import ACCESS_COOKIE_NAME
from utils.csrf import verify_same_origin
from utils.request_meta import get_ip_address
from utils.response import error_response

# Per-request auth gate: public, soft-auth, or requires login. Also applies
# the two generic rate-limit catch-alls (IP for public/soft-auth, user for
# authenticated) that apply to every request regardless of route. Anything
# more specific (per-endpoint IP limits, OTP-generation limits, etc.) lives as
# route-level dependencies in apis/rate_limiting/dependencies.py instead, so
# this file stays a simple, business-logic-free auth gate.
#
# Every path below is built from apis.routes.paths.P rather than hardcoded as
# a literal string, so this gate can't silently drift out of sync with the
# actual route table (e.g. after an API version bump) the way two independent
# copies of the same path would.

# Dynamic id - scoped to one segment so /me/purchased, /{id}/view|download stay protected.
PUBLIC_PATH_RE = re.compile(rf"^{re.escape(P.transcripts.BASE)}/[^/]+$")

# Also public, like the detail page itself - unlike /view|download, there's no
# entitlement being checked here, just a read-only recommendation list.
PUBLIC_TRANSCRIPT_SUBPATH_RE = re.compile(rf"^{re.escape(P.transcripts.BASE)}/[^/]+/similar$")

# Verified via gateway signature instead - and unversioned, since this URL is
# registered directly in the payment gateway's dashboard (see paths.py).
WEBHOOK_PATH_RE = re.compile(rf"^{re.escape(P.orders_webhook.BASE)}/webhook/[^/]+$")

# Server-to-server transcript ingest from the Infollion backend - authenticated by a
# shared x-api-key at the route level (see apis/dependencies.verify_ingest_api_key),
# so it bypasses the JWT gate. Treated like webhooks: exempt from IP rate-limiting too.
INGEST_PATH_RE = re.compile(rf"^{re.escape(P.transcript_ingest.BASE)}(/[^/]+)?$")

# Bearer token decoded if present, but not required. .../cart/merge excluded.
SOFT_AUTH_PATHS = {P.cart.BASE, P.support.BASE, f"{P.topics.BASE}{P.topics.REQUEST}"}
SOFT_AUTH_PATH_RE = re.compile(rf"^{re.escape(P.cart.BASE + P.cart.ITEMS)}(/[^/]+)?$")

_DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"} if get_settings().services.enable_docs else set()

UNPROTECTED_PATHS = {
    P.system.HEALTH,
    *_DOCS_PATHS,
    f"{P.auth.BASE}{P.auth.REGISTER}",
    f"{P.auth.BASE}{P.auth.REGISTER_VERIFY_OTP}",
    f"{P.auth.BASE}{P.auth.REGISTER_RESEND_OTP}",
    f"{P.auth.BASE}{P.auth.LOGIN}",
    f"{P.auth.BASE}{P.auth.LOGIN_OTP_SEND}",
    f"{P.auth.BASE}{P.auth.LOGIN_OTP_VERIFY}",
    f"{P.auth.BASE}{P.auth.REFRESH}",
    f"{P.auth.BASE}{P.auth.LOGOUT}",
    f"{P.auth.BASE}{P.auth.FORGOT_PASSWORD}",
    f"{P.auth.BASE}{P.auth.RESET_PASSWORD}",
    P.transcripts.BASE,
    f"{P.transcripts.BASE}{P.transcripts.DOMAINS}",
}


def _rate_limit_response(policy: RateLimitPolicy, key: str) -> JSONResponse | None:
    try:
        policy.check(key)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=error_response(str(exc.detail)))
    return None


def _csrf_response(request: Request) -> JSONResponse | None:
    # The access-token cookie is attached by the browser to any cross-site
    # request automatically, so state-changing requests need an explicit
    # same-origin check the way header-based auth never did. Safe/read-only
    # GETs are left alone.
    if request.method == "GET":
        return None
    try:
        verify_same_origin(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=error_response(str(exc.detail)))
    return None


async def jwt_middleware(request: Request, call_next):
    path = request.url.path

    # Fully public, unauthenticated - webhooks excluded (server-to-server,
    # protected by gateway signature instead; IP-limiting them risks dropping
    # legitimate redelivery bursts from the gateway's own IP pool).
    if (
        path in UNPROTECTED_PATHS
        or PUBLIC_PATH_RE.match(path)
        or PUBLIC_TRANSCRIPT_SUBPATH_RE.match(path)
        or WEBHOOK_PATH_RE.match(path)
        or INGEST_PATH_RE.match(path)
    ):
        if not (WEBHOOK_PATH_RE.match(path) or INGEST_PATH_RE.match(path)):
            ip_address = get_ip_address(request)
            if ip_address:
                blocked = _rate_limit_response(RateLimits.general.PUBLIC_IP, f"public:{ip_address}")
                if blocked:
                    return blocked
        return await call_next(request)

    # Soft-auth: optional login, but still unauthenticated-reachable.
    if path in SOFT_AUTH_PATHS or SOFT_AUTH_PATH_RE.match(path):
        ip_address = get_ip_address(request)
        if ip_address:
            blocked = _rate_limit_response(RateLimits.general.PUBLIC_IP, f"public:{ip_address}")
            if blocked:
                return blocked

        blocked = _csrf_response(request)
        if blocked:
            return blocked

        token = request.cookies.get(ACCESS_COOKIE_NAME)
        if token:
            payload = decode_access_token(token)
            if payload is None:
                # Cookie present but expired/invalid - unlike a genuinely
                # anonymous visitor (no cookie at all), this is a logged-in
                # user whose token lapsed. 401 so the frontend's existing
                # refresh-and-retry logic runs instead of this silently
                # falling back to an anonymous submission.
                return JSONResponse(status_code=401, content=error_response("Invalid or expired token"))
            request.state.user_id = payload.get("user_id")
        return await call_next(request)

    # Hard auth required.
    blocked = _csrf_response(request)
    if blocked:
        return blocked

    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content=error_response("Not authenticated"))

    payload = decode_access_token(token)
    if payload is None:
        return JSONResponse(status_code=401, content=error_response("Invalid or expired token"))

    request.state.user_id = payload.get("user_id")
    request.state.user_name = payload.get("user_name")
    request.state.email = payload.get("email")
    request.state.access_token_exp = payload.get("exp")

    blocked = _rate_limit_response(RateLimits.general.AUTHENTICATED_USER, f"user:{request.state.user_id}")
    if blocked:
        return blocked

    return await call_next(request)
