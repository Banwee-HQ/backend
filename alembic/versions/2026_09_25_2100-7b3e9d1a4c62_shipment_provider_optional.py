"""shipment provider optional

Shipments can be recorded without a carrier API account; deleting a provider detaches its shipments.

Revision ID: 7b3e9d1a4c62
Revises: 4e8a1c2b7d55
Create Date: 2026-09-25 21:00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b3e9d1a4c62'
down_revision: Union[str, None] = '4e8a1c2b7d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = 'shipment_tracking_provider_id_fkey'


def upgrade() -> None:
    op.alter_column('shipment_tracking', 'provider_id', nullable=True, schema='commerce')
    op.drop_constraint(FK, 'shipment_tracking', schema='commerce', type_='foreignkey')
    op.create_foreign_key(FK, 'shipment_tracking', 'shipping_providers', ['provider_id'], ['id'],
                          source_schema='commerce', referent_schema='commerce', ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(FK, 'shipment_tracking', schema='commerce', type_='foreignkey')
    op.create_foreign_key(FK, 'shipment_tracking', 'shipping_providers', ['provider_id'], ['id'],
                          source_schema='commerce', referent_schema='commerce')
    op.execute("DELETE FROM commerce.shipment_tracking WHERE provider_id IS NULL")
    op.alter_column('shipment_tracking', 'provider_id', nullable=False, schema='commerce')
