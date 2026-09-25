"""drop contact messages

The contact form now opens the customer's own email app, so nothing is stored.

Revision ID: 9c4d2e7f1b30
Revises: 7b1e2c9d4a10
Create Date: 2026-09-25 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import core.db

# revision identifiers, used by Alembic.
revision: str = '9c4d2e7f1b30'
down_revision: Union[str, None] = '7b1e2c9d4a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('contact_messages', schema='system')
    op.execute('DROP TYPE IF EXISTS public.messagestatus')
    op.execute('DROP TYPE IF EXISTS public.messagepriority')


def downgrade() -> None:
    status = postgresql.ENUM('new', 'in_progress', 'resolved', 'closed', name='messagestatus')
    priority = postgresql.ENUM('low', 'medium', 'high', 'urgent', name='messagepriority')
    status.create(op.get_bind(), checkfirst=True)
    priority.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'contact_messages',
        sa.Column('id', core.db.GUID(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', postgresql.ENUM(name='messagestatus', create_type=False), nullable=False),
        sa.Column('priority', postgresql.ENUM(name='messagepriority', create_type=False), nullable=False),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('assigned_to', core.db.GUID(), nullable=True),
        sa.Column('created_at', core.db.UTCDateTime(), nullable=False),
        sa.Column('updated_at', core.db.UTCDateTime(), nullable=False),
        sa.Column('resolved_at', core.db.UTCDateTime(), nullable=True),
        schema='system',
    )
    for col in ('status', 'priority', 'email', 'assigned_to', 'created_at', 'resolved_at'):
        op.create_index(f'idx_contact_messages_{col}', 'contact_messages', [col], schema='system')
    op.create_index('idx_contact_messages_status_priority', 'contact_messages', ['status', 'priority'], schema='system')
    op.create_index('idx_contact_messages_status_created', 'contact_messages', ['status', 'created_at'], schema='system')
