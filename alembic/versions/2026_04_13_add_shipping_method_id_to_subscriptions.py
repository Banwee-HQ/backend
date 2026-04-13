"""Add shipping_method_id to subscriptions

Revision ID: add_shipping_method_id_sub
Revises: change_age_to_date_of_birth
Create Date: 2026-04-13 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_shipping_method_id_sub'
down_revision: Union[str, None] = 'create_sub_assoc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'subscriptions',
        sa.Column('shipping_method_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        schema='commerce'
    )
    op.create_foreign_key(
        'fk_subscriptions_shipping_method_id',
        'subscriptions', 'shipping_methods',
        ['shipping_method_id'], ['id'],
        source_schema='commerce', referent_schema='commerce'
    )
    op.create_index(
        'idx_subscriptions_shipping_method_id',
        'subscriptions', ['shipping_method_id'],
        schema='commerce'
    )


def downgrade() -> None:
    op.drop_index('idx_subscriptions_shipping_method_id', table_name='subscriptions', schema='commerce')
    op.drop_constraint('fk_subscriptions_shipping_method_id', 'subscriptions', schema='commerce', type_='foreignkey')
    op.drop_column('subscriptions', 'shipping_method_id', schema='commerce')
