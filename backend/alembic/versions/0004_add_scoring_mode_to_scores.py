"""Add scoring mode to scores and allow one score per mode.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scores",
        sa.Column("scoring_mode", sa.String(length=32), nullable=False, server_default="broad"),
    )
    op.execute("UPDATE scores SET scoring_mode = 'broad' WHERE scoring_mode IS NULL")
    op.drop_constraint("uq_scores_property_id", "scores", type_="unique")
    op.create_unique_constraint(
        "uq_scores_property_mode",
        "scores",
        ["property_id", "scoring_mode"],
    )
    op.create_index("ix_scores_scoring_mode", "scores", ["scoring_mode"])


def downgrade() -> None:
    op.drop_index("ix_scores_scoring_mode", table_name="scores")
    op.drop_constraint("uq_scores_property_mode", "scores", type_="unique")
    op.create_unique_constraint("uq_scores_property_id", "scores", ["property_id"])
    op.drop_column("scores", "scoring_mode")