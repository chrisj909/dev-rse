"""
RSE ORM Model — properties table.
Primary record for each real estate parcel.
The canonical dedupe key is (county, parcel_id).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, Date, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Canonical dedupe key — sourced from county records.
    county: Mapped[str] = mapped_column(String(32), nullable=False, default="shelby", index=True)
    parcel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Address fields — normalized for matching, raw preserved for display
    address: Mapped[str | None] = mapped_column(String(255))          # normalized
    raw_address: Mapped[str | None] = mapped_column(String(255))      # original as-ingested
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2), default="AL")
    zip: Mapped[str | None] = mapped_column(String(10))

    # Owner fields
    owner_name: Mapped[str | None] = mapped_column(String(255))
    mailing_address: Mapped[str | None] = mapped_column(String(255))  # normalized
    raw_mailing_address: Mapped[str | None] = mapped_column(String(255))  # original

    # Property data
    last_sale_date: Mapped[datetime | None] = mapped_column(Date)
    assessed_value: Mapped[float | None] = mapped_column(Numeric(12, 2))

    # Coordinates (WGS84) — populated from ArcGIS geometry at ingest time
    lat: Mapped[float | None] = mapped_column(nullable=True)
    lng: Mapped[float | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    signal: Mapped["Signal"] = relationship(  # noqa: F821
        "Signal", back_populates="property", uselist=False, lazy="select"
    )
    scores: Mapped[list["Score"]] = relationship(  # noqa: F821
        "Score", back_populates="property", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Property county={self.county!r} parcel_id={self.parcel_id!r} address={self.address!r}>"
