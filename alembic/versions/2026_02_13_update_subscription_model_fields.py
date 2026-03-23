"""update subscription model fields

Revision ID: update_subscription_fields
Revises: add_price_at_creation
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'update_subscription_fields'
down_revision = 'add_price_at_creation'
branch_labels = None
depends_on = None


def upgrade():
    # Add new fields
    op.add_column('subscriptions', sa.Column('delivery_type', sa.String(50), nullable=True, server_default='standard'))
    op.add_column('subscriptions', sa.Column('delivery_address_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('subscriptions', sa.Column('discount', sa.JSON(), nullable=True))
    op.add_column('subscriptions', sa.Column('subscription_metadata', sa.JSON(), nullable=True))
    op.add_column('subscriptions', sa.Column('last_payment_error', sa.Text(), nullable=True))
    
    # Add foreign key for delivery_address_id
    op.create_foreign_key(
        'fk_subscriptions_delivery_address_id',
        'subscriptions',
        'addresses',
        ['delivery_address_id'],
        ['id']
    )
    
    # Migrate existing variant_quantities to subscription_metadata
    op.execute("""
        UPDATE subscriptions
        SET subscription_metadata = jsonb_build_object('variant_quantities', variant_quantities)
        WHERE variant_quantities IS NOT NULL
    """)


def downgrade():
    # Remove foreign key
    op.drop_constraint('fk_subscriptions_delivery_address_id', 'subscriptions', type_='foreignkey')
    
    # Remove new columns
    op.drop_column('subscriptions', 'last_payment_error')
    op.drop_column('subscriptions', 'subscription_metadata')
    op.drop_column('subscriptions', 'discount')
    op.drop_column('subscriptions', 'delivery_address_id')
    op.drop_column('subscriptions', 'delivery_type')
