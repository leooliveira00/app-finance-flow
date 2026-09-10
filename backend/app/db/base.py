"""Base declarativa do SQLAlchemy 2.0 para os modelos ORM."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base comum de todos os modelos."""
