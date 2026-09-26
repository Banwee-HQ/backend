"""subscription totals

Stores a subscription's current subtotal, discount and total, so every screen shows the backend's figures.

Revision ID: 4e8a1c2b7d55
Revises: 9c4d2e7f1b30
Create Date: 2026-09-25 11:00:00

"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4e8a1c2b7d55'
down_revision: Union[str, None] = '9c4d2e7f1b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ('current_subtotal', 'current_discount_amount', 'current_total')


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column('subscriptions', sa.Column(name, sa.Numeric(10, 2), nullable=True), schema='commerce')

    # Fill existing subscriptions from their stored line prices, shipping, tax and discount.
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, current_variant_prices, current_shipping_amount, current_tax_amount, discount_type, discount_value "
        "FROM commerce.subscriptions"
    )).mappings().all()
    cent = Decimal('0.01')
    for row in rows:
        subtotal = sum((Decimal(str(line.get('price', 0))) * int(line.get('qty', 1)) for line in (row['current_variant_prices'] or [])), Decimal('0'))
        value = Decimal(str(row['discount_value'] or 0))
        discount = (subtotal * value / 100) if row['discount_type'] == 'percentage' else value
        discount = min(discount, subtotal).quantize(cent, rounding=ROUND_HALF_UP)
        total = subtotal + Decimal(str(row['current_shipping_amount'] or 0)) + Decimal(str(row['current_tax_amount'] or 0)) - discount
        bind.execute(
            sa.text("UPDATE commerce.subscriptions SET current_subtotal=:s, current_discount_amount=:d, current_total=:t WHERE id=:id"),
            {"s": subtotal.quantize(cent), "d": discount, "t": total.quantize(cent), "id": row['id']},
        )


def downgrade() -> None:
    for name in COLUMNS:
        op.drop_column('subscriptions', name, schema='commerce')
