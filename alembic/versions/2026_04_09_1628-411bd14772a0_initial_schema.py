"""initial_schema

Revision ID: 411bd14772a0
Revises: 
Create Date: 2026-04-09 16:28:58.909120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import core.db
from core.db import GUID
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '411bd14772a0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create schemas first
    op.execute('CREATE SCHEMA IF NOT EXISTS accounts')
    op.execute('CREATE SCHEMA IF NOT EXISTS catalog')
    op.execute('CREATE SCHEMA IF NOT EXISTS commerce')
    op.execute('CREATE SCHEMA IF NOT EXISTS admin')
    op.execute('CREATE SCHEMA IF NOT EXISTS system')
    # Create accounts.users and accounts.addresses first (other tables FK to them)
    op.create_table('users',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('firstname', sa.String(length=255), nullable=False),
    sa.Column('lastname', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('account_status', sa.String(length=50), nullable=False),
    sa.Column('verification_status', sa.String(length=50), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('phone_verified', sa.Boolean(), nullable=False),
    sa.Column('country', sa.String(length=100), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('timezone', sa.String(length=100), nullable=True),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('age', sa.Integer(), nullable=True),
    sa.Column('gender', sa.String(length=20), nullable=True),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
    sa.Column('preferences', sa.JSON(), nullable=True),
    sa.Column('verification_token', sa.String(length=255), nullable=True),
    sa.Column('token_expiration', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reset_token', sa.String(length=255), nullable=True),
    sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('stripe_customer_id'),
    schema='accounts'
    )
    op.create_index('idx_users_email_account_status', 'users', ['email', 'account_status'], schema='accounts')
    op.create_index('idx_users_role_verification_status', 'users', ['role', 'verification_status'], schema='accounts')
    op.create_index('idx_users_country_language', 'users', ['country', 'language'], schema='accounts')
    op.create_index('idx_users_last_login', 'users', ['last_login'], schema='accounts')
    op.create_index('idx_users_stripe_customer', 'users', ['stripe_customer_id'], schema='accounts')
    op.create_index('idx_users_age', 'users', ['age'], schema='accounts')
    op.create_index('idx_users_gender', 'users', ['gender'], schema='accounts')
    op.create_table('addresses',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('street', sa.String(length=255), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=100), nullable=False),
    sa.Column('country', sa.String(length=100), nullable=False),
    sa.Column('post_code', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='accounts'
    )
    op.create_index('idx_addresses_user_id', 'addresses', ['user_id'], schema='accounts')
    op.create_index('idx_addresses_city', 'addresses', ['city'], schema='accounts')
    op.create_index('idx_addresses_state', 'addresses', ['state'], schema='accounts')
    op.create_index('idx_addresses_country', 'addresses', ['country'], schema='accounts')
    op.create_index('idx_addresses_post_code', 'addresses', ['post_code'], schema='accounts')
    op.create_index('idx_addresses_kind', 'addresses', ['kind'], schema='accounts')
    op.create_index('idx_addresses_default', 'addresses', ['is_default'], schema='accounts')
    op.create_index('idx_addresses_user_default', 'addresses', ['user_id', 'is_default'], schema='accounts')
    op.create_index('idx_addresses_user_kind', 'addresses', ['user_id', 'kind'], schema='accounts')
    op.create_index('idx_addresses_country_city', 'addresses', ['country', 'city'], schema='accounts')
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('payment_analytics',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('total_payments', sa.Integer(), nullable=False),
    sa.Column('successful_payments', sa.Integer(), nullable=False),
    sa.Column('failed_payments', sa.Integer(), nullable=False),
    sa.Column('pending_payments', sa.Integer(), nullable=False),
    sa.Column('success_rate', sa.Float(), nullable=False),
    sa.Column('total_volume', sa.Float(), nullable=False),
    sa.Column('successful_volume', sa.Float(), nullable=False),
    sa.Column('average_payment_amount', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('breakdown_by_method', sa.JSON(), nullable=True),
    sa.Column('breakdown_by_country', sa.JSON(), nullable=True),
    sa.Column('breakdown_by_currency', sa.JSON(), nullable=True),
    sa.Column('failure_breakdown', sa.JSON(), nullable=True),
    sa.Column('processing_metrics', sa.JSON(), nullable=True),
    sa.Column('additional_metrics', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_table('pricing_configs',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_percentage', sa.Float(), nullable=False),
    sa.Column('delivery_costs', sa.JSON(), nullable=False),
    sa.Column('tax_rates', sa.JSON(), nullable=False),
    sa.Column('currency_settings', sa.JSON(), nullable=False),
    sa.Column('updated_by', GUID(), nullable=False),
    sa.Column('config_version', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.String(length=20), nullable=False),
    sa.Column('change_reason', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_index('idx_pricing_configs_active', 'pricing_configs', ['is_active'], unique=False, schema='admin')
    op.create_index('idx_pricing_configs_created_at', 'pricing_configs', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_pricing_configs_updated_by', 'pricing_configs', ['updated_by'], unique=False, schema='admin')
    op.create_index('idx_pricing_configs_version', 'pricing_configs', ['config_version'], unique=False, schema='admin')
    op.create_table('subscription_analytics',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('total_active_subscriptions', sa.Integer(), nullable=False),
    sa.Column('new_subscriptions', sa.Integer(), nullable=False),
    sa.Column('canceled_subscriptions', sa.Integer(), nullable=False),
    sa.Column('paused_subscriptions', sa.Integer(), nullable=False),
    sa.Column('resumed_subscriptions', sa.Integer(), nullable=False),
    sa.Column('total_revenue', sa.Float(), nullable=False),
    sa.Column('average_subscription_value', sa.Float(), nullable=False),
    sa.Column('monthly_recurring_revenue', sa.Float(), nullable=False),
    sa.Column('churn_rate', sa.Float(), nullable=False),
    sa.Column('conversion_rate', sa.Float(), nullable=False),
    sa.Column('retention_rate', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('plan_breakdown', sa.JSON(), nullable=True),
    sa.Column('delivery_breakdown', sa.JSON(), nullable=True),
    sa.Column('geographic_breakdown', sa.JSON(), nullable=True),
    sa.Column('additional_metrics', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_table('subscription_cost_history',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', GUID(), nullable=False),
    sa.Column('old_cost_breakdown', sa.JSON(), nullable=True),
    sa.Column('new_cost_breakdown', sa.JSON(), nullable=False),
    sa.Column('change_reason', sa.String(length=100), nullable=False),
    sa.Column('effective_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('changed_by', GUID(), nullable=True),
    sa.Column('pricing_metadata', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_index('idx_subscription_cost_history_change_reason', 'subscription_cost_history', ['change_reason'], unique=False, schema='admin')
    op.create_index('idx_subscription_cost_history_changed_by', 'subscription_cost_history', ['changed_by'], unique=False, schema='admin')
    op.create_index('idx_subscription_cost_history_created_at', 'subscription_cost_history', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_subscription_cost_history_effective_date', 'subscription_cost_history', ['effective_date'], unique=False, schema='admin')
    op.create_index('idx_subscription_cost_history_sub_effective', 'subscription_cost_history', ['subscription_id', 'effective_date'], unique=False, schema='admin')
    op.create_index('idx_subscription_cost_history_subscription_id', 'subscription_cost_history', ['subscription_id'], unique=False, schema='admin')
    op.create_table('products',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('short_description', sa.String(length=500), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('product_status', sa.Enum('ACTIVE', 'INACTIVE', 'DRAFT', 'DISCONTINUED', name='productstatus'), nullable=False),
    sa.Column('rating_average', sa.Float(), nullable=False),
    sa.Column('rating_count', sa.Integer(), nullable=False),
    sa.Column('review_count', sa.Integer(), nullable=False),
    sa.Column('is_featured', sa.Boolean(), nullable=False),
    sa.Column('is_bestseller', sa.Boolean(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('product_metadata', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug'),
    schema='catalog'
    )
    op.create_index('idx_products_category_status', 'products', ['category', 'product_status'], unique=False, schema='catalog')
    op.create_index('idx_products_published', 'products', ['published_at', 'product_status'], unique=False, schema='catalog')
    op.create_index('idx_products_slug', 'products', ['slug'], unique=False, schema='catalog')
    op.create_table('warehouse_locations',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_warehouse_locations_name', 'warehouse_locations', ['name'], unique=False, schema='catalog')
    op.create_table('discounts',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('minimum_amount', sa.Float(), nullable=True),
    sa.Column('maximum_discount', sa.Float(), nullable=True),
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
    op.create_index('idx_discounts_active', 'discounts', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_discounts_active_valid', 'discounts', ['is_active', 'valid_from', 'valid_until'], unique=False, schema='commerce')
    op.create_index('idx_discounts_code', 'discounts', ['code'], unique=False, schema='commerce')
    op.create_index('idx_discounts_code_active', 'discounts', ['code', 'is_active'], unique=False, schema='commerce')
    op.create_index('idx_discounts_type', 'discounts', ['type'], unique=False, schema='commerce')
    op.create_index('idx_discounts_usage_limit', 'discounts', ['usage_limit'], unique=False, schema='commerce')
    op.create_index('idx_discounts_used_count', 'discounts', ['used_count'], unique=False, schema='commerce')
    op.create_index('idx_discounts_valid_from', 'discounts', ['valid_from'], unique=False, schema='commerce')
    op.create_index('idx_discounts_valid_until', 'discounts', ['valid_until'], unique=False, schema='commerce')
    op.create_table('promocodes',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('discount_type', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('minimum_order_amount', sa.Float(), nullable=True),
    sa.Column('maximum_discount_amount', sa.Float(), nullable=True),
    sa.Column('usage_limit', sa.Integer(), nullable=True),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    schema='commerce'
    )
    op.create_index('idx_promocodes_active', 'promocodes', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_active_valid', 'promocodes', ['is_active', 'valid_from', 'valid_until'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_code', 'promocodes', ['code'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_discount_type', 'promocodes', ['discount_type'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_usage_limit', 'promocodes', ['usage_limit'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_used_count', 'promocodes', ['used_count'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_valid_from', 'promocodes', ['valid_from'], unique=False, schema='commerce')
    op.create_index('idx_promocodes_valid_until', 'promocodes', ['valid_until'], unique=False, schema='commerce')
    op.create_table('shipping_methods',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('estimated_days', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('carrier', sa.String(length=100), nullable=True),
    sa.Column('tracking_url_template', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_shipping_methods_active', 'shipping_methods', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_methods_active_price', 'shipping_methods', ['is_active', 'price'], unique=False, schema='commerce')
    op.create_index('idx_shipping_methods_estimated_days', 'shipping_methods', ['estimated_days'], unique=False, schema='commerce')
    op.create_index('idx_shipping_methods_name', 'shipping_methods', ['name'], unique=False, schema='commerce')
    op.create_index('idx_shipping_methods_price', 'shipping_methods', ['price'], unique=False, schema='commerce')
    op.create_table('shipping_providers',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('carrier', postgresql.ENUM('UPS', 'CANADA_EXPRESS', 'ROYAL_MAIL', 'FEDEX', 'DHL', 'USPS', 'CANADA_POST', 'PUROLATOR', 'TNT', 'ARAMEX', 'LASERSHIP', 'ONTRAC', 'HERMES', 'EVRI', 'DPD', 'DPD_LOCAL', 'GLS', 'POSTNL', 'BPOST', 'SWISS_POST', 'AUSTRALIA_POST', 'NZ_POST', 'JAPAN_POST', 'KOREA_POST', 'CHINA_POST', 'SF_EXPRESS', 'YANWEN', 'CAINIAO', 'LAPOSTE', 'COLISSIMO', 'CORREOS', 'POSTE_ITALIANE', 'POSTNORD', 'BRING', 'BLUE_DART', 'DELHIVERY', 'DTDC', 'XPRESSBEES', 'OTHER', name='shipping_carrier'), nullable=False),
    sa.Column('api_key', sa.String(length=255), nullable=True),
    sa.Column('api_secret', sa.String(length=255), nullable=True),
    sa.Column('api_url', sa.String(length=255), nullable=False),
    sa.Column('tracking_url_template', sa.String(length=500), nullable=False),
    sa.Column('webhook_url', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('configuration', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('rate_limits', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_shipping_providers_active', 'shipping_providers', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_providers_carrier', 'shipping_providers', ['carrier'], unique=False, schema='commerce')
    op.create_table('shipping_rules',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('location_code', sa.String(length=10), nullable=False),
    sa.Column('weight_min', sa.Float(), nullable=False),
    sa.Column('weight_max', sa.Float(), nullable=False),
    sa.Column('base_rate', sa.Float(), nullable=False),
    sa.Column('minimum_shipping', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_shipping_rules_active', 'shipping_rules', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_rules_base_rate', 'shipping_rules', ['base_rate'], unique=False, schema='commerce')
    op.create_index('idx_shipping_rules_location_active', 'shipping_rules', ['location_code', 'is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_rules_location_code', 'shipping_rules', ['location_code'], unique=False, schema='commerce')
    op.create_index('idx_shipping_rules_weight_active', 'shipping_rules', ['weight_min', 'weight_max', 'is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_rules_weight_range', 'shipping_rules', ['weight_min', 'weight_max'], unique=False, schema='commerce')
    op.create_table('tax_rates',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('country_name', sa.String(length=100), nullable=False),
    sa.Column('province_code', sa.String(length=10), nullable=True),
    sa.Column('province_name', sa.String(length=100), nullable=True),
    sa.Column('tax_rate', sa.Float(), nullable=False),
    sa.Column('tax_name', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('effective_date', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_tax_country_province', 'tax_rates', ['country_code', 'province_code'], unique=False, schema='commerce')
    op.create_table('tax_rules',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('location_code', sa.String(length=10), nullable=False),
    sa.Column('tax_rate', sa.Float(), nullable=False),
    sa.Column('minimum_tax', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_tax_rules_active', 'tax_rules', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_tax_rules_location_active', 'tax_rules', ['location_code', 'is_active'], unique=False, schema='commerce')
    op.create_index('idx_tax_rules_location_code', 'tax_rules', ['location_code'], unique=False, schema='commerce')
    op.create_index('idx_tax_rules_tax_rate', 'tax_rules', ['tax_rate'], unique=False, schema='commerce')
    op.create_table('contact_messages',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', postgresql.ENUM('new', 'in_progress', 'resolved', 'closed', name='messagestatus'), nullable=False),
    sa.Column('priority', postgresql.ENUM('low', 'medium', 'high', 'urgent', name='messagepriority'), nullable=False),
    sa.Column('admin_notes', sa.Text(), nullable=True),
    sa.Column('assigned_to', GUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='system'
    )
    op.create_index('idx_contact_messages_assigned_to', 'contact_messages', ['assigned_to'], unique=False, schema='system')
    op.create_index('idx_contact_messages_created_at', 'contact_messages', ['created_at'], unique=False, schema='system')
    op.create_index('idx_contact_messages_email', 'contact_messages', ['email'], unique=False, schema='system')
    op.create_index('idx_contact_messages_priority', 'contact_messages', ['priority'], unique=False, schema='system')
    op.create_index('idx_contact_messages_resolved_at', 'contact_messages', ['resolved_at'], unique=False, schema='system')
    op.create_index('idx_contact_messages_status', 'contact_messages', ['status'], unique=False, schema='system')
    op.create_index('idx_contact_messages_status_created', 'contact_messages', ['status', 'created_at'], unique=False, schema='system')
    op.create_index('idx_contact_messages_status_priority', 'contact_messages', ['status', 'priority'], unique=False, schema='system')
    op.create_table('customer_lifecycle_metrics',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('first_purchase_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('time_to_first_purchase_hours', sa.Float(), nullable=True),
    sa.Column('total_orders', sa.Integer(), nullable=False),
    sa.Column('total_revenue', sa.Float(), nullable=False),
    sa.Column('average_order_value', sa.Float(), nullable=False),
    sa.Column('last_purchase_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('days_since_last_purchase', sa.Integer(), nullable=True),
    sa.Column('average_days_between_orders', sa.Float(), nullable=True),
    sa.Column('total_refunds', sa.Integer(), nullable=False),
    sa.Column('total_refund_amount', sa.Float(), nullable=False),
    sa.Column('refund_rate', sa.Float(), nullable=False),
    sa.Column('customer_segment', sa.String(length=50), nullable=True),
    sa.Column('lifetime_value', sa.Float(), nullable=False),
    sa.Column('predicted_ltv', sa.Float(), nullable=True),
    sa.Column('total_sessions', sa.Integer(), nullable=False),
    sa.Column('total_page_views', sa.Integer(), nullable=False),
    sa.Column('average_session_duration', sa.Float(), nullable=False),
    sa.Column('metrics_updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id'),
    schema='admin'
    )
    op.create_index('idx_customer_lifecycle_created_at', 'customer_lifecycle_metrics', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_customer_lifecycle_segment', 'customer_lifecycle_metrics', ['customer_segment'], unique=False, schema='admin')
    op.create_index('idx_customer_lifecycle_user_id', 'customer_lifecycle_metrics', ['user_id'], unique=False, schema='admin')
    op.create_table('user_sessions',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('session_id', sa.String(length=255), nullable=False),
    sa.Column('user_id', GUID(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('browser', sa.String(length=100), nullable=True),
    sa.Column('os', sa.String(length=100), nullable=True),
    sa.Column('traffic_source', sa.Enum('DIRECT', 'ORGANIC_SEARCH', 'PAID_SEARCH', 'SOCIAL', 'EMAIL', 'REFERRAL', 'AFFILIATE', 'UNKNOWN', name='trafficsource'), nullable=False),
    sa.Column('referrer_url', sa.Text(), nullable=True),
    sa.Column('utm_source', sa.String(length=255), nullable=True),
    sa.Column('utm_medium', sa.String(length=255), nullable=True),
    sa.Column('utm_campaign', sa.String(length=255), nullable=True),
    sa.Column('utm_content', sa.String(length=255), nullable=True),
    sa.Column('utm_term', sa.String(length=255), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('page_views', sa.Integer(), nullable=False),
    sa.Column('events_count', sa.Integer(), nullable=False),
    sa.Column('converted', sa.Boolean(), nullable=False),
    sa.Column('conversion_value', sa.Float(), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('region', sa.String(length=100), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id'),
    schema='admin'
    )
    op.create_index('idx_user_sessions_converted', 'user_sessions', ['converted'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_created_at', 'user_sessions', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_ended_at', 'user_sessions', ['ended_at'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_session_id', 'user_sessions', ['session_id'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_source_created', 'user_sessions', ['traffic_source', 'created_at'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_started_at', 'user_sessions', ['started_at'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_traffic_source', 'user_sessions', ['traffic_source'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_user_created', 'user_sessions', ['user_id', 'created_at'], unique=False, schema='admin')
    op.create_index('idx_user_sessions_user_id', 'user_sessions', ['user_id'], unique=False, schema='admin')
    op.create_table('product_variants',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('sku', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('base_price', sa.Float(), nullable=False),
    sa.Column('sale_price', sa.Float(), nullable=True),
    sa.Column('attributes', sa.JSON(), nullable=True),
    sa.Column('specifications', sa.JSON(), nullable=True),
    sa.Column('dietary_tags', sa.JSON(), nullable=False),
    sa.Column('tags', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('availability_status', sa.Enum('AVAILABLE', 'LIMITED', 'OUT_OF_STOCK', name='availabilitystatus'), nullable=False),
    sa.Column('view_count', sa.Integer(), nullable=False),
    sa.Column('purchase_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sku'),
    schema='catalog'
    )
    op.create_index('idx_variants_active', 'product_variants', ['is_active'], unique=False, schema='catalog')
    op.create_index('idx_variants_availability', 'product_variants', ['availability_status'], unique=False, schema='catalog')
    op.create_index('idx_variants_price', 'product_variants', ['base_price', 'sale_price'], unique=False, schema='catalog')
    op.create_index('idx_variants_product_id', 'product_variants', ['product_id'], unique=False, schema='catalog')
    op.create_index('idx_variants_sku', 'product_variants', ['sku'], unique=False, schema='catalog')
    op.create_table('reviews',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('is_verified_purchase', sa.Boolean(), nullable=False),
    sa.Column('is_approved', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_reviews_approved', 'reviews', ['is_approved'], unique=False, schema='catalog')
    op.create_index('idx_reviews_created_at', 'reviews', ['created_at'], unique=False, schema='catalog')
    op.create_index('idx_reviews_product_approved', 'reviews', ['product_id', 'is_approved'], unique=False, schema='catalog')
    op.create_index('idx_reviews_product_id', 'reviews', ['product_id'], unique=False, schema='catalog')
    op.create_index('idx_reviews_product_rating', 'reviews', ['product_id', 'rating'], unique=False, schema='catalog')
    op.create_index('idx_reviews_rating', 'reviews', ['rating'], unique=False, schema='catalog')
    op.create_index('idx_reviews_user_approved', 'reviews', ['user_id', 'is_approved'], unique=False, schema='catalog')
    op.create_index('idx_reviews_user_id', 'reviews', ['user_id'], unique=False, schema='catalog')
    op.create_index('idx_reviews_verified', 'reviews', ['is_verified_purchase'], unique=False, schema='catalog')
    op.create_table('wishlists',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('name', sa.String(length=225), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_wishlists_default', 'wishlists', ['is_default'], unique=False, schema='catalog')
    op.create_index('idx_wishlists_name', 'wishlists', ['name'], unique=False, schema='catalog')
    op.create_index('idx_wishlists_public', 'wishlists', ['is_public'], unique=False, schema='catalog')
    op.create_index('idx_wishlists_user_default', 'wishlists', ['user_id', 'is_default'], unique=False, schema='catalog')
    op.create_index('idx_wishlists_user_id', 'wishlists', ['user_id'], unique=False, schema='catalog')
    op.create_table('carts',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_carts_user_id', 'carts', ['user_id'], unique=True, schema='commerce')
    op.create_table('payment_methods',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('type', postgresql.ENUM('CARD', 'BANK_ACCOUNT', 'MOBILE_MONEY', 'OTHER', name='payment_type'), nullable=False),
    sa.Column('provider', postgresql.ENUM('STRIPE', 'PAYPAL', 'MOMO', 'GOOGLE_PAY', 'APPLE_PAY', 'BANK_TRANSFER', 'UNKNOWN', name='payment_provider'), nullable=False),
    sa.Column('last_four', sa.String(length=4), nullable=True),
    sa.Column('expiry_month', sa.Integer(), nullable=True),
    sa.Column('expiry_year', sa.Integer(), nullable=True),
    sa.Column('brand', postgresql.ENUM('VISA', 'VERVE', 'MASTERCARD', 'AMEX', 'DISCOVER', 'JCB', 'DINERS_CLUB', 'UNIONPAY', 'UNKNOWN', 'OTHER', name='card_brand'), nullable=True),
    sa.Column('stripe_payment_method_id', sa.String(length=255), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('payment_method_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stripe_payment_method_id'),
    schema='commerce'
    )
    op.create_index('idx_payment_methods_active', 'payment_methods', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_default', 'payment_methods', ['is_default'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_provider', 'payment_methods', ['provider'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_stripe_id', 'payment_methods', ['stripe_payment_method_id'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_type', 'payment_methods', ['type'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_user_active', 'payment_methods', ['user_id', 'is_active'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_user_default', 'payment_methods', ['user_id', 'is_default'], unique=False, schema='commerce')
    op.create_index('idx_payment_methods_user_id', 'payment_methods', ['user_id'], unique=False, schema='commerce')
    op.create_table('shipping_webhooks',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('provider_id', GUID(), nullable=False),
    sa.Column('webhook_url', sa.String(length=500), nullable=False),
    sa.Column('webhook_secret', sa.String(length=255), nullable=True),
    sa.Column('event_types', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('last_triggered', sa.DateTime(timezone=True), nullable=True),
    sa.Column('success_count', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['provider_id'], ['commerce.shipping_providers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_shipping_webhooks_active', 'shipping_webhooks', ['is_active'], unique=False, schema='commerce')
    op.create_index('idx_shipping_webhooks_provider', 'shipping_webhooks', ['provider_id'], unique=False, schema='commerce')
    op.create_table('conversion_funnels',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('session_id', sa.String(length=255), nullable=False),
    sa.Column('user_id', GUID(), nullable=True),
    sa.Column('current_step', sa.Integer(), nullable=False),
    sa.Column('max_step_reached', sa.Integer(), nullable=False),
    sa.Column('landing_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('product_view_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cart_add_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('checkout_start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purchase_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('abandoned_at_step', sa.Integer(), nullable=True),
    sa.Column('abandoned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('cart_value', sa.Float(), nullable=True),
    sa.Column('purchase_value', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['admin.user_sessions.session_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_index('idx_conversion_funnels_created_at', 'conversion_funnels', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_conversion_funnels_session_id', 'conversion_funnels', ['session_id'], unique=False, schema='admin')
    op.create_index('idx_conversion_funnels_step', 'conversion_funnels', ['current_step'], unique=False, schema='admin')
    op.create_index('idx_conversion_funnels_user_id', 'conversion_funnels', ['user_id'], unique=False, schema='admin')
    op.create_table('inventory',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('location_id', GUID(), nullable=False),
    sa.Column('quantity_available', sa.Integer(), nullable=False),
    sa.Column('low_stock_threshold', sa.Integer(), nullable=False),
    sa.Column('reorder_point', sa.Integer(), nullable=False),
    sa.Column('inventory_status', sa.String(length=50), nullable=False),
    sa.Column('last_restocked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sold_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['catalog.warehouse_locations.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('variant_id'),
    schema='catalog'
    )
    op.create_index('idx_inventory_location_id', 'inventory', ['location_id'], unique=False, schema='catalog')
    op.create_index('idx_inventory_location_quantity', 'inventory', ['location_id', 'quantity_available'], unique=False, schema='catalog')
    op.create_index('idx_inventory_low_stock', 'inventory', ['low_stock_threshold'], unique=False, schema='catalog')
    op.create_index('idx_inventory_quantity_available', 'inventory', ['quantity_available'], unique=False, schema='catalog')
    op.create_index('idx_inventory_status', 'inventory', ['inventory_status'], unique=False, schema='catalog')
    op.create_index('idx_inventory_variant_id', 'inventory', ['variant_id'], unique=False, schema='catalog')
    op.create_index('idx_inventory_variant_status', 'inventory', ['variant_id', 'inventory_status'], unique=False, schema='catalog')
    op.create_table('product_images',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('alt_text', sa.String(length=255), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('format', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_images_primary', 'product_images', ['is_primary'], unique=False, schema='catalog')
    op.create_index('idx_images_variant_id', 'product_images', ['variant_id'], unique=False, schema='catalog')
    op.create_table('variant_analytics',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_type', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='analyticsperiodtype'), nullable=False),
    sa.Column('total_subscriptions', sa.Integer(), nullable=False),
    sa.Column('new_subscriptions', sa.Integer(), nullable=False),
    sa.Column('canceled_subscriptions', sa.Integer(), nullable=False),
    sa.Column('active_subscriptions', sa.Integer(), nullable=False),
    sa.Column('total_revenue', sa.Float(), nullable=False),
    sa.Column('average_subscription_duration_days', sa.Integer(), nullable=False),
    sa.Column('churn_rate', sa.Float(), nullable=False),
    sa.Column('popularity_rank', sa.Integer(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('additional_metrics', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_variant_analytics_currency', 'variant_analytics', ['currency'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_date', 'variant_analytics', ['date'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_date_period', 'variant_analytics', ['date', 'period_type'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_period_type', 'variant_analytics', ['period_type'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_popularity_rank', 'variant_analytics', ['popularity_rank'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_total_revenue', 'variant_analytics', ['total_revenue'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_variant_date', 'variant_analytics', ['variant_id', 'date'], unique=False, schema='catalog')
    op.create_index('idx_variant_analytics_variant_id', 'variant_analytics', ['variant_id'], unique=False, schema='catalog')
    op.create_table('variant_price_history',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('old_price', sa.Float(), nullable=True),
    sa.Column('new_price', sa.Float(), nullable=False),
    sa.Column('old_sale_price', sa.Float(), nullable=True),
    sa.Column('new_sale_price', sa.Float(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('change_reason', sa.String(length=100), nullable=True),
    sa.Column('changed_by_user_id', GUID(), nullable=True),
    sa.Column('effective_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('affected_subscriptions_count', sa.Integer(), nullable=False),
    sa.Column('price_metadata', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_variant_price_history_change_reason', 'variant_price_history', ['change_reason'], unique=False, schema='catalog')
    op.create_index('idx_variant_price_history_changed_by', 'variant_price_history', ['changed_by_user_id'], unique=False, schema='catalog')
    op.create_index('idx_variant_price_history_currency', 'variant_price_history', ['currency'], unique=False, schema='catalog')
    op.create_index('idx_variant_price_history_effective_date', 'variant_price_history', ['effective_date'], unique=False, schema='catalog')
    op.create_index('idx_variant_price_history_variant_effective', 'variant_price_history', ['variant_id', 'effective_date'], unique=False, schema='catalog')
    op.create_index('idx_variant_price_history_variant_id', 'variant_price_history', ['variant_id'], unique=False, schema='catalog')
    op.create_table('variant_substitutions',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('original_variant_id', GUID(), nullable=False),
    sa.Column('substitute_variant_id', GUID(), nullable=False),
    sa.Column('similarity_score', sa.Float(), nullable=False),
    sa.Column('substitution_reason', sa.String(length=100), nullable=True),
    sa.Column('times_suggested', sa.Integer(), nullable=False),
    sa.Column('times_accepted', sa.Integer(), nullable=False),
    sa.Column('acceptance_rate', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('substitution_metadata', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['original_variant_id'], ['catalog.product_variants.id'], ),
    sa.ForeignKeyConstraint(['substitute_variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_variant_substitutions_acceptance_rate', 'variant_substitutions', ['acceptance_rate'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_active', 'variant_substitutions', ['is_active'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_original_active', 'variant_substitutions', ['original_variant_id', 'is_active'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_original_id', 'variant_substitutions', ['original_variant_id'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_reason', 'variant_substitutions', ['substitution_reason'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_similarity_score', 'variant_substitutions', ['similarity_score'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_substitute_active', 'variant_substitutions', ['substitute_variant_id', 'is_active'], unique=False, schema='catalog')
    op.create_index('idx_variant_substitutions_substitute_id', 'variant_substitutions', ['substitute_variant_id'], unique=False, schema='catalog')
    op.create_table('wishlist_items',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('wishlist_id', GUID(), nullable=False),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('variant_id', GUID(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.ForeignKeyConstraint(['wishlist_id'], ['catalog.wishlists.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_wishlist_items_created_at', 'wishlist_items', ['created_at'], unique=False, schema='catalog')
    op.create_index('idx_wishlist_items_product_id', 'wishlist_items', ['product_id'], unique=False, schema='catalog')
    op.create_index('idx_wishlist_items_variant_id', 'wishlist_items', ['variant_id'], unique=False, schema='catalog')
    op.create_index('idx_wishlist_items_wishlist_id', 'wishlist_items', ['wishlist_id'], unique=False, schema='catalog')
    op.create_index('idx_wishlist_items_wishlist_product', 'wishlist_items', ['wishlist_id', 'product_id'], unique=False, schema='catalog')
    op.create_table('cart_items',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cart_id', GUID(), nullable=False),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('price_per_unit', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['cart_id'], ['commerce.carts.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_cart_items_cart_id', 'cart_items', ['cart_id'], unique=False, schema='commerce')
    op.create_index('idx_cart_items_cart_product_variant', 'cart_items', ['cart_id', 'product_id', 'variant_id'], unique=True, schema='commerce')
    op.create_index('idx_cart_items_product_id', 'cart_items', ['product_id'], unique=False, schema='commerce')
    op.create_index('idx_cart_items_variant_id', 'cart_items', ['variant_id'], unique=False, schema='commerce')
    op.create_table('subscriptions',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('billing_cycle', sa.String(length=20), nullable=False),
    sa.Column('auto_renew', sa.Boolean(), nullable=False),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_billing_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pause_reason', sa.Text(), nullable=True),
    sa.Column('last_payment_error', sa.Text(), nullable=True),
    sa.Column('payment_retry_count', sa.Integer(), nullable=False),
    sa.Column('last_payment_attempt', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_retry_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('payment_gateway', sa.String(length=50), nullable=True),
    sa.Column('payment_reference', sa.String(length=255), nullable=True),
    sa.Column('delivery_type', sa.String(length=50), nullable=True),
    sa.Column('delivery_address_id', GUID(), nullable=True),
    sa.Column('price_at_creation', sa.Float(), nullable=True),
    sa.Column('variant_prices_at_creation', sa.JSON(), nullable=True),
    sa.Column('shipping_amount_at_creation', sa.Float(), nullable=True),
    sa.Column('tax_amount_at_creation', sa.Float(), nullable=True),
    sa.Column('tax_rate_at_creation', sa.Float(), nullable=True),
    sa.Column('current_variant_prices', sa.JSON(), nullable=True),
    sa.Column('current_shipping_amount', sa.Float(), nullable=True),
    sa.Column('current_tax_amount', sa.Float(), nullable=True),
    sa.Column('current_tax_rate', sa.Float(), nullable=True),
    sa.Column('variant_ids', sa.JSON(), nullable=True),
    sa.Column('subscription_metadata', sa.JSON(), nullable=True),
    sa.Column('discount_id', GUID(), nullable=True),
    sa.Column('discount_type', sa.String(length=20), nullable=True),
    sa.Column('discount_value', sa.Float(), nullable=True),
    sa.Column('discount_code', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['delivery_address_id'], ['accounts.addresses.id'], ),
    sa.ForeignKeyConstraint(['discount_id'], ['commerce.promocodes.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_subscriptions_active', 'subscriptions', ['user_id', 'status'], unique=False, schema='commerce', postgresql_where=sa.text("status = 'active'"))
    op.create_index('idx_subscriptions_delivery_address', 'subscriptions', ['delivery_address_id'], unique=False, schema='commerce')
    op.create_index('idx_subscriptions_next_billing_date', 'subscriptions', ['next_billing_date'], unique=False, schema='commerce')
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'], unique=False, schema='commerce')
    op.create_index('idx_subscriptions_status_next_billing', 'subscriptions', ['status', 'next_billing_date'], unique=False, schema='commerce')
    op.create_index('idx_subscriptions_user_id', 'subscriptions', ['user_id'], unique=False, schema='commerce')
    op.create_index('idx_subscriptions_user_status', 'subscriptions', ['user_id', 'status'], unique=False, schema='commerce')
    op.create_table('stock_adjustments',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('inventory_id', GUID(), nullable=False),
    sa.Column('quantity_change', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=False),
    sa.Column('adjusted_by_user_id', GUID(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['adjusted_by_user_id'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['inventory_id'], ['catalog.inventory.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_stock_adjustments_created_at', 'stock_adjustments', ['created_at'], unique=False, schema='catalog')
    op.create_index('idx_stock_adjustments_inventory_created', 'stock_adjustments', ['inventory_id', 'created_at'], unique=False, schema='catalog')
    op.create_index('idx_stock_adjustments_inventory_id', 'stock_adjustments', ['inventory_id'], unique=False, schema='catalog')
    op.create_index('idx_stock_adjustments_reason', 'stock_adjustments', ['reason'], unique=False, schema='catalog')
    op.create_index('idx_stock_adjustments_user_id', 'stock_adjustments', ['adjusted_by_user_id'], unique=False, schema='catalog')
    op.create_table('variant_tracking_entries',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('subscription_id', GUID(), nullable=False),
    sa.Column('price_at_time', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('action_type', sa.Enum('ADDED', 'REMOVED', 'PRICE_CHANGED', name='trackingactiontype'), nullable=False),
    sa.Column('tracking_timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('entry_metadata', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='catalog'
    )
    op.create_index('idx_variant_tracking_entries_action_type', 'variant_tracking_entries', ['action_type'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_currency', 'variant_tracking_entries', ['currency'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_sub_timestamp', 'variant_tracking_entries', ['subscription_id', 'tracking_timestamp'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_subscription_id', 'variant_tracking_entries', ['subscription_id'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_timestamp', 'variant_tracking_entries', ['tracking_timestamp'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_variant_action', 'variant_tracking_entries', ['variant_id', 'action_type'], unique=False, schema='catalog')
    op.create_index('idx_variant_tracking_entries_variant_id', 'variant_tracking_entries', ['variant_id'], unique=False, schema='catalog')
    op.create_table('orders',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_number', sa.String(length=50), nullable=False),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('guest_email', sa.String(length=255), nullable=True),
    sa.Column('subscription_id', GUID(), nullable=True),
    sa.Column('order_status', sa.Enum('PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'REFUNDED', name='orderstatus'), nullable=False),
    sa.Column('payment_status', sa.Enum('PENDING', 'AUTHORIZED', 'PAID', 'FAILED', 'CANCELLED', 'REFUNDED', name='paymentstatus'), nullable=False),
    sa.Column('fulfillment_status', sa.Enum('UNFULFILLED', 'PARTIAL', 'FULFILLED', 'CANCELLED', name='fulfillmentstatus'), nullable=False),
    sa.Column('subtotal', sa.Float(), nullable=False),
    sa.Column('shipping_cost', sa.Float(), nullable=False),
    sa.Column('discount_amount', sa.Float(), nullable=False),
    sa.Column('tax_amount', sa.Float(), nullable=False),
    sa.Column('tax_rate', sa.Float(), nullable=False),
    sa.Column('total_amount', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('shipping_method', sa.String(length=100), nullable=True),
    sa.Column('tracking_number', sa.String(length=255), nullable=True),
    sa.Column('carrier', sa.String(length=100), nullable=True),
    sa.Column('billing_address', postgresql.JSON(astext_type=sa.Text()), nullable=False),
    sa.Column('shipping_address', postgresql.JSON(astext_type=sa.Text()), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('customer_notes', sa.Text(), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    sa.Column('source', sa.Enum('WEB', 'MOBILE', 'API', 'ADMIN', name='ordersource'), nullable=False),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    sa.UniqueConstraint('order_number'),
    schema='commerce'
    )
    op.create_index('idx_orders_confirmed_shipped', 'orders', ['confirmed_at', 'shipped_at'], unique=False, schema='commerce')
    op.create_index('idx_orders_fulfillment_status', 'orders', ['fulfillment_status'], unique=False, schema='commerce')
    op.create_index('idx_orders_order_number', 'orders', ['order_number'], unique=False, schema='commerce')
    op.create_index('idx_orders_payment_status', 'orders', ['payment_status', 'created_at'], unique=False, schema='commerce')
    op.create_index('idx_orders_subscription_id', 'orders', ['subscription_id'], unique=False, schema='commerce')
    op.create_index('idx_orders_total_currency', 'orders', ['total_amount', 'currency'], unique=False, schema='commerce')
    op.create_index('idx_orders_tracking', 'orders', ['tracking_number'], unique=False, schema='commerce')
    op.create_index('idx_orders_user_status', 'orders', ['user_id', 'order_status'], unique=False, schema='commerce')
    op.create_table('product_removal_audit',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', GUID(), nullable=False),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('removed_by', GUID(), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), server_default='NOW()', nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['removed_by'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_product_removal_audit_product_id', 'product_removal_audit', ['product_id'], unique=False, schema='commerce')
    op.create_index('idx_product_removal_audit_removed_at', 'product_removal_audit', ['removed_at'], unique=False, schema='commerce')
    op.create_index('idx_product_removal_audit_removed_by', 'product_removal_audit', ['removed_by'], unique=False, schema='commerce')
    op.create_index('idx_product_removal_audit_sub_product', 'product_removal_audit', ['subscription_id', 'product_id'], unique=False, schema='commerce')
    op.create_index('idx_product_removal_audit_subscription_id', 'product_removal_audit', ['subscription_id'], unique=False, schema='commerce')
    op.create_index('idx_product_removal_audit_user_date', 'product_removal_audit', ['removed_by', 'removed_at'], unique=False, schema='commerce')
    op.create_table('subscription_discounts',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', GUID(), nullable=False),
    sa.Column('discount_id', GUID(), nullable=False),
    sa.Column('discount_amount', sa.Float(), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), server_default='NOW()', nullable=False),
    sa.ForeignKeyConstraint(['discount_id'], ['commerce.discounts.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_subscription_discounts_applied_at', 'subscription_discounts', ['applied_at'], unique=False, schema='commerce')
    op.create_index('idx_subscription_discounts_discount_id', 'subscription_discounts', ['discount_id'], unique=False, schema='commerce')
    op.create_index('idx_subscription_discounts_sub_discount', 'subscription_discounts', ['subscription_id', 'discount_id'], unique=False, schema='commerce')
    op.create_index('idx_subscription_discounts_subscription_id', 'subscription_discounts', ['subscription_id'], unique=False, schema='commerce')
    op.create_table('subscription_products',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subscription_id', GUID(), nullable=False),
    sa.Column('product_id', GUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price', sa.Float(), nullable=False),
    sa.Column('total_price', sa.Float(), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default='NOW()', nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('removed_by', GUID(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['catalog.products.id'], ),
    sa.ForeignKeyConstraint(['removed_by'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['commerce.subscriptions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_subscription_products_active', 'subscription_products', ['subscription_id', 'product_id'], unique=False, schema='commerce', postgresql_where=sa.text('removed_at IS NULL'))
    op.create_index('idx_subscription_products_product_id', 'subscription_products', ['product_id'], unique=False, schema='commerce')
    op.create_index('idx_subscription_products_removed_by', 'subscription_products', ['removed_by'], unique=False, schema='commerce')
    op.create_index('idx_subscription_products_sub_product', 'subscription_products', ['subscription_id', 'product_id'], unique=False, schema='commerce')
    op.create_index('idx_subscription_products_subscription_id', 'subscription_products', ['subscription_id'], unique=False, schema='commerce')
    op.create_table('analytics_events',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('session_id', sa.String(length=255), nullable=False),
    sa.Column('user_id', GUID(), nullable=True),
    sa.Column('event_type', sa.Enum('PAGE_VIEW', 'CART_ADD', 'CART_REMOVE', 'CART_VIEW', 'CHECKOUT_START', 'CHECKOUT_STEP', 'CHECKOUT_COMPLETE', 'CHECKOUT_ABANDON', 'PURCHASE', 'REFUND_REQUEST', 'REFUND_COMPLETE', 'USER_REGISTER', 'USER_LOGIN', name='eventtype'), nullable=False),
    sa.Column('page_url', sa.Text(), nullable=True),
    sa.Column('page_title', sa.String(length=500), nullable=True),
    sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('order_id', GUID(), nullable=True),
    sa.Column('product_id', GUID(), nullable=True),
    sa.Column('variant_id', GUID(), nullable=True),
    sa.Column('category', sa.String(length=255), nullable=True),
    sa.Column('revenue', sa.Float(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['admin.user_sessions.session_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='admin'
    )
    op.create_index('idx_analytics_events_created_at', 'analytics_events', ['created_at'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_order_id', 'analytics_events', ['order_id'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_session_id', 'analytics_events', ['session_id'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_session_type', 'analytics_events', ['session_id', 'event_type'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_type', 'analytics_events', ['event_type'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_type_created', 'analytics_events', ['event_type', 'created_at'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_user_id', 'analytics_events', ['user_id'], unique=False, schema='admin')
    op.create_index('idx_analytics_events_user_type', 'analytics_events', ['user_id', 'event_type'], unique=False, schema='admin')
    op.create_table('order_items',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', GUID(), nullable=False),
    sa.Column('variant_id', GUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('price_per_unit', sa.Float(), nullable=False),
    sa.Column('total_price', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['catalog.product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_order_items_order_id', 'order_items', ['order_id'], unique=False, schema='commerce')
    op.create_index('idx_order_items_variant_id', 'order_items', ['variant_id'], unique=False, schema='commerce')
    op.create_table('payment_intents',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=False),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('subscription_id', GUID(), nullable=True),
    sa.Column('order_id', GUID(), nullable=True),
    sa.Column('amount_breakdown', postgresql.JSON(astext_type=sa.Text()), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('stripe_verification', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('payment_method_id', sa.String(length=255), nullable=True),
    sa.Column('payment_method_type', sa.String(length=50), nullable=True),
    sa.Column('requires_action', sa.Boolean(), nullable=False),
    sa.Column('client_secret', sa.String(length=500), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('payment_intent_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stripe_payment_intent_id'),
    schema='commerce'
    )
    op.create_index('idx_payment_intents_created_at', 'payment_intents', ['created_at'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_currency', 'payment_intents', ['currency'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_expires_at', 'payment_intents', ['expires_at'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_order_id', 'payment_intents', ['order_id'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_status', 'payment_intents', ['status'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_status_created', 'payment_intents', ['status', 'created_at'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_stripe_id', 'payment_intents', ['stripe_payment_intent_id'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_subscription_id', 'payment_intents', ['subscription_id'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_user_id', 'payment_intents', ['user_id'], unique=False, schema='commerce')
    op.create_index('idx_payment_intents_user_status', 'payment_intents', ['user_id', 'status'], unique=False, schema='commerce')
    op.create_table('refunds',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', GUID(), nullable=False),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('refund_number', sa.String(length=50), nullable=False),
    sa.Column('status', sa.Enum('REQUESTED', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', name='refundstatus'), nullable=False),
    sa.Column('refund_type', sa.Enum('FULL_REFUND', 'PARTIAL_REFUND', 'STORE_CREDIT', 'EXCHANGE', name='refundtype'), nullable=False),
    sa.Column('reason', sa.Enum('DEFECTIVE_PRODUCT', 'WRONG_ITEM', 'NOT_AS_DESCRIBED', 'DAMAGED_IN_SHIPPING', 'CHANGED_MIND', 'DUPLICATE_ORDER', 'UNAUTHORIZED_PURCHASE', 'LATE_DELIVERY', 'MISSING_PARTS', 'SIZE_ISSUE', 'QUALITY_ISSUE', 'OTHER', name='refundreason'), nullable=False),
    sa.Column('requested_amount', sa.Float(), nullable=False),
    sa.Column('approved_amount', sa.Float(), nullable=True),
    sa.Column('processed_amount', sa.Float(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('stripe_refund_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_status', sa.String(length=50), nullable=True),
    sa.Column('customer_reason', sa.Text(), nullable=True),
    sa.Column('customer_notes', sa.Text(), nullable=True),
    sa.Column('admin_notes', sa.Text(), nullable=True),
    sa.Column('reviewed_by', GUID(), nullable=True),
    sa.Column('processed_by', GUID(), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('auto_approved', sa.Boolean(), nullable=False),
    sa.Column('requires_return', sa.Boolean(), nullable=False),
    sa.Column('return_shipping_paid', sa.Boolean(), nullable=False),
    sa.Column('refund_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['processed_by'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['accounts.users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('refund_number'),
    sa.UniqueConstraint('stripe_refund_id'),
    schema='commerce'
    )
    op.create_index('idx_refunds_created_at', 'refunds', ['created_at'], unique=False, schema='commerce')
    op.create_index('idx_refunds_order_id', 'refunds', ['order_id'], unique=False, schema='commerce')
    op.create_index('idx_refunds_order_status', 'refunds', ['order_id', 'status'], unique=False, schema='commerce')
    op.create_index('idx_refunds_status', 'refunds', ['status'], unique=False, schema='commerce')
    op.create_index('idx_refunds_status_created', 'refunds', ['status', 'created_at'], unique=False, schema='commerce')
    op.create_index('idx_refunds_stripe_refund_id', 'refunds', ['stripe_refund_id'], unique=False, schema='commerce')
    op.create_index('idx_refunds_type', 'refunds', ['refund_type'], unique=False, schema='commerce')
    op.create_index('idx_refunds_user_id', 'refunds', ['user_id'], unique=False, schema='commerce')
    op.create_index('idx_refunds_user_status', 'refunds', ['user_id', 'status'], unique=False, schema='commerce')
    op.create_table('tracking_events',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', GUID(), nullable=False),
    sa.Column('status', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_tracking_events_created_at', 'tracking_events', ['created_at'], unique=False, schema='commerce')
    op.create_index('idx_tracking_events_order_id', 'tracking_events', ['order_id'], unique=False, schema='commerce')
    op.create_table('refund_items',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refund_id', GUID(), nullable=False),
    sa.Column('order_item_id', GUID(), nullable=False),
    sa.Column('quantity_to_refund', sa.Integer(), nullable=False),
    sa.Column('unit_price', sa.Float(), nullable=False),
    sa.Column('total_refund_amount', sa.Float(), nullable=False),
    sa.Column('condition_notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['order_item_id'], ['commerce.order_items.id'], ),
    sa.ForeignKeyConstraint(['refund_id'], ['commerce.refunds.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_refund_items_order_item_id', 'refund_items', ['order_item_id'], unique=False, schema='commerce')
    op.create_index('idx_refund_items_refund_id', 'refund_items', ['refund_id'], unique=False, schema='commerce')
    op.create_table('shipment_tracking',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', GUID(), nullable=False),
    sa.Column('order_item_id', GUID(), nullable=True),
    sa.Column('provider_id', GUID(), nullable=False),
    sa.Column('tracking_number', sa.String(length=100), nullable=False),
    sa.Column('carrier', postgresql.ENUM('UPS', 'CANADA_EXPRESS', 'ROYAL_MAIL', 'FEDEX', 'DHL', 'USPS', 'CANADA_POST', 'PUROLATOR', 'TNT', 'ARAMEX', 'LASERSHIP', 'ONTRAC', 'HERMES', 'EVRI', 'DPD', 'DPD_LOCAL', 'GLS', 'POSTNL', 'BPOST', 'SWISS_POST', 'AUSTRALIA_POST', 'NZ_POST', 'JAPAN_POST', 'KOREA_POST', 'CHINA_POST', 'SF_EXPRESS', 'YANWEN', 'CAINIAO', 'LAPOSTE', 'COLISSIMO', 'CORREOS', 'POSTE_ITALIANE', 'POSTNORD', 'BRING', 'BLUE_DART', 'DELHIVERY', 'DTDC', 'XPRESSBEES', 'OTHER', name='shipment_carrier'), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDING', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELAYED', 'EXCEPTION', 'RETURNED', 'CANCELLED', name='tracking_status'), nullable=False),
    sa.Column('shipment_type', postgresql.ENUM('STANDARD', 'EXPRESS', 'OVERNIGHT', 'INTERNATIONAL', 'FREIGHT', name='shipment_type'), nullable=False),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('estimated_delivery', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_delivery', sa.DateTime(timezone=True), nullable=True),
    sa.Column('origin_address', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('destination_address', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('current_location', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('delivery_instructions', sa.Text(), nullable=True),
    sa.Column('package_weight', sa.Float(), nullable=True),
    sa.Column('package_dimensions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('package_value', sa.Float(), nullable=True),
    sa.Column('insurance_amount', sa.Float(), nullable=True),
    sa.Column('service_level', sa.String(length=50), nullable=True),
    sa.Column('delivery_signature_required', sa.Boolean(), nullable=False),
    sa.Column('delivery_confirmation', sa.String(length=100), nullable=True),
    sa.Column('external_tracking_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('last_api_sync', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_status', sa.String(length=50), nullable=False),
    sa.Column('customer_notified', sa.Boolean(), nullable=False),
    sa.Column('notification_preferences', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['order_item_id'], ['commerce.order_items.id'], ),
    sa.ForeignKeyConstraint(['provider_id'], ['commerce.shipping_providers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tracking_number'),
    schema='commerce'
    )
    op.create_index('idx_shipment_tracking_carrier', 'shipment_tracking', ['carrier'], unique=False, schema='commerce')
    op.create_index('idx_shipment_tracking_created_at', 'shipment_tracking', ['created_at'], unique=False, schema='commerce')
    op.create_index('idx_shipment_tracking_estimated_delivery', 'shipment_tracking', ['estimated_delivery'], unique=False, schema='commerce')
    op.create_index('idx_shipment_tracking_order_id', 'shipment_tracking', ['order_id'], unique=False, schema='commerce')
    op.create_index('idx_shipment_tracking_status', 'shipment_tracking', ['status'], unique=False, schema='commerce')
    op.create_index('idx_shipment_tracking_tracking_number', 'shipment_tracking', ['tracking_number'], unique=False, schema='commerce')
    op.create_table('transactions',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', GUID(), nullable=False),
    sa.Column('order_id', GUID(), nullable=True),
    sa.Column('payment_intent_id', GUID(), nullable=True),
    sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('transaction_type', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    sa.Column('request_id', sa.String(length=255), nullable=True),
    sa.Column('transaction_metadata', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['commerce.orders.id'], ),
    sa.ForeignKeyConstraint(['payment_intent_id'], ['commerce.payment_intents.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    schema='commerce'
    )
    op.create_index('idx_transactions_amount', 'transactions', ['amount'], unique=False, schema='commerce')
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'], unique=False, schema='commerce')
    op.create_index('idx_transactions_currency', 'transactions', ['currency'], unique=False, schema='commerce')
    op.create_index('idx_transactions_idempotency_key', 'transactions', ['idempotency_key'], unique=False, schema='commerce')
    op.create_index('idx_transactions_order_id', 'transactions', ['order_id'], unique=False, schema='commerce')
    op.create_index('idx_transactions_payment_intent_id', 'transactions', ['payment_intent_id'], unique=False, schema='commerce')
    op.create_index('idx_transactions_request_id', 'transactions', ['request_id'], unique=False, schema='commerce')
    op.create_index('idx_transactions_status', 'transactions', ['status'], unique=False, schema='commerce')
    op.create_index('idx_transactions_status_created', 'transactions', ['status', 'created_at'], unique=False, schema='commerce')
    op.create_index('idx_transactions_stripe_id', 'transactions', ['stripe_payment_intent_id'], unique=False, schema='commerce')
    op.create_index('idx_transactions_type', 'transactions', ['transaction_type'], unique=False, schema='commerce')
    op.create_index('idx_transactions_user_id', 'transactions', ['user_id'], unique=False, schema='commerce')
    op.create_index('idx_transactions_user_status', 'transactions', ['user_id', 'status'], unique=False, schema='commerce')
    op.create_index('idx_transactions_user_type', 'transactions', ['user_id', 'transaction_type'], unique=False, schema='commerce')
    op.create_table('shipment_tracking_events',
    sa.Column('id', GUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('shipment_id', GUID(), nullable=False),
    sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('event_description', sa.Text(), nullable=False),
    sa.Column('event_location', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('carrier_event_code', sa.String(length=50), nullable=True),
    sa.Column('carrier_event_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('estimated_delivery', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delay_reason', sa.String(length=255), nullable=True),
    sa.Column('exception_details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('contact_name', sa.String(length=100), nullable=True),
    sa.Column('contact_phone', sa.String(length=20), nullable=True),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('raw_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['shipment_id'], ['commerce.shipment_tracking.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='commerce'
    )
    op.create_index('idx_tracking_events_event_type', 'shipment_tracking_events', ['event_type'], unique=False, schema='commerce')
    op.create_index('idx_tracking_events_shipment_id', 'shipment_tracking_events', ['shipment_id'], unique=False, schema='commerce')
    op.create_index('idx_tracking_events_timestamp', 'shipment_tracking_events', ['event_timestamp'], unique=False, schema='commerce')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_tracking_events_timestamp', table_name='shipment_tracking_events', schema='commerce')
    op.drop_index('idx_tracking_events_shipment_id', table_name='shipment_tracking_events', schema='commerce')
    op.drop_index('idx_tracking_events_event_type', table_name='shipment_tracking_events', schema='commerce')
    op.drop_table('shipment_tracking_events', schema='commerce')
    op.drop_index('idx_transactions_user_type', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_user_status', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_user_id', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_type', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_stripe_id', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_status_created', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_status', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_request_id', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_payment_intent_id', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_order_id', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_idempotency_key', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_currency', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_created_at', table_name='transactions', schema='commerce')
    op.drop_index('idx_transactions_amount', table_name='transactions', schema='commerce')
    op.drop_table('transactions', schema='commerce')
    op.drop_index('idx_shipment_tracking_tracking_number', table_name='shipment_tracking', schema='commerce')
    op.drop_index('idx_shipment_tracking_status', table_name='shipment_tracking', schema='commerce')
    op.drop_index('idx_shipment_tracking_order_id', table_name='shipment_tracking', schema='commerce')
    op.drop_index('idx_shipment_tracking_estimated_delivery', table_name='shipment_tracking', schema='commerce')
    op.drop_index('idx_shipment_tracking_created_at', table_name='shipment_tracking', schema='commerce')
    op.drop_index('idx_shipment_tracking_carrier', table_name='shipment_tracking', schema='commerce')
    op.drop_table('shipment_tracking', schema='commerce')
    op.drop_index('idx_refund_items_refund_id', table_name='refund_items', schema='commerce')
    op.drop_index('idx_refund_items_order_item_id', table_name='refund_items', schema='commerce')
    op.drop_table('refund_items', schema='commerce')
    op.drop_index('idx_tracking_events_order_id', table_name='tracking_events', schema='commerce')
    op.drop_index('idx_tracking_events_created_at', table_name='tracking_events', schema='commerce')
    op.drop_table('tracking_events', schema='commerce')
    op.drop_index('idx_refunds_user_status', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_user_id', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_type', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_stripe_refund_id', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_status_created', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_status', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_order_status', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_order_id', table_name='refunds', schema='commerce')
    op.drop_index('idx_refunds_created_at', table_name='refunds', schema='commerce')
    op.drop_table('refunds', schema='commerce')
    op.drop_index('idx_payment_intents_user_status', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_user_id', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_subscription_id', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_stripe_id', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_status_created', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_status', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_order_id', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_expires_at', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_currency', table_name='payment_intents', schema='commerce')
    op.drop_index('idx_payment_intents_created_at', table_name='payment_intents', schema='commerce')
    op.drop_table('payment_intents', schema='commerce')
    op.drop_index('idx_order_items_variant_id', table_name='order_items', schema='commerce')
    op.drop_index('idx_order_items_order_id', table_name='order_items', schema='commerce')
    op.drop_table('order_items', schema='commerce')
    op.drop_index('idx_analytics_events_user_type', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_user_id', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_type_created', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_type', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_session_type', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_session_id', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_order_id', table_name='analytics_events', schema='admin')
    op.drop_index('idx_analytics_events_created_at', table_name='analytics_events', schema='admin')
    op.drop_table('analytics_events', schema='admin')
    op.drop_index('idx_subscription_products_subscription_id', table_name='subscription_products', schema='commerce')
    op.drop_index('idx_subscription_products_sub_product', table_name='subscription_products', schema='commerce')
    op.drop_index('idx_subscription_products_removed_by', table_name='subscription_products', schema='commerce')
    op.drop_index('idx_subscription_products_product_id', table_name='subscription_products', schema='commerce')
    op.drop_index('idx_subscription_products_active', table_name='subscription_products', schema='commerce', postgresql_where=sa.text('removed_at IS NULL'))
    op.drop_table('subscription_products', schema='commerce')
    op.drop_index('idx_subscription_discounts_subscription_id', table_name='subscription_discounts', schema='commerce')
    op.drop_index('idx_subscription_discounts_sub_discount', table_name='subscription_discounts', schema='commerce')
    op.drop_index('idx_subscription_discounts_discount_id', table_name='subscription_discounts', schema='commerce')
    op.drop_index('idx_subscription_discounts_applied_at', table_name='subscription_discounts', schema='commerce')
    op.drop_table('subscription_discounts', schema='commerce')
    op.drop_index('idx_product_removal_audit_user_date', table_name='product_removal_audit', schema='commerce')
    op.drop_index('idx_product_removal_audit_subscription_id', table_name='product_removal_audit', schema='commerce')
    op.drop_index('idx_product_removal_audit_sub_product', table_name='product_removal_audit', schema='commerce')
    op.drop_index('idx_product_removal_audit_removed_by', table_name='product_removal_audit', schema='commerce')
    op.drop_index('idx_product_removal_audit_removed_at', table_name='product_removal_audit', schema='commerce')
    op.drop_index('idx_product_removal_audit_product_id', table_name='product_removal_audit', schema='commerce')
    op.drop_table('product_removal_audit', schema='commerce')
    op.drop_index('idx_orders_user_status', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_tracking', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_total_currency', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_subscription_id', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_payment_status', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_order_number', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_fulfillment_status', table_name='orders', schema='commerce')
    op.drop_index('idx_orders_confirmed_shipped', table_name='orders', schema='commerce')
    op.drop_table('orders', schema='commerce')
    op.drop_index('idx_variant_tracking_entries_variant_id', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_variant_action', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_timestamp', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_subscription_id', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_sub_timestamp', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_currency', table_name='variant_tracking_entries', schema='catalog')
    op.drop_index('idx_variant_tracking_entries_action_type', table_name='variant_tracking_entries', schema='catalog')
    op.drop_table('variant_tracking_entries', schema='catalog')
    op.drop_index('idx_stock_adjustments_user_id', table_name='stock_adjustments', schema='catalog')
    op.drop_index('idx_stock_adjustments_reason', table_name='stock_adjustments', schema='catalog')
    op.drop_index('idx_stock_adjustments_inventory_id', table_name='stock_adjustments', schema='catalog')
    op.drop_index('idx_stock_adjustments_inventory_created', table_name='stock_adjustments', schema='catalog')
    op.drop_index('idx_stock_adjustments_created_at', table_name='stock_adjustments', schema='catalog')
    op.drop_table('stock_adjustments', schema='catalog')
    op.drop_index('idx_subscriptions_user_status', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_user_id', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_status_next_billing', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_status', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_next_billing_date', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_delivery_address', table_name='subscriptions', schema='commerce')
    op.drop_index('idx_subscriptions_active', table_name='subscriptions', schema='commerce', postgresql_where=sa.text("status = 'active'"))
    op.drop_table('subscriptions', schema='commerce')
    op.drop_index('idx_cart_items_variant_id', table_name='cart_items', schema='commerce')
    op.drop_index('idx_cart_items_product_id', table_name='cart_items', schema='commerce')
    op.drop_index('idx_cart_items_cart_product_variant', table_name='cart_items', schema='commerce')
    op.drop_index('idx_cart_items_cart_id', table_name='cart_items', schema='commerce')
    op.drop_table('cart_items', schema='commerce')
    op.drop_index('idx_wishlist_items_wishlist_product', table_name='wishlist_items', schema='catalog')
    op.drop_index('idx_wishlist_items_wishlist_id', table_name='wishlist_items', schema='catalog')
    op.drop_index('idx_wishlist_items_variant_id', table_name='wishlist_items', schema='catalog')
    op.drop_index('idx_wishlist_items_product_id', table_name='wishlist_items', schema='catalog')
    op.drop_index('idx_wishlist_items_created_at', table_name='wishlist_items', schema='catalog')
    op.drop_table('wishlist_items', schema='catalog')
    op.drop_index('idx_variant_substitutions_substitute_id', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_substitute_active', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_similarity_score', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_reason', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_original_id', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_original_active', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_active', table_name='variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_substitutions_acceptance_rate', table_name='variant_substitutions', schema='catalog')
    op.drop_table('variant_substitutions', schema='catalog')
    op.drop_index('idx_variant_price_history_variant_id', table_name='variant_price_history', schema='catalog')
    op.drop_index('idx_variant_price_history_variant_effective', table_name='variant_price_history', schema='catalog')
    op.drop_index('idx_variant_price_history_effective_date', table_name='variant_price_history', schema='catalog')
    op.drop_index('idx_variant_price_history_currency', table_name='variant_price_history', schema='catalog')
    op.drop_index('idx_variant_price_history_changed_by', table_name='variant_price_history', schema='catalog')
    op.drop_index('idx_variant_price_history_change_reason', table_name='variant_price_history', schema='catalog')
    op.drop_table('variant_price_history', schema='catalog')
    op.drop_index('idx_variant_analytics_variant_id', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_variant_date', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_total_revenue', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_popularity_rank', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_period_type', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_date_period', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_date', table_name='variant_analytics', schema='catalog')
    op.drop_index('idx_variant_analytics_currency', table_name='variant_analytics', schema='catalog')
    op.drop_table('variant_analytics', schema='catalog')
    op.drop_index('idx_images_variant_id', table_name='product_images', schema='catalog')
    op.drop_index('idx_images_primary', table_name='product_images', schema='catalog')
    op.drop_table('product_images', schema='catalog')
    op.drop_index('idx_inventory_variant_status', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_variant_id', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_status', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_quantity_available', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_low_stock', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_location_quantity', table_name='inventory', schema='catalog')
    op.drop_index('idx_inventory_location_id', table_name='inventory', schema='catalog')
    op.drop_table('inventory', schema='catalog')
    op.drop_index('idx_conversion_funnels_user_id', table_name='conversion_funnels', schema='admin')
    op.drop_index('idx_conversion_funnels_step', table_name='conversion_funnels', schema='admin')
    op.drop_index('idx_conversion_funnels_session_id', table_name='conversion_funnels', schema='admin')
    op.drop_index('idx_conversion_funnels_created_at', table_name='conversion_funnels', schema='admin')
    op.drop_table('conversion_funnels', schema='admin')
    op.drop_index('idx_shipping_webhooks_provider', table_name='shipping_webhooks', schema='commerce')
    op.drop_index('idx_shipping_webhooks_active', table_name='shipping_webhooks', schema='commerce')
    op.drop_table('shipping_webhooks', schema='commerce')
    op.drop_index('idx_payment_methods_user_id', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_user_default', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_user_active', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_type', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_stripe_id', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_provider', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_default', table_name='payment_methods', schema='commerce')
    op.drop_index('idx_payment_methods_active', table_name='payment_methods', schema='commerce')
    op.drop_table('payment_methods', schema='commerce')
    op.drop_index('idx_carts_user_id', table_name='carts', schema='commerce')
    op.drop_table('carts', schema='commerce')
    op.drop_index('idx_wishlists_user_id', table_name='wishlists', schema='catalog')
    op.drop_index('idx_wishlists_user_default', table_name='wishlists', schema='catalog')
    op.drop_index('idx_wishlists_public', table_name='wishlists', schema='catalog')
    op.drop_index('idx_wishlists_name', table_name='wishlists', schema='catalog')
    op.drop_index('idx_wishlists_default', table_name='wishlists', schema='catalog')
    op.drop_table('wishlists', schema='catalog')
    op.drop_index('idx_reviews_verified', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_user_id', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_user_approved', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_rating', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_product_rating', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_product_id', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_product_approved', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_created_at', table_name='reviews', schema='catalog')
    op.drop_index('idx_reviews_approved', table_name='reviews', schema='catalog')
    op.drop_table('reviews', schema='catalog')
    op.drop_index('idx_variants_sku', table_name='product_variants', schema='catalog')
    op.drop_index('idx_variants_product_id', table_name='product_variants', schema='catalog')
    op.drop_index('idx_variants_price', table_name='product_variants', schema='catalog')
    op.drop_index('idx_variants_availability', table_name='product_variants', schema='catalog')
    op.drop_index('idx_variants_active', table_name='product_variants', schema='catalog')
    op.drop_table('product_variants', schema='catalog')
    op.drop_index('idx_user_sessions_user_id', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_user_created', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_traffic_source', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_started_at', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_source_created', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_session_id', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_ended_at', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_created_at', table_name='user_sessions', schema='admin')
    op.drop_index('idx_user_sessions_converted', table_name='user_sessions', schema='admin')
    op.drop_table('user_sessions', schema='admin')
    op.drop_index('idx_customer_lifecycle_user_id', table_name='customer_lifecycle_metrics', schema='admin')
    op.drop_index('idx_customer_lifecycle_segment', table_name='customer_lifecycle_metrics', schema='admin')
    op.drop_index('idx_customer_lifecycle_created_at', table_name='customer_lifecycle_metrics', schema='admin')
    op.drop_table('customer_lifecycle_metrics', schema='admin')
    op.drop_index('idx_contact_messages_status_priority', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_status_created', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_status', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_resolved_at', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_priority', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_email', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_created_at', table_name='contact_messages', schema='system')
    op.drop_index('idx_contact_messages_assigned_to', table_name='contact_messages', schema='system')
    op.drop_table('contact_messages', schema='system')
    op.drop_index('idx_tax_rules_tax_rate', table_name='tax_rules', schema='commerce')
    op.drop_index('idx_tax_rules_location_code', table_name='tax_rules', schema='commerce')
    op.drop_index('idx_tax_rules_location_active', table_name='tax_rules', schema='commerce')
    op.drop_index('idx_tax_rules_active', table_name='tax_rules', schema='commerce')
    op.drop_table('tax_rules', schema='commerce')
    op.drop_index('idx_tax_country_province', table_name='tax_rates', schema='commerce')
    op.drop_table('tax_rates', schema='commerce')
    op.drop_index('idx_shipping_rules_weight_range', table_name='shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_rules_weight_active', table_name='shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_rules_location_code', table_name='shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_rules_location_active', table_name='shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_rules_base_rate', table_name='shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_rules_active', table_name='shipping_rules', schema='commerce')
    op.drop_table('shipping_rules', schema='commerce')
    op.drop_index('idx_shipping_providers_carrier', table_name='shipping_providers', schema='commerce')
    op.drop_index('idx_shipping_providers_active', table_name='shipping_providers', schema='commerce')
    op.drop_table('shipping_providers', schema='commerce')
    op.drop_index('idx_shipping_methods_price', table_name='shipping_methods', schema='commerce')
    op.drop_index('idx_shipping_methods_name', table_name='shipping_methods', schema='commerce')
    op.drop_index('idx_shipping_methods_estimated_days', table_name='shipping_methods', schema='commerce')
    op.drop_index('idx_shipping_methods_active_price', table_name='shipping_methods', schema='commerce')
    op.drop_index('idx_shipping_methods_active', table_name='shipping_methods', schema='commerce')
    op.drop_table('shipping_methods', schema='commerce')
    op.drop_index('idx_promocodes_valid_until', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_valid_from', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_used_count', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_usage_limit', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_discount_type', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_code', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_active_valid', table_name='promocodes', schema='commerce')
    op.drop_index('idx_promocodes_active', table_name='promocodes', schema='commerce')
    op.drop_table('promocodes', schema='commerce')
    op.drop_index('idx_discounts_valid_until', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_valid_from', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_used_count', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_usage_limit', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_type', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_code_active', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_code', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_active_valid', table_name='discounts', schema='commerce')
    op.drop_index('idx_discounts_active', table_name='discounts', schema='commerce')
    op.drop_table('discounts', schema='commerce')
    op.drop_index('idx_warehouse_locations_name', table_name='warehouse_locations', schema='catalog')
    op.drop_table('warehouse_locations', schema='catalog')
    op.drop_index('idx_products_slug', table_name='products', schema='catalog')
    op.drop_index('idx_products_published', table_name='products', schema='catalog')
    op.drop_index('idx_products_category_status', table_name='products', schema='catalog')
    op.drop_table('products', schema='catalog')
    op.drop_index('idx_subscription_cost_history_subscription_id', table_name='subscription_cost_history', schema='admin')
    op.drop_index('idx_subscription_cost_history_sub_effective', table_name='subscription_cost_history', schema='admin')
    op.drop_index('idx_subscription_cost_history_effective_date', table_name='subscription_cost_history', schema='admin')
    op.drop_index('idx_subscription_cost_history_created_at', table_name='subscription_cost_history', schema='admin')
    op.drop_index('idx_subscription_cost_history_changed_by', table_name='subscription_cost_history', schema='admin')
    op.drop_index('idx_subscription_cost_history_change_reason', table_name='subscription_cost_history', schema='admin')
    op.drop_table('subscription_cost_history', schema='admin')
    op.drop_table('subscription_analytics', schema='admin')
    op.drop_index('idx_pricing_configs_version', table_name='pricing_configs', schema='admin')
    op.drop_index('idx_pricing_configs_updated_by', table_name='pricing_configs', schema='admin')
    op.drop_index('idx_pricing_configs_created_at', table_name='pricing_configs', schema='admin')
    op.drop_index('idx_pricing_configs_active', table_name='pricing_configs', schema='admin')
    op.drop_table('pricing_configs', schema='admin')
    op.drop_table('payment_analytics', schema='admin')
    # ### end Alembic commands ###
    op.drop_index('idx_addresses_country_city', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_user_kind', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_user_default', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_default', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_kind', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_post_code', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_country', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_state', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_city', table_name='addresses', schema='accounts')
    op.drop_index('idx_addresses_user_id', table_name='addresses', schema='accounts')
    op.drop_table('addresses', schema='accounts')
    op.drop_index('idx_users_gender', table_name='users', schema='accounts')
    op.drop_index('idx_users_age', table_name='users', schema='accounts')
    op.drop_index('idx_users_stripe_customer', table_name='users', schema='accounts')
    op.drop_index('idx_users_last_login', table_name='users', schema='accounts')
    op.drop_index('idx_users_country_language', table_name='users', schema='accounts')
    op.drop_index('idx_users_role_verification_status', table_name='users', schema='accounts')
    op.drop_index('idx_users_email_account_status', table_name='users', schema='accounts')
    op.drop_table('users', schema='accounts')
    op.execute('DROP SCHEMA IF EXISTS accounts CASCADE')
    op.execute('DROP SCHEMA IF EXISTS catalog CASCADE')
    op.execute('DROP SCHEMA IF EXISTS commerce CASCADE')
    op.execute('DROP SCHEMA IF EXISTS admin CASCADE')
    op.execute('DROP SCHEMA IF EXISTS system CASCADE')
