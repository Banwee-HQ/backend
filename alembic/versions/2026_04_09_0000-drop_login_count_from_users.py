"""drop_login_count_from_users

Revision ID: drop_login_count
Revises: 5a2f22565cbc
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'drop_login_count'
down_revision: Union[str, None] = '5a2f22565cbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'login_count')


def downgrade() -> None:
    op.add_column('users', sa.Column('login_count', sa.Integer(), nullable=True))
