"""Change age to date_of_birth

Revision ID: change_age_to_date_of_birth
Revises: 
Create Date: 2026-04-12 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'change_age_to_date_of_birth'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old index on age if it exists
    try:
        op.drop_index('idx_users_age', table_name='users', schema='accounts')
    except Exception:
        pass  # Index might not exist
    
    # Drop the age column
    try:
        op.drop_column('users', 'age', schema='accounts')
    except Exception:
        pass  # Column might not exist
    
    # Add the date_of_birth column
    op.add_column('users', sa.Column('date_of_birth', sa.DateTime(timezone=True), nullable=True), schema='accounts')
    
    # Create index on date_of_birth
    op.create_index('idx_users_date_of_birth', 'users', ['date_of_birth'], schema='accounts')


def downgrade() -> None:
    # Reverse the changes
    op.drop_index('idx_users_date_of_birth', table_name='users', schema='accounts')
    op.drop_column('users', 'date_of_birth', schema='accounts')
    op.add_column('users', sa.Column('age', sa.Integer(), nullable=True), schema='accounts')
    op.create_index('idx_users_age', 'users', ['age'], schema='accounts')
