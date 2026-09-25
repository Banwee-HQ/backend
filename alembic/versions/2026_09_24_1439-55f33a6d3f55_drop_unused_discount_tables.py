"""drop unused discount tables

Promo codes live only in commerce.promocodes; these three tables were never written by the app.

Revision ID: 55f33a6d3f55
Revises: 55c927cf90e1
Create Date: 2026-09-24 14:39:17.404671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import core.db

# revision identifiers, used by Alembic.
revision: str = '55f33a6d3f55'
down_revision: Union[str, None] = '55c927cf90e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('subscription_discounts', schema='commerce')
    op.drop_table('product_removal_audit', schema='commerce')
    op.drop_table('discounts', schema='commerce')


def downgrade() -> None:
    op.create_table('discounts',
    sa.Column('id', core.db.GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('minimum_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('maximum_discount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('usage_limit', sa.Integer(), nullable=True),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    schema='commerce'
    )
    op.create_table('product_removal_audit',
    sa.Column('id', core.db.GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', core.db.GUID(), nullable=False),
    sa.Column('product_id', core.db.GUID(), nullable=False),
    sa.Column('removed_by', core.db.GUID(), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['removed_by'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_table('subscription_discounts',
    sa.Column('id', core.db.GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', core.db.GUID(), nullable=False),
    sa.Column('discount_id', core.db.GUID(), nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['discount_id'], ['commerce.discounts.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
