"""Add response_time column to reading table

Revision ID: 002_add_response_time
Revises: 001_add_error_percentage
Create Date: 2026-01-20 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_response_time'
down_revision = '001_add_error_percentage'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding it
    # This makes migration idempotent and safe for existing databases
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if reading table exists
    if 'reading' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('reading')]
        
        if 'response_time' not in columns:
            # SQLite: Add column as nullable with default
            # SQLite will set default value for existing rows
            # Application code already handles None values (see webapp.py)
            op.add_column('reading', sa.Column('response_time', sa.Float(), nullable=True, server_default=sa.text('NULL')))
            # Note: We don't set a default value since response_time may not be available
            # for older firmware versions or API versions


def downgrade() -> None:
    # Check if column exists before removing it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'reading' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('reading')]
        
        if 'response_time' in columns:
            op.drop_column('reading', 'response_time')
