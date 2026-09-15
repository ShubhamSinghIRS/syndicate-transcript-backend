"""rename topic_requests.domain to domains

Revision ID: b3e8f1a4c7d2
Revises: a1c4d7e9f2b6
Create Date: 2026-08-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3e8f1a4c7d2'
down_revision: Union[str, None] = 'a1c4d7e9f2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Now an array column (see a1c4d7e9f2b6) - pluralize to match the naming
    # convention already used for array columns (Transcript.domains/geographies).
    #
    # Guarded like 3970e3b6a3d1: 8a88c8e366e2 rebuilds topic_requests via
    # Base.metadata.create_all against live models, so on a database migrated
    # from scratch today, the column is already named "domains" by the time
    # this migration runs.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("topic_requests")}

    if "domain" in columns and "domains" not in columns:
        op.alter_column('topic_requests', 'domain', new_column_name='domains')


def downgrade() -> None:
    op.alter_column('topic_requests', 'domains', new_column_name='domain')
