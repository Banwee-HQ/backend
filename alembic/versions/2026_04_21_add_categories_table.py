"""Add categories table and migrate products.category (string) to products.category_id (FK)

Revision ID: 2026_04_21_category
Revises: 2026_04_20_lockout
Create Date: 2026-04-21 00:00:00.000000
"""
import re
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from core.db import GUID
from core.utils.uuid_utils import uuid7

revision: str = '2026_04_21_category'
down_revision: Union[str, None] = '2026_04_20_lockout'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create categories table ---
    op.create_table(
        'categories',
        sa.Column('id', GUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=150), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_id', GUID(), sa.ForeignKey('catalog.categories.id'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        schema='catalog'
    )
    op.create_index('idx_categories_slug', 'categories', ['slug'], schema='catalog')
    op.create_index('idx_categories_parent_id', 'categories', ['parent_id'], schema='catalog')

    # --- Add the new FK column to products (nullable for now, backfilled below) ---
    op.add_column(
        'products',
        sa.Column('category_id', GUID(), sa.ForeignKey('catalog.categories.id'), nullable=True),
        schema='catalog'
    )

    # --- Backfill: turn each distinct products.category string into a Category row ---
    conn = op.get_bind()
    distinct_categories = conn.execute(
        sa.text("SELECT DISTINCT category FROM catalog.products WHERE category IS NOT NULL")
    ).fetchall()

    for (category_value,) in distinct_categories:
        if not category_value or not category_value.strip():
            continue

        slug = re.sub(r'[^a-z0-9-]', '', category_value.strip().lower().replace(' ', '-')) or 'category'
        name = category_value.strip().replace('-', ' ').replace('_', ' ').title()
        new_id = str(uuid7())

        conn.execute(
            sa.text(
                "INSERT INTO catalog.categories (id, name, slug, is_active, sort_order) "
                "VALUES (:id, :name, :slug, true, 0)"
            ),
            {"id": new_id, "name": name, "slug": slug}
        )
        conn.execute(
            sa.text("UPDATE catalog.products SET category_id = :cid WHERE category = :cat"),
            {"cid": new_id, "cat": category_value}
        )

    # --- Swap the index and drop the old string column ---
    op.drop_index('idx_products_category_status', table_name='products', schema='catalog')
    op.drop_column('products', 'category', schema='catalog')
    op.alter_column('products', 'category_id', nullable=False, schema='catalog')
    op.create_index('idx_products_category_status', 'products', ['category_id', 'product_status'], schema='catalog')


def downgrade() -> None:
    op.drop_index('idx_products_category_status', table_name='products', schema='catalog')
    op.add_column('products', sa.Column('category', sa.String(length=100), nullable=True), schema='catalog')

    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE catalog.products p SET category = c.slug "
        "FROM catalog.categories c WHERE p.category_id = c.id"
    ))

    op.alter_column('products', 'category', nullable=False, schema='catalog')
    op.create_index('idx_products_category_status', 'products', ['category', 'product_status'], schema='catalog')
    op.drop_column('products', 'category_id', schema='catalog')

    op.drop_index('idx_categories_parent_id', table_name='categories', schema='catalog')
    op.drop_index('idx_categories_slug', table_name='categories', schema='catalog')
    op.drop_table('categories', schema='catalog')
