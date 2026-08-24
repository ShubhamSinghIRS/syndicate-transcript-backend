from fastapi import Response

REFRESH_COOKIE_NAME = "refresh_token"
GUEST_CART_COOKIE_NAME = "guest_id"
ACCESS_COOKIE_NAME = "access_token"

SECONDS_PER_DAY = 86400
SECONDS_PER_MINUTE = 60


def _samesite(secure: bool) -> str:
    return "none" if secure else "lax"


def set_access_cookie(response: Response, token: str, secure: bool, max_age_minutes: int) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        max_age=max_age_minutes * SECONDS_PER_MINUTE,
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
        path="/",
    )


def clear_access_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
    )


def set_refresh_cookie(response: Response, token: str, secure: bool, max_age_days: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age_days * SECONDS_PER_DAY,
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
    )


def set_guest_cart_cookie(response: Response, guest_id: str, secure: bool, max_age_days: int = 180) -> None:
    response.set_cookie(
        key=GUEST_CART_COOKIE_NAME,
        value=guest_id,
        max_age=max_age_days * SECONDS_PER_DAY,
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
        path="/api/cart",
    )


def clear_guest_cart_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        key=GUEST_CART_COOKIE_NAME,
        path="/api/cart",
        httponly=True,
        secure=secure,
        samesite=_samesite(secure),
    )
