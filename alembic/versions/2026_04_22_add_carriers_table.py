"""Add carriers table; replace the ShippingCarrier enum on shipping_providers/shipment_tracking with a carrier_id FK

Revision ID: 2026_04_22_carrier
Revises: 2026_04_21_category
Create Date: 2026-04-22 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from core.db import GUID
from core.utils.uuid_utils import uuid7

revision: str = '2026_04_22_carrier'
down_revision: Union[str, None] = '2026_04_21_category'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The only carriers with a real API integration (services/commerce/carrier_integrations.py).
# Anything else in the old enum had no backing implementation, so it isn't carried forward -
# admins can add more carriers through the new /shipping-tracking/carriers/ endpoint.
SEED_CARRIERS = [
    ("ups", "UPS"),
    ("canada_express", "Canada Express"),
    ("royal_mail", "Royal Mail"),
    ("fedex", "FedEx"),
    ("dhl", "DHL"),
    ("usps", "USPS"),
    ("canada_post", "Canada Post"),
    ("purolator", "Purolator"),
]


def upgrade() -> None:
    op.create_table(
        'carriers',
        sa.Column('id', GUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('code', sa.String(length=50), nullable=False, unique=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('tracking_url_template', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        schema='commerce'
    )
    op.create_index('idx_carriers_code', 'carriers', ['code'], schema='commerce')
    op.create_index('idx_carriers_active', 'carriers', ['is_active'], schema='commerce')

    conn = op.get_bind()
    carrier_ids = {}
    for code, name in SEED_CARRIERS:
        new_id = str(uuid7())
        carrier_ids[code] = new_id
        conn.execute(
            sa.text(
                "INSERT INTO commerce.carriers (id, code, name, is_active) "
                "VALUES (:id, :code, :name, true)"
            ),
            {"id": new_id, "code": code, "name": name}
        )

    # --- shipping_providers: enum column -> FK column ---
    op.add_column(
        'shipping_providers',
        sa.Column('carrier_id', GUID(), sa.ForeignKey('commerce.carriers.id'), nullable=True),
        schema='commerce'
    )
    for code, new_id in carrier_ids.items():
        conn.execute(
            sa.text("UPDATE commerce.shipping_providers SET carrier_id = :cid WHERE carrier::text = :code"),
            {"cid": new_id, "code": code}
        )
    op.drop_index('idx_shipping_providers_carrier', table_name='shipping_providers', schema='commerce')
    op.drop_column('shipping_providers', 'carrier', schema='commerce')
    op.alter_column('shipping_providers', 'carrier_id', nullable=False, schema='commerce')
    op.create_index('idx_shipping_providers_carrier', 'shipping_providers', ['carrier_id'], schema='commerce')

    # --- shipment_tracking: enum column -> FK column ---
    op.add_column(
        'shipment_tracking',
        sa.Column('carrier_id', GUID(), sa.ForeignKey('commerce.carriers.id'), nullable=True),
        schema='commerce'
    )
    for code, new_id in carrier_ids.items():
        conn.execute(
            sa.text("UPDATE commerce.shipment_tracking SET carrier_id = :cid WHERE carrier::text = :code"),
            {"cid": new_id, "code": code}
        )
    op.drop_index('idx_shipment_tracking_carrier', table_name='shipment_tracking', schema='commerce')
    op.drop_column('shipment_tracking', 'carrier', schema='commerce')
    op.alter_column('shipment_tracking', 'carrier_id', nullable=False, schema='commerce')
    op.create_index('idx_shipment_tracking_carrier', 'shipment_tracking', ['carrier_id'], schema='commerce')

    # Old Postgres enum types are no longer referenced by any column
    op.execute("DROP TYPE IF EXISTS shipping_carrier")
    op.execute("DROP TYPE IF EXISTS shipment_carrier")


def downgrade() -> None:
    shipping_carrier_enum = sa.Enum(
        'ups', 'canada_express', 'royal_mail', 'fedex', 'dhl', 'usps', 'canada_post', 'purolator',
        'tnt', 'aramex', 'lasership', 'ontrac', 'hermes', 'evri', 'dpd', 'dpd_local', 'gls',
        'postnl', 'bpost', 'swiss_post', 'australia_post', 'nz_post', 'japan_post', 'korea_post',
        'china_post', 'sf_express', 'yanwen', 'cainiao', 'laposte', 'colissimo', 'correos',
        'poste_italiane', 'postnord', 'bring', 'blue_dart', 'delhivery', 'dtdc', 'xpressbees', 'other',
        name='shipping_carrier'
    )
    shipment_carrier_enum = sa.Enum(
        'ups', 'canada_express', 'royal_mail', 'fedex', 'dhl', 'usps', 'canada_post', 'purolator',
        'tnt', 'aramex', 'lasership', 'ontrac', 'hermes', 'evri', 'dpd', 'dpd_local', 'gls',
        'postnl', 'bpost', 'swiss_post', 'australia_post', 'nz_post', 'japan_post', 'korea_post',
        'china_post', 'sf_express', 'yanwen', 'cainiao', 'laposte', 'colissimo', 'correos',
        'poste_italiane', 'postnord', 'bring', 'blue_dart', 'delhivery', 'dtdc', 'xpressbees', 'other',
        name='shipment_carrier'
    )
    conn = op.get_bind()
    shipping_carrier_enum.create(conn, checkfirst=True)
    shipment_carrier_enum.create(conn, checkfirst=True)

    op.drop_index('idx_shipment_tracking_carrier', table_name='shipment_tracking', schema='commerce')
    op.add_column('shipment_tracking', sa.Column('carrier', shipment_carrier_enum, nullable=True), schema='commerce')
    conn.execute(sa.text(
        "UPDATE commerce.shipment_tracking st SET carrier = c.code::shipment_carrier "
        "FROM commerce.carriers c WHERE st.carrier_id = c.id"
    ))
    op.alter_column('shipment_tracking', 'carrier', nullable=False, schema='commerce')
    op.create_index('idx_shipment_tracking_carrier', 'shipment_tracking', ['carrier'], schema='commerce')
    op.drop_column('shipment_tracking', 'carrier_id', schema='commerce')

    op.drop_index('idx_shipping_providers_carrier', table_name='shipping_providers', schema='commerce')
    op.add_column('shipping_providers', sa.Column('carrier', shipping_carrier_enum, nullable=True), schema='commerce')
    conn.execute(sa.text(
        "UPDATE commerce.shipping_providers sp SET carrier = c.code::shipping_carrier "
        "FROM commerce.carriers c WHERE sp.carrier_id = c.id"
    ))
    op.alter_column('shipping_providers', 'carrier', nullable=False, schema='commerce')
    op.create_index('idx_shipping_providers_carrier', 'shipping_providers', ['carrier'], schema='commerce')
    op.drop_column('shipping_providers', 'carrier_id', schema='commerce')

    op.drop_index('idx_carriers_active', table_name='carriers', schema='commerce')
    op.drop_index('idx_carriers_code', table_name='carriers', schema='commerce')
    op.drop_table('carriers', schema='commerce')
