"""drop_wishlist_tables

Revision ID: bb176c3d2411
Revises: 411bd14772a0
Create Date: 2026-04-11 22:49:04.211913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb176c3d2411'
down_revision: Union[str, None] = '411bd14772a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop wishlist tables if they exist
    op.execute('DROP TABLE IF EXISTS wishlist_items CASCADE')
    op.execute('DROP TABLE IF EXISTS wishlists CASCADE')


def downgrade() -> None:
    # Recreate wishlist tables (for rollback)
    op.execute('''
        CREATE TABLE IF NOT EXISTS wishlists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    op.execute('''
        CREATE TABLE IF NOT EXISTS wishlist_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wishlist_id UUID NOT NULL REFERENCES wishlists(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
            quantity INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
