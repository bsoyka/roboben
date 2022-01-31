"""Constant values for the bot."""

from pathlib import Path

from pydantic import BaseSettings, Field


class Bot(BaseSettings):
    """Bot-related settings."""

    prefix: str
    token: str


class Server(BaseSettings):
    """Server-related constants."""

    invite: str
    id: int = Field(..., env="SERVER_ID")


class Roles(BaseSettings):
    """Role IDs."""

    updates: int = Field(..., env="ROLE_UPDATES")


class Channels(BaseSettings):
    """Channel IDs."""

    off_topic: int = Field(..., env="OFF_TOPIC_ID")


kwargs = dict(_env_file=Path(__file__).parent.parent / ".env")

bot = Bot(**kwargs)
server = Server(**kwargs)
roles = Roles(**kwargs)
channels = Channels(**kwargs)
