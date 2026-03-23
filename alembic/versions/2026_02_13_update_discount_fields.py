"""Update discount fields in subscriptions

Revision ID: 2026_02_13_discount
Revises: 2026_02_13_final_subscription_model
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2026_02_13_discount'
down_revision = 'final_subscription_model'
branch_labels = None
depends_on = None


def upgrade():
    # Remove old discount JSON column
    op.drop_column('subscriptions', 'discount')
    
    # Add new discount fields
    op.add_column('subscriptions', sa.Column('discount_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_type', sa.String(length=20), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_value', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_code', sa.String(length=50), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key('fk_subscriptions_discount_id', 'subscriptions', 'promocodes', ['discount_id'], ['id'])


def downgrade():
    # Remove foreign key constraint
    op.drop_constraint('fk_subscriptions_discount_id', 'subscriptions', type_='foreignkey')
    
    # Remove new discount fields
    op.drop_column('subscriptions', 'discount_code')
    op.drop_column('subscriptions', 'discount_value')
    op.drop_column('subscriptions', 'discount_type')
    op.drop_column('subscriptions', 'discount_id')
    
    # Add back old discount JSON column
    op.add_column('subscriptions', sa.Column('discount', postgresql.JSON(astext_type=sa.Text()), nullable=True))
