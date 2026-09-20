"""Add login lockout fields, user activity log table, and cart promocode

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

    # --- User activity/audit log ---
    op.create_table(
        'user_activity_logs',
        sa.Column('id', GUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('user_id', GUID(), sa.ForeignKey('accounts.users.id'), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('performed_by', GUID(), sa.ForeignKey('accounts.users.id'), nullable=True),
        sa.Column('activity_metadata', sa.JSON(), nullable=True),
        schema='accounts'
    )
    op.create_index('idx_user_activity_user_id', 'user_activity_logs', ['user_id'], schema='accounts')
    op.create_index('idx_user_activity_created_at', 'user_activity_logs', ['created_at'], schema='accounts')

    # --- Cart promocode ---
    op.add_column(
        'carts',
        sa.Column('promocode_id', GUID(), sa.ForeignKey('commerce.promocodes.id'), nullable=True),
        schema='commerce'
    )


def downgrade() -> None:
    op.drop_column('carts', 'promocode_id', schema='commerce')

    op.drop_index('idx_user_activity_created_at', table_name='user_activity_logs', schema='accounts')
    op.drop_index('idx_user_activity_user_id', table_name='user_activity_logs', schema='accounts')
    op.drop_table('user_activity_logs', schema='accounts')

    op.drop_column('users', 'locked_until', schema='accounts')
    op.drop_column('users', 'failed_login_attempts', schema='accounts')
