"""revoked tokens

Revision ID: 55c927cf90e1
Revises: 3695f6e711a9
Create Date: 2026-09-24 06:57:16.885686

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '55c927cf90e1'
down_revision: Union[str, None] = '3695f6e711a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Revoked JWT ids (logout / revoke); rows are purged once the token would have expired.
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('jti'),
        schema='accounts',
    )
    op.create_index('idx_revoked_tokens_expires_at', 'revoked_tokens', ['expires_at'], unique=False, schema='accounts')


def downgrade() -> None:
    op.drop_index('idx_revoked_tokens_expires_at', table_name='revoked_tokens', schema='accounts')
    op.drop_table('revoked_tokens', schema='accounts')
