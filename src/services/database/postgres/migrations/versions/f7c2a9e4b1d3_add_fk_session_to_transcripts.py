"""add fk_session to transcripts (idempotency key for Infollion publish upserts)

Revision ID: f7c2a9e4b1d3
Revises: ce5614d07d2d
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c2a9e4b1d3'
down_revision: Union[str, None] = 'fc4468e7a504'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # fk_session = the Infollion syndicate_sessions.id. It is the idempotency key the
    # publish endpoint upserts on (INSERT ... ON CONFLICT (fk_session) DO UPDATE).
    # Nullable so any pre-existing rows (which predate this integration) stay valid;
    # UNIQUE so a re-publish updates the same row instead of inserting a duplicate.
    #
    # Guarded like 3970e3b6a3d1: 8a88c8e366e2 rebuilds transcripts via
    # Base.metadata.create_all against live models, so on a database migrated
    # from scratch today, fk_session (and its unique constraint) already exists
    # by the time this migration runs.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("transcripts")}
    unique_constraints = inspector.get_unique_constraints("transcripts")

    if "fk_session" not in columns:
        op.add_column('transcripts', sa.Column('fk_session', sa.BigInteger(), nullable=True))
    if not any(uq["column_names"] == ["fk_session"] for uq in unique_constraints):
        op.create_unique_constraint('uq_transcripts_fk_session', 'transcripts', ['fk_session'])


def downgrade() -> None:
    op.drop_constraint('uq_transcripts_fk_session', 'transcripts', type_='unique')
    op.drop_column('transcripts', 'fk_session')
