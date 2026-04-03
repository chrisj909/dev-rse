"""Initial schema — properties, signals, scores

Revision ID: 0001
Revises:
Create Date: 2026-04-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── properties ─────────────────────────────────────────────────────────
    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("parcel_id", sa.String(64), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("raw_address", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=False, server_default="AL"),
        sa.Column("zip", sa.String(10), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("mailing_address", sa.String(255), nullable=True),
        sa.Column("raw_mailing_address", sa.String(255), nullable=True),
        sa.Column("last_sale_date", sa.Date(), nullable=True),
        sa.Column("assessed_value", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_properties_parcel_id", "properties", ["parcel_id"])
    op.create_index("ix_properties_parcel_id", "properties", ["parcel_id"])

    # ── signals ────────────────────────────────────────────────────────────
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("absentee_owner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("long_term_owner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tax_delinquent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pre_foreclosure", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("probate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("eviction", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("code_violation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_signals_property_id", "signals", ["property_id"])
    op.create_index("ix_signals_property_id", "signals", ["property_id"])

    # ── scores ─────────────────────────────────────────────────────────────
    op.create_table(
        "scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rank", sa.String(1), nullable=False, server_default="C"),
        sa.Column(
            "reason",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("scoring_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_scores_property_id", "scores", ["property_id"])
    op.create_index("ix_scores_property_id", "scores", ["property_id"])


def downgrade() -> None:
    op.drop_table("scores")
    op.drop_table("signals")
    op.drop_table("properties")
