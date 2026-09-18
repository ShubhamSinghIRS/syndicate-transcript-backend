"""flip order_items.access_permission meaning to true = has access

Revision ID: c4f9a2e6b8d1
Revises: b3e8f1a4c7d2
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4f9a2e6b8d1'
down_revision: Union[str, None] = 'b3e8f1a4c7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Was true = access revoked (renamed from "refunded"), which read backwards
    # against the column name. Flip so true = access granted, matching the name.
    op.execute('UPDATE order_items SET access_permission = NOT access_permission')
    op.alter_column('order_items', 'access_permission', server_default=sa.text('true'))


def downgrade() -> None:
    op.alter_column('order_items', 'access_permission', server_default=sa.text('false'))
    op.execute('UPDATE order_items SET access_permission = NOT access_permission')
