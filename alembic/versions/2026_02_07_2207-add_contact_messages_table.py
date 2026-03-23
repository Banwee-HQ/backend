"""add contact messages table

Revision ID: d4e8f9a1b2c3
Revises: b798a82bfa90
Create Date: 2026-02-07 22:07:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd4e8f9a1b2c3'
down_revision = 'b798a82bfa90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure uuid-ossp extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create enum types if they don't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagestatus AS ENUM ('new', 'in_progress', 'resolved', 'closed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagepriority AS ENUM ('low', 'medium', 'high', 'urgent');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create contact_messages table using raw SQL to avoid enum creation issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            status messagestatus NOT NULL DEFAULT 'new',
            priority messagepriority NOT NULL DEFAULT 'medium',
            admin_notes TEXT,
            assigned_to UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMP WITH TIME ZONE
        )
    """)
    
    # Create indexes for better query performance
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_messages_status ON contact_messages(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_messages_priority ON contact_messages(priority)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_messages_created_at ON contact_messages(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_messages_email ON contact_messages(email)")


def downgrade() -> None:
    # Drop table
    op.drop_table('contact_messages')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS messagepriority')
    op.execute('DROP TYPE IF EXISTS messagestatus')

