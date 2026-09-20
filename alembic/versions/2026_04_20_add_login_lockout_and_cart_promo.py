"""Add login lockout fields and cart promocode

Revision ID: 2026_04_20_lockout
Revises: 2026_04_13_1353
Create Date: 2026-04-20 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from core.db import GUID

revision: str = '2026_04_20_lockout'
down_revision: Union[str, None] = '2026_04_13_1353'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Account brute-force lockout ---
    op.add_column(
        'users',
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        schema='accounts'
    )
    op.add_column(
        'users',
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        schema='accounts'
    )

    # --- Cart promocode ---
    op.add_column(
        'carts',
        sa.Column('promocode_id', GUID(), sa.ForeignKey('commerce.promocodes.id'), nullable=True),
        schema='commerce'
    )


def downgrade() -> None:
    op.drop_column('carts', 'promocode_id', schema='commerce')
    op.drop_column('users', 'locked_until', schema='accounts')
    op.drop_column('users', 'failed_login_attempts', schema='accounts')
