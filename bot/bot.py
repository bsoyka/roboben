"""Our custom instance of discord.ext.commands.Bot."""

from __future__ import annotations

from asyncio import get_event_loop

from discord import Activity, ActivityType, AllowedMentions, Intents
from discord.ext import commands
from loguru import logger

from bot import constants


class RobobenBot(commands.Bot):
    """Our custom instance of discord.ext.commands.Bot."""

    # pylint: disable=abstract-method,too-many-ancestors

    @classmethod
    def create(cls) -> RobobenBot:
        """Creates an instance of the Roboben bot."""
        loop = get_event_loop()
        activity = Activity(name=constants.bot.prefix + "help", type=ActivityType.watching)

        intents = Intents.all()

        return cls(
            loop=loop,
            command_prefix=commands.when_mentioned_or(constants.bot.prefix),
            activity=activity,
            case_insensitive=True,
            max_messages=10_000,
            allowed_mentions=AllowedMentions(everyone=False),
            intents=intents,
        )

    def load_extensions(self) -> None:
        """Loads all extensions."""
        # This is done here to avoid circular imports.
        from bot.utils.extensions import EXTENSIONS  # pylint: disable=import-outside-toplevel

        extensions = set(EXTENSIONS)  # Create a mutable copy.

        for extension in extensions:
            logger.debug(f"Loading extension {extension}")
            self.load_extension(extension)

    async def on_connect(self):
        """Logs when the bot connects to Discord."""
        logger.info(f"Connected to Discord as {self.user}")

    async def on_ready(self) -> None:
        """Logs when the bot is ready."""
        logger.info("Bot is ready")

    async def on_disconnect(self) -> None:
        """Logs when the bot disconnects from Discord."""
        logger.critical("Disconnected from Discord")

    async def on_resumed(self) -> None:
        """Logs when the bot resumes from a disconnection."""
        logger.info("Resumed Discord session")
