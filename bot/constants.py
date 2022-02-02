"""Constant values for the bot."""

from enum import Enum
from os import environ

from discord import Color


class Bot:
    """Bot-related settings."""

    prefix: str = environ.get("PREFIX", "!")
    token: str = environ["TOKEN"]


class Server:
    """Server-related constants."""

    invite: str = environ.get("INVITE", "4kssDaYNHp")
    id: int = int(environ.get("SERVER_ID", 854165018866483240))

    modlog_blocklist: set[int] = set(
        map(int, environ.get("MODLOG_BLOCKLIST", "854357156861968464,938087670205251605").split(","))
    )


class Roles:
    """Role IDs."""

    moderators: int = int(environ.get("ROLE_MODERATORS", 926638942361628721))
    admins: int = int(environ.get("ROLE_ADMINS", 938280082231922749))

    updates: int = int(environ.get("ROLE_UPDATES", 924753745210925170))


class Channels:
    """Channel IDs."""

    off_topic: int = int(environ.get("CHANNEL_OFF_TOPIC", 854165019444117509))

    mod_log: int = int(environ.get("CHANNEL_MOD_LOG", 854357156861968464))
    user_log: int = int(environ.get("CHANNEL_USER_LOG", 938087637720367135))
    message_log: int = int(environ.get("CHANNEL_MESSAGE_LOG", 938087670205251605))
    voice_log: int = int(environ.get("CHANNEL_VOICE_LOG", 938087681206935582))
    server_log: int = int(environ.get("CHANNEL_SERVER_LOG", 938087710386696233))


def _get_color_env(name: str, default: tuple[int, int, int]) -> Color:
    """Gets an RGB color value from the environment."""
    color_str = environ.get(name, None)

    rgb = default if color_str is None else tuple(map(int, color_str.split(",")))

    return Color.from_rgb(*rgb)


class Colors:
    """Color objects."""

    red: Color = _get_color_env("COLOR_RED", (237, 66, 69))
    green: Color = _get_color_env("COLOR_GREEN", (87, 242, 135))
    blurple: Color = _get_color_env("COLOR_BLURPLE", (88, 101, 242))


class Webhooks:
    """Webhook IDs."""

    dev_log: int = int(environ.get("WEBHOOK_DEV_LOG", 938278912339890208))


class Event(Enum):
    """Event names.

    This does not include every event (for example, raw events aren't here), but
    only events used in the mod log for now.
    """

    # pylint: disable=invalid-name

    guild_channel_create = "guild_channel_create"
    guild_channel_delete = "guild_channel_delete"
    guild_channel_update = "guild_channel_update"
    guild_role_create = "guild_role_create"
    guild_role_delete = "guild_role_delete"
    guild_role_update = "guild_role_update"
    guild_update = "guild_update"

    member_join = "member_join"
    member_remove = "member_remove"
    member_ban = "member_ban"
    member_unban = "member_unban"
    member_update = "member_update"

    message_delete = "message_delete"
    message_edit = "message_edit"

    voice_state_update = "voice_state_update"
