"""Add cross-county owner pattern signals.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("out_of_state_owner", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("signals", sa.Column("corporate_owner", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("signals", "corporate_owner")
    op.drop_column("signals", "out_of_state_owner")