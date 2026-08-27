"""SQLAlchemy declarative base."""

from sqlalchemy.orm import declarative_base

# Create Base here to avoid circular imports
# This Base is also exported by app.database for consistency
Base = declarative_base()
