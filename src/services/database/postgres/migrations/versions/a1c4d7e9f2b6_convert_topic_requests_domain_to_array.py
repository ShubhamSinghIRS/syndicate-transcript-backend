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
