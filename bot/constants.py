"""Constant values for the bot."""

from os import environ


class Bot:
    """Bot-related settings."""

    prefix: str = environ.get("PREFIX", "!")
    token: str = environ["TOKEN"]


class Server:
    """Server-related constants."""

    invite: str = environ.get("INVITE", "4kssDaYNHp")
    id: int = int(environ.get("SERVER_ID", 854165018866483240))


class Roles:
    """Role IDs."""

    updates: int = int(environ.get("ROLE_UPDATES", 924753745210925170))


class Channels:
    """Channel IDs."""

    off_topic: int = int(environ.get("CHANNEL_OFF_TOPIC", 854165019444117509))
