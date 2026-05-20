"""add_message_count_to_chat_sessions

Revision ID: 9daf689c085d
Revises: ab327e2943d3
Create Date: 2026-01-22 20:07:57.304867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9daf689c085d'
down_revision: Union[str, Sequence[str], None] = 'ab327e2943d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
   
    # Add message_count column
    op.add_column('chat_sessions', sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'))
    
    # Create unique constraint
    op.create_unique_constraint('unique_user_session_per_day', 'chat_sessions', ['user_id', 'session_date'])
    
  
    
 


def downgrade() -> None:
    """Downgrade schema."""
    # Drop unique constraint
    op.drop_constraint('unique_user_session_per_day', 'chat_sessions', type_='unique')
    
    # Drop columns
    op.drop_column('chat_sessions', 'message_count')
    