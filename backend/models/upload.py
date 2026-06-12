from datetime import datetime

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[str] = mapped_column(String, default="")
    privacy: Mapped[str] = mapped_column(String, default="private")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_method: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    youtube_video_id: Mapped[str | None] = mapped_column(String, nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String, nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_error: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    thumbnail_error: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    comment_error: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    quota_cost: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    channel: Mapped["Channel"] = relationship(back_populates="uploads")
