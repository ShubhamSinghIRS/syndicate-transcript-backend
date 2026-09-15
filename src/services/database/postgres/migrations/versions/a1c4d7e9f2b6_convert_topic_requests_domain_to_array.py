"""convert topic_requests.domain to array

Revision ID: a1c4d7e9f2b6
Revises: f7c2a9e4b1d3
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c4d7e9f2b6'
down_revision: Union[str, None] = 'f7c2a9e4b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The frontend multi-select was joining several domains into one ", "-separated
    # string before this; string_to_array recovers the original list for existing rows.
    #
    # Guarded like 3970e3b6a3d1: 8a88c8e366e2 rebuilds topic_requests via
    # Base.metadata.create_all against live models, so on a database migrated
    # from scratch today, the column is already named "domains" (plural, array
    # type) by the time this migration runs - there's no "domain" left to alter.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("topic_requests")}

    if "domain" in columns:
        op.alter_column(
            'topic_requests',
            'domain',
            type_=postgresql.ARRAY(sa.String()),
            postgresql_using="string_to_array(domain, ', ')",
        )


def downgrade() -> None:
    op.alter_column(
        'topic_requests',
        'domain',
        type_=sa.String(),
        postgresql_using="array_to_string(domain, ', ')",
    )
