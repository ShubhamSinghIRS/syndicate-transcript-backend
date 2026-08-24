import os
import sys

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

load_dotenv()

_TEST_DB_ENV = "TRANSCRIPT_TEST_DATABASE_URL"
_TEST_ENV = {
    "ENVIRONMENT": "development",
    "JWT_SECRET": "test-jwt-secret",
    "ACCESS_TOKEN_EXPIRY_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRY_DAYS": "30",
    "COOKIE_SECURE": "false",
    "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
    "FRONTEND_BASE_URL": "http://localhost:5173",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "console",
    # Dummy but non-empty so PaymentConfig.is_configured is True in tests -
    # RazorpayService itself is monkeypatched, these values are never used
    # to make a real request.
    "RAZORPAY_KEY_ID": "rzp_test_dummy",
    "RAZORPAY_KEY_SECRET": "dummy_secret",
    "RAZORPAY_WEBHOOK_SECRET": "dummy_webhook_secret",
    "PAYMENT_CURRENCY": "USD",
}


def _database_url() -> str | None:
    return os.getenv(_TEST_DB_ENV, "").strip() or None


def _warn_if_shared_with_dev(url: str) -> None:
    dev_url = os.getenv("DATABASE_URL", "").strip()
    if dev_url and url == dev_url:
        print(
            f"\nWARNING: {_TEST_DB_ENV} is the same database as DATABASE_URL. "
            "Every test run TRUNCATEs sessions/order_items/orders/cart_items/carts/transcripts/"
            "users, erasing all real data in this database. Proceeding because this was an explicit choice.\n",
            file=sys.stderr,
        )


@pytest.fixture(scope="session")
def engine():
    url = _database_url()
    if not url:
        pytest.skip(f"{_TEST_DB_ENV} not set; skipping Postgres-backed tests")
    _warn_if_shared_with_dev(url)

    os.environ.update(_TEST_ENV)
    os.environ["DATABASE_URL"] = url

    import apis.models  # noqa: F401 -- registers models on Base.metadata
    from services.database.postgres.connection import Base

    eng = create_engine(url, future=True, pool_pre_ping=True)

    # Schema is owned by Alembic. Don't create/drop it here - just fail loudly
    # if migrations haven't been applied yet, so the schema never depends on
    # this fixture and a test run can't leave the shared dev DB schema-less.
    existing_tables = set(inspect(eng).get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - existing_tables
    if missing:
        pytest.exit(f"Tables missing: {sorted(missing)}. Run `alembic upgrade head` first.", returncode=1)

    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(request):
    if "engine" in request.fixturenames:
        eng = request.getfixturevalue("engine")
        with eng.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE sessions, receipts, payments, order_items, orders, cart_items, carts, "
                    "support_tickets, topic_requests, transcripts, users RESTART IDENTITY CASCADE"
                )
            )
    yield


@pytest.fixture()
def client(engine):
    import config

    config._settings = None
    import apis.dependencies as dependencies

    dependencies._orders_controller = None
    from apis.rate_limiting.limiter import reset_rate_limits

    reset_rate_limits()
    import main

    with TestClient(main.app) as c:
        yield c
