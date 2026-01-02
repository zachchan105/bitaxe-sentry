"""Add error_percentage column to reading table

Revision ID: 001_add_error_percentage
Revises: 
Create Date: 2026-01-02 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_error_percentage'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding it
    # This makes the migration idempotent and safe for existing databases
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if reading table exists
    if 'reading' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('reading')]
        
        if 'error_percentage' not in columns:
            # SQLite: Add column as nullable with default
            # SQLite will set default value for existing rows
            # Application code already handles None values (see webapp.py)
            op.add_column('reading', sa.Column('error_percentage', sa.Float(), nullable=True, server_default=sa.text('0.0')))
            # Update any existing NULL values (safety check)
            op.execute("UPDATE reading SET error_percentage = 0.0 WHERE error_percentage IS NULL")


def downgrade() -> None:
    # Check if column exists before removing it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'reading' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('reading')]
        
        if 'error_percentage' in columns:
            op.drop_column('reading', 'error_percentage')

