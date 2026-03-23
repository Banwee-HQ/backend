"""add price_at_creation to subscriptions

Revision ID: add_price_at_creation
Revises: 2026_02_07_2207
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_price_at_creation'
down_revision = 'd4e8f9a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    # Add price_at_creation column to subscriptions table
    op.add_column('subscriptions', sa.Column('price_at_creation', sa.Float(), nullable=True))


def downgrade():
    # Remove price_at_creation column from subscriptions table
    op.drop_column('subscriptions', 'price_at_creation')
