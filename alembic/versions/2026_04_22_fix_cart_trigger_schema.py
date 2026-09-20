"""Schema-qualify the cart-touch trigger/function (was unqualified 'carts' - broke on any
connection whose search_path doesn't happen to include commerce at trigger-execution time,
which made every add-to-cart fail against the real DB).

Revision ID: 2026_04_22_carttrig
Revises: 2026_04_22_carrier
Create Date: 2026-04-22 00:30:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = '2026_04_22_carttrig'
down_revision: Union[str, None] = '2026_04_22_carrier'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_update_cart_updated_at ON cart_items")
    op.execute("DROP TRIGGER IF EXISTS trigger_update_cart_updated_at ON commerce.cart_items")
    op.execute("DROP FUNCTION IF EXISTS update_cart_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS commerce.update_cart_updated_at()")

    op.execute("""
        CREATE FUNCTION commerce.update_cart_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE commerce.carts
            SET updated_at = NOW()
            WHERE id = NEW.cart_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_cart_updated_at
        AFTER INSERT OR UPDATE OR DELETE ON commerce.cart_items
        FOR EACH ROW
        EXECUTE FUNCTION commerce.update_cart_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_update_cart_updated_at ON commerce.cart_items")
    op.execute("DROP FUNCTION IF EXISTS commerce.update_cart_updated_at()")

    op.execute("""
        CREATE FUNCTION update_cart_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE carts
            SET updated_at = NOW()
            WHERE id = NEW.cart_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_cart_updated_at
        AFTER INSERT OR UPDATE OR DELETE ON commerce.cart_items
        FOR EACH ROW
        EXECUTE FUNCTION update_cart_updated_at();
    """)
