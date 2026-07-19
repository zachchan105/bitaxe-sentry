"""Add fan, pool, and session diff columns to reading table

Revision ID: 003_add_fan_pool_data
Revises: 002_add_response_time
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '003_add_fan_pool_data'
down_revision = '002_add_response_time'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'reading' not in inspector.get_table_names():
        return

    columns = [col['name'] for col in inspector.get_columns('reading')]

    if 'fan_rpm' not in columns:
        op.add_column('reading', sa.Column('fan_rpm', sa.Integer(), nullable=True, server_default=sa.text('NULL')))
    if 'fan_pct' not in columns:
        op.add_column('reading', sa.Column('fan_pct', sa.Float(), nullable=True, server_default=sa.text('NULL')))
    if 'pool_url' not in columns:
        op.add_column('reading', sa.Column('pool_url', sa.String(), nullable=True, server_default=sa.text('NULL')))
    if 'using_fallback' not in columns:
        op.add_column('reading', sa.Column('using_fallback', sa.Boolean(), nullable=True, server_default=sa.text('NULL')))
    if 'best_session_diff' not in columns:
        op.add_column('reading', sa.Column('best_session_diff', sa.String(), nullable=True, server_default=sa.text('NULL')))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'reading' not in inspector.get_table_names():
        return

    columns = [col['name'] for col in inspector.get_columns('reading')]
    for col in ('fan_rpm', 'fan_pct', 'pool_url', 'using_fallback', 'best_session_diff'):
        if col in columns:
            op.drop_column('reading', col)
