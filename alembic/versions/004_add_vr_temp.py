"""Add vr_temp column to reading table

Revision ID: 004_add_vr_temp
Revises: 003_add_fan_pool_data
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '004_add_vr_temp'
down_revision = '003_add_fan_pool_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'reading' not in inspector.get_table_names():
        return

    columns = [col['name'] for col in inspector.get_columns('reading')]

    if 'vr_temp' not in columns:
        op.add_column('reading', sa.Column('vr_temp', sa.Float(), nullable=True, server_default=sa.text('NULL')))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'reading' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('reading')]
        if 'vr_temp' in columns:
            op.drop_column('reading', 'vr_temp')
