import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from config import get_settings

JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "syndicate-transcript-backend"
PENDING_VERIFICATION_PURPOSE = "email_verification"
PENDING_VERIFICATION_EXPIRY_MINUTES = 15
OTP_LOGIN_PURPOSE = "otp_login"
OTP_LOGIN_EXPIRY_MINUTES = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # bcrypt>=4.0 raises instead of truncating for passwords over 72 bytes -
        # treat as a non-match rather than a 500, same as any other wrong password.
        return False


def create_access_token(*, user_id: uuid.UUID, user_name: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user_id),
        "user_name": user_name,
        "email": email,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth.access_token_expiry_minutes),
    }
    return jwt.encode(payload, settings.auth.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.auth.jwt_secret, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE)
    except JWTError:
        return None


def _create_purpose_token(*, purpose: str, expiry_minutes: int, user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": purpose,
        "user_id": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expiry_minutes),
    }
    return jwt.encode(payload, settings.auth.jwt_secret, algorithm=JWT_ALGORITHM)


def _decode_purpose_token(token: str, *, purpose: str) -> uuid.UUID | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    user_id = payload.get("user_id")
    return uuid.UUID(user_id) if user_id else None


def create_pending_verification_token(user_id: uuid.UUID) -> str:
    # Carries only user_id, so decode_access_token can't mistake it for a real token.
    return _create_purpose_token(
        purpose=PENDING_VERIFICATION_PURPOSE, expiry_minutes=PENDING_VERIFICATION_EXPIRY_MINUTES, user_id=user_id
    )


def decode_pending_verification_token(token: str) -> uuid.UUID | None:
    return _decode_purpose_token(token, purpose=PENDING_VERIFICATION_PURPOSE)


def create_otp_login_token(user_id: uuid.UUID) -> str:
    # Own purpose so it can't be replayed against the email-verification endpoints.
    return _create_purpose_token(purpose=OTP_LOGIN_PURPOSE, expiry_minutes=OTP_LOGIN_EXPIRY_MINUTES, user_id=user_id)


def decode_otp_login_token(token: str) -> uuid.UUID | None:
    return _decode_purpose_token(token, purpose=OTP_LOGIN_PURPOSE)
