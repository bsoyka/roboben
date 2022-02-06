"""Database models."""

from beanie import Document


class User(Document):
    """A Discord user."""

    user_id: int
