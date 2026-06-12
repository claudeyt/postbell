from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class LanguageSchedule(Base):
    __tablename__ = "language_schedules"

    language_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    time_brt: Mapped[str] = mapped_column(String(5), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
