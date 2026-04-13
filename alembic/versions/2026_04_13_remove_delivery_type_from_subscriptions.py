"""Remove delivery_type from subscriptions

Revision ID: remove_delivery_type_sub
Revises: add_shipping_method_id_sub
Create Date: 2026-04-13 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'remove_delivery_type_sub'
down_revision: Union[str, None] = 'add_shipping_method_id_sub'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('subscriptions', 'delivery_type', schema='commerce')


def downgrade() -> None:
    op.add_column(
        'subscriptions',
        sa.Column('delivery_type', sa.String(length=50), nullable=True),
        schema='commerce'
    )
