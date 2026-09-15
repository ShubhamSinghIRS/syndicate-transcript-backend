"""switch all primary and foreign keys to uuid

Revision ID: 8a88c8e366e2
Revises: e3681963f464
Create Date: 2026-08-17 08:10:41.600000

Sequential integer ids are guessable/enumerable (e.g. iterating order_id or
user_id to probe other users' data). This migration drops every app table and
recreates it from the updated models, where every id/foreign-key column is now
UUID instead of BigInteger. There is no in-place ALTER path from int to
unrelated UUID values, so this intentionally deletes all existing rows -
authorized as a full reset of the transcripts/orders/users data.
"""
from typing import Sequence, Union

from alembic import op

import apis.models  # noqa: F401 -- registers every table on Base.metadata
from services.database.postgres.connection import Base

# revision identifiers, used by Alembic.
revision: str = '8a88c8e366e2'
down_revision: Union[str, None] = 'e3681963f464'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Any table depends only on others in this same list, so CASCADE covers FK order.
_TABLES = [
    "coupon_redemptions",
    "order_items",
    "cart_items",
    "receipts",
    "payments",
    "sessions",
    "support_tickets",
    "topic_requests",
    "orders",
    "carts",
    "coupons",
    "transcripts",
    "users",
]


def upgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    # Scoped to _TABLES only - Base.metadata also includes tables added by
    # later migrations (e.g. transcript_filter_bounds), which would otherwise
    # get created here too and collide with their own explicit CREATE TABLE
    # when replaying the full history against a fresh database.
    Base.metadata.create_all(bind=conn, tables=[Base.metadata.tables[t] for t in _TABLES])


def downgrade() -> None:
    # Not meaningfully reversible: the previous schema's integer ids can't be
    # reconstructed from UUIDs, and upgrade() already destroyed the old data.
    # This just leaves the database empty rather than half-migrated.
    conn = op.get_bind()
    for table in _TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
