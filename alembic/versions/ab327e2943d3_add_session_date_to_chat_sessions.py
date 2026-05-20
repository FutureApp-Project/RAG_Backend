"""add_session_date_to_chat_sessions

Revision ID: ab327e2943d3
Revises: f66623cc91c7
Create Date: 2026-01-22 19:58:32.957804

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab327e2943d3'
down_revision: Union[str, Sequence[str], None] = 'f66623cc91c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add session_date column
    op.add_column('chat_sessions', sa.Column('session_date', sa.Date(), nullable=True))
    
    # Set session_date from created_at for existing records
    op.execute("UPDATE chat_sessions SET session_date = DATE(created_at)")

def downgrade():
    op.drop_column('chat_sessions', 'session_date')