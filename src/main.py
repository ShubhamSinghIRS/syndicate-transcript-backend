import logging

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from apis.middlewares.jwt import jwt_middleware
from apis.middlewares.security_headers import security_headers_middleware
from apis.routes import api_router
from config import get_settings
from logging_config import setup_logging
from utils.response import error_response

setup_logging()
logger = logging.getLogger(__name__)

if not get_settings().email.is_configured:
    logger.warning("SendGrid is not configured (SENDGRID_API_KEY/FROM_EMAIL) - emails will not be sent.")

_docs_enabled = get_settings().services.enable_docs
app = FastAPI(
    title="Syndicate Transcript Backend",
    version="1.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

app.add_middleware(BaseHTTPMiddleware, dispatch=jwt_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().services.cors_origins,
    allow_credentials=True,
    # Narrowed to what the frontend actually sends/uses - no route here
    # accepts PUT/PATCH, and no browser request needs a header beyond these
    # two (the webhook's X-Razorpay-* headers are server-to-server, not
    # subject to CORS at all).
    allow_methods=["GET", "POST", "DELETE"],
    # Idempotency-Key is a custom header sent by the browser on POST /api/orders
    # (create order / "buy transcript"). It must be allow-listed or the CORS
    # preflight fails with "Disallowed CORS headers" and the buy request is blocked.
    # Auth is cookie-based (see apis/middlewares/jwt.py) - no Authorization header needed.
    allow_headers=["Content-Type", "Idempotency-Key"],
)

# Outermost: assign/propagate X-Request-ID so every log line carries the correlation id.
app.add_middleware(CorrelationIdMiddleware)

app.include_router(api_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    # detail can be a dict ({"message": ..., "data": ...}) for structured errors.
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message", "Error")
        data = exc.detail.get("data")
        return JSONResponse(status_code=exc.status_code, content=error_response(message, data))
    return JSONResponse(status_code=exc.status_code, content=error_response(str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = exc.errors()
    message = errors[0]["msg"] if errors else "Validation error"
    return JSONResponse(status_code=422, content=error_response(message))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    # Safety net only - every handler already catches its own exceptions and
    # raises a generic HTTPException(500); this exists so a future handler
    # that forgets to would still return a clean response instead of leaking
    # an internal stack trace.
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content=error_response("Internal error"))
