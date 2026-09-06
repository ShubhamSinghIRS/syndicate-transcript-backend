"""align transcripts table with schema.dbml

Revision ID: 3970e3b6a3d1
Revises: 8a88c8e366e2
Create Date: 2026-08-17 09:00:00.000000

Renames domain/geography/key_insight to their plural dbml names, drops
approved_at and created_at (published_at now covers both, with a default of
now()), adds currency and updated_at, and widens price to bigint. Existing
rows are preserved - this is a set of in-place alters, not a table rebuild.

Every step is guarded on the table's actual current state: 8a88c8e366e2
(the previous revision) rebuilds transcripts via `Base.metadata.create_all`
against the live models module, not a frozen snapshot - so on a database
migrated from scratch today, that step already creates the plural/renamed
columns this migration was written to produce, and every operation below
would otherwise fail against a column/index that no longer has its old name.
On a database that reached this revision back when the models still used
the old names, the guards are no-ops and the alters run as originally written.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3970e3b6a3d1'
down_revision: Union[str, None] = '8a88c8e366e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("transcripts")}
    indexes = {idx["name"] for idx in inspector.get_indexes("transcripts")}

    if "domain" in columns:
        op.alter_column('transcripts', 'domain', new_column_name='domains')
    if "geography" in columns:
        op.alter_column('transcripts', 'geography', new_column_name='geographies')
    if "key_insight" in columns:
        op.alter_column('transcripts', 'key_insight', new_column_name='key_insights')

    if "currency" not in columns:
        op.add_column('transcripts', sa.Column('currency', sa.String(), nullable=False, server_default='INR'))
    if "updated_at" not in columns:
        op.add_column('transcripts', sa.Column('updated_at', sa.DateTime(), nullable=True))

    op.alter_column('transcripts', 'price', type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False)
    op.alter_column(
        'transcripts', 'published_at', server_default=sa.text('now()'), existing_type=sa.DateTime(), existing_nullable=True
    )

    if "approved_at" in columns:
        op.drop_column('transcripts', 'approved_at')
    if "created_at" in columns:
        op.drop_column('transcripts', 'created_at')

    if "ix_transcripts_domain" in indexes:
        op.execute('ALTER INDEX ix_transcripts_domain RENAME TO ix_transcripts_domains')
    if "ix_transcripts_geography" in indexes:
        op.execute('ALTER INDEX ix_transcripts_geography RENAME TO ix_transcripts_geographies')


def downgrade() -> None:
    op.execute('ALTER INDEX ix_transcripts_domains RENAME TO ix_transcripts_domain')
    op.execute('ALTER INDEX ix_transcripts_geographies RENAME TO ix_transcripts_geography')

    op.add_column('transcripts', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('transcripts', sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True))

    op.alter_column('transcripts', 'published_at', server_default=None, existing_type=sa.DateTime(), existing_nullable=True)
    op.alter_column('transcripts', 'price', type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False)

    op.drop_column('transcripts', 'updated_at')
    op.drop_column('transcripts', 'currency')

    op.alter_column('transcripts', 'key_insights', new_column_name='key_insight')
    op.alter_column('transcripts', 'geographies', new_column_name='geography')
    op.alter_column('transcripts', 'domains', new_column_name='domain')
