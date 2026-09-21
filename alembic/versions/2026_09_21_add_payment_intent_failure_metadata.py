"""Add payment_intents.failure_metadata - retry()/failure_status()/failed_payments()
in services/commerce/payments.py all read/write this column, but it was never
added to the table, so every call to those three live endpoints crashed with
AttributeError.

Revision ID: 2026_09_21_pifailmeta
Revises: 2026_04_22_dropqty
Create Date: 2026-09-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '2026_09_21_pifailmeta'
down_revision: Union[str, None] = '2026_04_22_dropqty'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payment_intents', sa.Column('failure_metadata', sa.JSON(), nullable=True), schema='commerce')


def downgrade() -> None:
    op.drop_column('payment_intents', 'failure_metadata', schema='commerce')
