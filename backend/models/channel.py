from datetime import datetime

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String, nullable=False)
    alias: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str] = mapped_column(String, nullable=False, default="")
    default_description: Mapped[str] = mapped_column(String, default="", nullable=False)
    default_comment: Mapped[str] = mapped_column(String, default="", nullable=False)
    default_tags: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_groups.id", ondelete="SET NULL"), nullable=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custom_schedule_time: Mapped[str | None] = mapped_column(String(5), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped["Account"] = relationship(back_populates="channels")
    uploads: Mapped[list["Upload"]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    group = relationship("ChannelGroup", back_populates="channels")
