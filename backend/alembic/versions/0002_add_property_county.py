"""Add county dimension to properties dedupe key.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("county", sa.String(length=32), nullable=True, server_default="shelby"),
    )
    op.execute("UPDATE properties SET county = 'shelby' WHERE county IS NULL OR county = ''")
    op.alter_column("properties", "county", nullable=False, server_default="shelby")

    op.drop_constraint("uq_properties_parcel_id", "properties", type_="unique")
    op.drop_index("ix_properties_parcel_id", table_name="properties")
    op.create_index("ix_properties_county", "properties", ["county"])
    op.create_index("ix_properties_county_parcel_id", "properties", ["county", "parcel_id"])
    op.create_unique_constraint("uq_properties_county_parcel_id", "properties", ["county", "parcel_id"])


def downgrade() -> None:
    op.drop_constraint("uq_properties_county_parcel_id", "properties", type_="unique")
    op.drop_index("ix_properties_county_parcel_id", table_name="properties")
    op.drop_index("ix_properties_county", table_name="properties")
    op.create_index("ix_properties_parcel_id", "properties", ["parcel_id"])
    op.create_unique_constraint("uq_properties_parcel_id", "properties", ["parcel_id"])
    op.drop_column("properties", "county")