"""Add reasoning_details to messages

Revision ID: c0bbf8dd65d6
Revises: ca6d892958f9
Create Date: 2026-08-07 06:20:01.576468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0bbf8dd65d6'
down_revision: Union[str, Sequence[str], None] = 'ca6d892958f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('reasoning_details', sa.JSON(), nullable=True))

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'reasoning_details')
