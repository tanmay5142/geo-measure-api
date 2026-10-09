import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FileStatus(enum.StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=FileStatus.PROCESSING.value)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="Feature.feature_index",
    )


class Feature(Base):
    __tablename__ = "features"
    # The same file can't have two features with the same index.
    __table_args__ = (UniqueConstraint("file_id", "feature_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    feature_index: Mapped[int] = mapped_column(Integer)
    geometry_type: Mapped[str] = mapped_column(String(50))
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crs: Mapped[str] = mapped_column(String(100))
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    measurement_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    crs_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[UploadedFile] = relationship(back_populates="features")