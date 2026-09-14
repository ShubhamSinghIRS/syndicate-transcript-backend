# Versioned - everything the frontend calls. Bump _API_V1 (and add a parallel
# v2 base) if a future breaking change needs both versions live at once.
_API_V1 = "/api/v1"
_AUTH = f"{_API_V1}/auth"
_USERS = f"{_API_V1}/users"
_TRANSCRIPTS = f"{_API_V1}/transcripts"
_CART = f"{_API_V1}/cart"
_ORDERS = f"{_API_V1}/orders"
_SUPPORT = f"{_API_V1}/support"
_TOPICS = f"{_API_V1}/topics"

# Unversioned - these URLs are registered outside this codebase (the payment
# gateway's webhook config, the Infollion backend's ingest client), so they
# can't move in lockstep with our own API version the way frontend-facing
# routes can. Changing either requires updating the other side first.
_ORDERS_WEBHOOK = "/api/orders"
_INTERNAL_TRANSCRIPTS = "/api/internal/transcripts"  # server-to-server ingest (x-api-key)


class P:
    class system:
        HEALTH = "/health"

    class auth:
        BASE = _AUTH
        REGISTER = "/register"
        REGISTER_VERIFY_OTP = "/register/verify-otp"
        REGISTER_RESEND_OTP = "/register/resend-otp"
        LOGIN = "/login"
        LOGIN_OTP_SEND = "/login/otp/send"
        LOGIN_OTP_VERIFY = "/login/otp/verify"
        REFRESH = "/refresh"
        LOGOUT = "/logout"
        FORGOT_PASSWORD = "/forgot-password"
        RESET_PASSWORD = "/reset-password"

    class users:
        BASE = _USERS
        ME = "/me"

    class transcripts:
        BASE = _TRANSCRIPTS
        LIST = ""
        FILTER = "/filter"
        MY_PURCHASED = "/me/purchased"
        DOMAINS = "/domains"
        FILTER_OPTIONS = "/filter-options"
        DETAIL = "/{transcript_id}"
        SIMILAR = "/{transcript_id}/similar"
        VIEW = "/{transcript_id}/view"
        DOWNLOAD = "/{transcript_id}/download"

    class cart:
        BASE = _CART
        ROOT = ""
        ITEMS = "/items"
        ITEM_DETAIL = "/items/{transcript_id}"
        MERGE = "/merge"

    class orders:
        BASE = _ORDERS
        ROOT = ""
        VERIFY = "/verify"
        DETAIL = "/{order_id}"
        RECEIPT = "/{order_id}/receipt"

    # Kept on its own unversioned base - see _ORDERS_WEBHOOK above.
    class orders_webhook:
        BASE = _ORDERS_WEBHOOK
        WEBHOOK = "/webhook/{gateway}"

    class support:
        BASE = _SUPPORT
        ROOT = ""

    class topics:
        BASE = _TOPICS
        REQUEST = "/request"
        MY_REQUESTS = "/my-requests"
        DETAIL = "/{request_id}"

    # Internal server-to-server ingest from the Infollion backend (x-api-key auth).
    class transcript_ingest:
        BASE = _INTERNAL_TRANSCRIPTS
        PUBLISH = ""  # POST  /api/internal/transcripts
        DETAIL = "/{transcript_id}"  # PATCH /api/internal/transcripts/{id}
