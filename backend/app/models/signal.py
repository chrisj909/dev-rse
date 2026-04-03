"""
RSE ORM Model — signals table
One row per property. Bool flags for each signal type.
Placeholder signals (pre_foreclosure, probate, eviction, code_violation)
are wired as False until their data sources are connected (Sprint 5+).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Active signals (MVP — computed from property/tax data) ────────────
    absentee_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    long_term_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Placeholder signals (wired in Sprint 5+) ─────────────────────────
    tax_delinquent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pre_foreclosure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    probate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eviction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    code_violation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
    property: Mapped["Property"] = relationship(  # noqa: F821
        "Property", back_populates="signal"
    )

    def __repr__(self) -> str:
        flags = [k for k, v in self.__dict__.items() if isinstance(v, bool) and v]
        return f"<Signal property_id={self.property_id} active={flags}>"
