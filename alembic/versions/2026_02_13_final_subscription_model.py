"""final subscription model with historical and current pricing

Revision ID: final_subscription_model
Revises: remove_deprecated_fields
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'final_subscription_model'
down_revision = 'remove_deprecated_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add new fields for historical pricing
    op.add_column('subscriptions', sa.Column('variants', sa.JSON(), nullable=True))
    op.add_column('subscriptions', sa.Column('variant_prices_at_creation', sa.JSON(), nullable=True))
    op.add_column('subscriptions', sa.Column('shipping_amount_at_creation', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('tax_amount_at_creation', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('tax_rate_at_creation', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('total_charged_at_creation', sa.Float(), nullable=True))
    
    # Add discount fields
    op.add_column('subscriptions', sa.Column('discount_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_type', sa.String(50), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_value', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('discount_code', sa.String(100), nullable=True))
    
    # Add payment gateway fields
    op.add_column('subscriptions', sa.Column('payment_gateway', sa.String(50), nullable=True, server_default='stripe'))
    op.add_column('subscriptions', sa.Column('payment_reference', sa.String(255), nullable=True))
    
    # Migrate existing data
    # Convert variant_ids to variants format
    op.execute("""
        UPDATE subscriptions
        SET variants = (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'id', value::text,
                    'qty', COALESCE(
                        (subscription_metadata->'variant_quantities'->>value::text)::int,
                        1
                    )
                )
            )
            FROM jsonb_array_elements_text(variant_ids::jsonb) AS value
        )
        WHERE variant_ids IS NOT NULL
    """)


def downgrade():
    # Remove new columns
    op.drop_column('subscriptions', 'payment_reference')
    op.drop_column('subscriptions', 'payment_gateway')
    op.drop_column('subscriptions', 'discount_code')
    op.drop_column('subscriptions', 'discount_value')
    op.drop_column('subscriptions', 'discount_type')
    op.drop_column('subscriptions', 'discount_id')
    op.drop_column('subscriptions', 'total_charged_at_creation')
    op.drop_column('subscriptions', 'tax_rate_at_creation')
    op.drop_column('subscriptions', 'tax_amount_at_creation')
    op.drop_column('subscriptions', 'shipping_amount_at_creation')
    op.drop_column('subscriptions', 'variant_prices_at_creation')
    op.drop_column('subscriptions', 'variants')
