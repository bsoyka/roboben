"""Database models."""

from datetime import datetime
from typing import Optional

from beanie import Document


class User(Document):
    """A Discord user."""

    user_id: int


class Infraction(Document):
    """A user infraction."""

    type: str
    reason: Optional[str]
    expires_at: Optional[datetime]

    user: int
    actor: int

    sent_dm: bool = False
