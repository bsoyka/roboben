"""Our custom instance of discord.ext.commands.Bot."""

from __future__ import annotations

from asyncio import Event, get_event_loop
from typing import Optional

import aiohttp
from beanie import init_beanie
from discord import Activity, ActivityType, AllowedMentions, Guild, HTTPException, Intents
from discord.ext import commands
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from bot import constants, models
from bot.utils.scheduling import create_task


class RobobenBot(commands.Bot):
    """Our custom instance of discord.ext.commands.Bot."""

    # pylint: disable=abstract-method,too-many-ancestors

    def __init__(self, *args, http_session: aiohttp.ClientSession, **kwargs):
        super().__init__(*args, **kwargs)

        self.http_session = http_session
        self.database: Optional[AsyncIOMotorClient] = None

        self._guild_available = Event()

        self._db_init_task = create_task(self._init_db(), event_loop=self.loop)

    async def _init_db(self) -> None:
        """Initializes the database."""
        self.database = AsyncIOMotorClient(constants.Database.uri)

        await init_beanie(self.database["roboben"], document_models=[models.User])

        logger.info("Database initialized")

    @classmethod
    def create(cls) -> RobobenBot:
        """Creates an instance of the Roboben bot."""
        loop = get_event_loop()
        activity = Activity(name=constants.Bot.prefix + "help", type=ActivityType.watching)

        intents = Intents.all()

        return cls(
            http_session=aiohttp.ClientSession(loop=loop),
            loop=loop,
            command_prefix=commands.when_mentioned_or(constants.Bot.prefix),
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

    async def on_guild_available(self, guild: Guild) -> None:
        """
        Set the internal guild available event when constants.Guild.id becomes available.
        If the cache appears to still be empty (no members, no channels, or no roles), the event
        will not be set.
        """
        if guild.id != constants.Server.id:
            return

        if not guild.roles or not guild.members or not guild.channels:
            msg = "Guild available event was dispatched but the cache appears to still be empty!"
            logger.warning(msg)

            try:
                webhook = await self.fetch_webhook(constants.Webhooks.dev_log)
            except HTTPException as error:
                logger.error(f"Failed to fetch webhook to send empty cache warning: status {error.status}")
            else:
                await webhook.send(f"<@&{constants.Roles.admins}> {msg}")

            return

        self._guild_available.set()

    async def on_guild_unavailable(self, guild: Guild) -> None:
        """Clear the internal guild available event when constants.Guild.id becomes unavailable."""
        if guild.id != constants.Server.id:
            return

        self._guild_available.clear()

    async def wait_until_guild_available(self) -> None:
        """Waits until the guild is available and the cache is ready.

        The on_ready event is inadequate because it only waits 2 seconds for a
        GUILD_CREATE gateway event before giving up and thus not populating the
        cache for unavailable guilds.
        """
        await self._guild_available.wait()

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
