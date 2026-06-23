"""add_escalation_question_to_transactions

Revision ID: a3f2c1d4e5b6
Revises: 91cfb0053f47
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f2c1d4e5b6'
down_revision: Union[str, None] = '91cfb0053f47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('escalation_question', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'escalation_question')
