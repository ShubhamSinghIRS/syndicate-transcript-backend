"""rename topic_requests.domain to domains

Revision ID: b3e8f1a4c7d2
Revises: a1c4d7e9f2b6
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3e8f1a4c7d2'
down_revision: Union[str, None] = 'a1c4d7e9f2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Now an array column (see a1c4d7e9f2b6) - pluralize to match the naming
    # convention already used for array columns (Transcript.domains/geographies).
    op.alter_column('topic_requests', 'domain', new_column_name='domains')


def downgrade() -> None:
    op.alter_column('topic_requests', 'domains', new_column_name='domain')
