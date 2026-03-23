"""Add payment retry fields to subscriptions

Revision ID: 2026_02_13_retry
Revises: 2026_02_13_discount
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2026_02_13_retry'
down_revision = '2026_02_13_discount'
branch_labels = None
depends_on = None


def upgrade():
    # Add payment retry tracking fields
    op.add_column('subscriptions', sa.Column('payment_retry_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('subscriptions', sa.Column('last_payment_attempt', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('next_retry_date', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remove payment retry tracking fields
    op.drop_column('subscriptions', 'next_retry_date')
    op.drop_column('subscriptions', 'last_payment_attempt')
    op.drop_column('subscriptions', 'payment_retry_count')
