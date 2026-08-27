"""SQLAlchemy model for the judge cache table."""

from sqlalchemy import JSON, Column, DateTime, Integer, String

from app.models.db_models import Base


class JudgeCacheDB(Base):
    __tablename__ = "judge_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    judge_id = Column(String(100), unique=True, nullable=False, index=True)
    judge_data = Column(JSON, nullable=False)  # Full judge profile as JSON
    opinions_data = Column(JSON, nullable=True)  # Cached opinions
    cached_at = Column(DateTime, nullable=False)
