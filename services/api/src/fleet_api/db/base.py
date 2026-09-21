from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for future tenant-owned SQLAlchemy models."""

