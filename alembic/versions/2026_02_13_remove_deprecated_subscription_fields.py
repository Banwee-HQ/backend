"""remove deprecated subscription fields

Revision ID: remove_deprecated_fields
Revises: update_subscription_fields
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_deprecated_fields'
down_revision = 'update_subscription_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Remove deprecated columns
    op.drop_column('subscriptions', 'price')
    op.drop_column('subscriptions', 'cost_breakdown')
    op.drop_column('subscriptions', 'subtotal')
    op.drop_column('subscriptions', 'shipping_cost')
    op.drop_column('subscriptions', 'tax_amount')
    op.drop_column('subscriptions', 'tax_rate')
    op.drop_column('subscriptions', 'discount_amount')
    op.drop_column('subscriptions', 'total')
    op.drop_column('subscriptions', 'variant_quantities')


def downgrade():
    # Add back deprecated columns (for rollback)
    op.add_column('subscriptions', sa.Column('price', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('cost_breakdown', sa.JSON(), nullable=True))
    op.add_column('subscriptions', sa.Column('subtotal', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('shipping_cost', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('tax_amount', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('tax_rate', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('discount_amount', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('total', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('subscriptions', sa.Column('variant_quantities', sa.JSON(), nullable=True))
