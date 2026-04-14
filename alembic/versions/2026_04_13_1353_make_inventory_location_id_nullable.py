"""make inventory.location_id nullable

Revision ID: 2026_04_13_1353
Revises: 
Create Date: 2026-04-13 13:53:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2026_04_13_1353'
down_revision = 'remove_delivery_type_sub'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'inventory',
        'location_id',
        existing_type=postgresql.UUID(),
        nullable=True
    )


def downgrade():
    op.alter_column(
        'inventory',
        'location_id',
        existing_type=postgresql.UUID(),
        nullable=False
    )
