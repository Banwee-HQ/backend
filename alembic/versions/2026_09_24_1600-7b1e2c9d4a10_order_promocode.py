"""order promocode

Records which promocode an order redeemed, so an unpaid order can give the redemption back.

Revision ID: 7b1e2c9d4a10
Revises: 55f33a6d3f55
Create Date: 2026-09-24 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import core.db

# revision identifiers, used by Alembic.
revision: str = '7b1e2c9d4a10'
down_revision: Union[str, None] = '55f33a6d3f55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('promocode_id', core.db.GUID(), nullable=True), schema='commerce')
    op.create_foreign_key('fk_orders_promocode_id', 'orders', 'promocodes', ['promocode_id'], ['id'],
                          source_schema='commerce', referent_schema='commerce', ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_orders_promocode_id', 'orders', schema='commerce', type_='foreignkey')
    op.drop_column('orders', 'promocode_id', schema='commerce')
