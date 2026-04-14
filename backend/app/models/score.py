"""
RSE ORM Model — scores table
Computed score + rank for each property and scoring mode.
scoring_version links back to the weight config that produced this score.
reason is a list of active signal tag strings (e.g. ["absentee_owner", "long_term_owner"]).
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("property_id", "scoring_mode", name="uq_scores_property_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rank: Mapped[str] = mapped_column(String(1), nullable=False, default="C")  # A | B | C
    reason: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    scoring_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="broad", index=True)
    scoring_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v3")

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship(  # noqa: F821
        "Property", back_populates="scores"
    )

    def __repr__(self) -> str:
        return (
            f"<Score property_id={self.property_id} "
            f"mode={self.scoring_mode!r} score={self.score} rank={self.rank!r} version={self.scoring_version!r}>"
        )
