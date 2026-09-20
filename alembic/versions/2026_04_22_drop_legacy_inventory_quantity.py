"""Drop the legacy inventory.quantity column - quantity_available is the real field
and has been the only one read anywhere for years; quantity was just kept in sync.

Revision ID: 2026_04_22_dropqty
Revises: 2026_04_22_carttrig
Create Date: 2026-04-22 01:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '2026_04_22_dropqty'
down_revision: Union[str, None] = '2026_04_22_carttrig'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('inventory', 'quantity', schema='catalog')


def downgrade() -> None:
    op.add_column('inventory', sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'), schema='catalog')
    op.execute("UPDATE catalog.inventory SET quantity = quantity_available")
