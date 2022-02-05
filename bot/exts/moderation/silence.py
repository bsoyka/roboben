"""Channel silencing."""

from asyncio import AbstractEventLoop
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Optional, OrderedDict

from discord import TextChannel, Thread
from discord.ext import commands, tasks
from discord.ext.commands import Context
from discord.utils import MISSING
from loguru import logger

from bot.bot import RobobenBot
from bot.constants import MODERATION_ROLES, Channels, Roles, Server
from bot.converters import HushDurationConverter
from bot.errors import LockedResourceError
from bot.utils import scheduling
from bot.utils.lock import lock, lock_arg

LOCK_NAMESPACE = "silence"

MSG_SILENCE_FAIL = "Already silenced {channel}."
MSG_SILENCE_PERMANENT = "Silenced {channel} indefinitely."
MSG_SILENCE_SUCCESS = "Silenced {{channel}} for {duration} minute(s)."

MSG_UNSILENCE_FAIL = "Couldn't silence {channel}."
MSG_UNSILENCE_MANUAL = (
    "Didn't silence {channel} because the current overwrites were "
    "set manually or the cache was prematurely cleared. "
    "Please edit the overwrites manually to unsilence."
)
MSG_UNSILENCE_SUCCESS = "Unsilenced {channel}."


class SilenceNotifier(tasks.Loop):
    """Loop notifier for posting notices to `alert_channel` containing added channels."""

    def __init__(self, alert_channel: TextChannel, loop: AbstractEventLoop):
        super().__init__(
            self._notifier, seconds=1, minutes=0, hours=0, count=None, reconnect=True, loop=None, time=MISSING
        )
        self._silenced_channels = {}
        self._alert_channel = alert_channel
        self.loop = loop

    def add_channel(self, channel: TextChannel) -> None:
        """Add channel to `_silenced_channels` and start loop if not launched."""
        if not self._silenced_channels:
            self.start()
            logger.info("Starting notifier loop")
        self._silenced_channels[channel] = self._current_loop

    def remove_channel(self, channel: TextChannel) -> None:
        """Remove channel from `_silenced_channels` and stop loop if no channels remain."""
        with suppress(KeyError):
            del self._silenced_channels[channel]
            if not self._silenced_channels:
                self.stop()
                logger.info("Stopping notifier loop")

    async def _notifier(self) -> None:
        """Post notice of `_silenced_channels` with their silenced duration to `_alert_channel` periodically."""
        # Wait for 15 minutes between notices with pause at start of loop.
        if self._current_loop and not self._current_loop / 60 % 15:
            logger.debug(
                "Sending notice with channels: "
                ", ".join(f"#{channel} ({channel.id})" for channel in self._silenced_channels)
            )
            channels_text = ", ".join(
                f"{channel.mention} for {(self._current_loop-start)//60} min"
                for channel, start in self._silenced_channels.items()
            )
            await self._alert_channel.send(f"<@&{Roles.moderators}> currently silenced channels: {channels_text}")


async def _select_lock_channel(args: OrderedDict[str, any]) -> TextChannel:
    """Passes the channel to be silenced to the resource lock."""
    channel, _ = Silence.parse_silence_args(args["ctx"], args["duration_or_channel"], args["duration"])
    return channel


class Silence(commands.Cog):
    """Commands for stopping channel messages for `everyone` role in a channel."""

    # Maps muted channel IDs to their previous overwrites for send_message and add_reactions.
    previous_overwrites: dict[int, dict[str, bool | None]] = {}

    # Maps muted channel IDs to POSIX timestamps of when they'll be unsilenced.
    # A timestamp equal to -1 means it's indefinite.
    unsilence_timestamps: dict[int, int] = {}

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self.scheduler = scheduling.Scheduler("silence")

        self._init_task = scheduling.create_task(self._async_init(), event_loop=self.bot.loop)

    async def _async_init(self) -> None:
        """Set instance attributes once the guild is available and reschedule unsilences."""
        await self.bot.wait_until_guild_available()

        guild = self.bot.get_guild(Server.id)

        self._everyone_role = guild.default_role

        self._mod_alerts_channel = self.bot.get_channel(Channels.moderator_alerts)

        self.notifier = SilenceNotifier(self.bot.get_channel(Channels.mod_log), self.bot.loop)
        await self._reschedule()

    async def send_message(
        self, message: str, source_channel: TextChannel, target_channel: TextChannel, *, alert_target: bool = False
    ) -> None:
        """Helper function to send message confirmation to `source_channel`, and notification to `target_channel`."""
        # Reply to invocation channel
        source_reply = message
        if source_channel != target_channel:
            source_reply = source_reply.format(channel=target_channel.mention)
        else:
            source_reply = source_reply.format(channel="current channel")
        await source_channel.send(source_reply)

        # Reply to target channel
        if alert_target and source_channel != target_channel:
            await target_channel.send(message.format(channel="current channel"))

    @commands.command(aliases=("hush",))
    @lock(LOCK_NAMESPACE, _select_lock_channel, raise_error=True)
    async def silence(
        self,
        ctx: Context,
        duration_or_channel: TextChannel | HushDurationConverter = None,
        duration: HushDurationConverter = 10,
    ) -> None:
        """Silences the current channel for `duration` minutes or `forever`.

        Duration is capped at 15 minutes, passing forever makes the silence indefinite.
        Indefinitely silenced channels get added to a notifier which posts notices every 15 minutes from the start.

        Passing a voice channel will attempt to move members out of the channel and back to force sync permissions.
        If `kick` is True, members will not be added back to the voice channel, and members will be unable to rejoin.
        """
        await self._init_task
        channel, duration = self.parse_silence_args(ctx, duration_or_channel, duration)

        channel_info = f"#{channel} ({channel.id})"
        logger.debug(f"{ctx.author} is silencing channel {channel_info}.")

        # Since threads don't have specific overrides, we cannot silence them individually.
        # The parent channel has to be muted or the thread should be archived.
        if isinstance(channel, Thread):
            await ctx.send(":x: Threads cannot be silenced.")
            return

        if not await self._set_silence_overwrites(channel):
            logger.info(f"Tried to silence channel {channel_info} but the channel was already silenced")
            await self.send_message(MSG_SILENCE_FAIL, ctx.channel, channel, alert_target=False)
            return

        await self._schedule_unsilence(ctx, channel, duration)

        if duration is None:
            self.notifier.add_channel(channel)
            logger.info(f"Silenced {channel_info} indefinitely")
            await self.send_message(MSG_SILENCE_PERMANENT, ctx.channel, channel, alert_target=True)

        else:
            logger.info(f"Silenced {channel_info} for {duration} minute(s)")
            formatted_message = MSG_SILENCE_SUCCESS.format(duration=duration)
            await self.send_message(formatted_message, ctx.channel, channel, alert_target=True)

    @staticmethod
    def parse_silence_args(
        ctx: Context, duration_or_channel: TextChannel | int, duration: HushDurationConverter
    ) -> tuple[TextChannel, Optional[int]]:
        """Helper method to parse the arguments of the silence command."""
        if duration_or_channel:
            if isinstance(duration_or_channel, TextChannel):
                channel = duration_or_channel
            else:
                channel = ctx.channel
                duration = duration_or_channel
        else:
            channel = ctx.channel

        if duration == -1:
            duration = None

        return channel, duration

    async def _set_silence_overwrites(self, channel: TextChannel) -> bool:
        """Set silence permission overwrites for `channel` and return True if successful."""
        # Get the original channel overwrites
        role = self._everyone_role
        overwrite = channel.overwrites_for(role)
        prev_overwrites = dict(
            send_messages=overwrite.send_messages,
            add_reactions=overwrite.add_reactions,
            create_private_threads=overwrite.create_private_threads,
            create_public_threads=overwrite.create_public_threads,
            send_messages_in_threads=overwrite.send_messages_in_threads,
        )

        # Stop if channel was already silenced
        if channel.id in self.scheduler or all(val is False for val in prev_overwrites.values()):
            return False

        # Set new permissions, store
        overwrite.update(**dict.fromkeys(prev_overwrites, False))
        await channel.set_permissions(role, overwrite=overwrite)
        self.previous_overwrites[channel.id] = prev_overwrites

        return True

    async def _schedule_unsilence(self, ctx: Context, channel: TextChannel, duration: Optional[int]) -> None:
        """Schedule `ctx.channel` to be unsilenced if `duration` is not None."""
        if duration is None:
            self.unsilence_timestamps[channel.id] = -1
        else:
            self.scheduler.schedule_later(duration * 60, channel.id, ctx.invoke(self.unsilence, channel=channel))
            unsilence_time = datetime.now(tz=timezone.utc) + timedelta(minutes=duration)
            self.unsilence_timestamps[channel.id] = unsilence_time.timestamp()

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context, *, channel: TextChannel = None) -> None:
        """
        Unsilence the given channel if given, else the current one.

        If the channel was silenced indefinitely, notifications for the channel will stop.
        """
        await self._init_task
        if channel is None:
            channel = ctx.channel
        logger.debug(f"Unsilencing channel #{channel} from {ctx.author}'s command")
        await self._unsilence_wrapper(channel, ctx)

    @lock_arg(LOCK_NAMESPACE, "channel", raise_error=True)
    async def _unsilence_wrapper(self, channel: TextChannel, ctx: Optional[Context] = None) -> None:
        """
        Unsilence `channel` and send a success/failure message to ctx.channel.

        If ctx is None or not passed, `channel` is used in its place.
        If `channel` and ctx.channel are the same, only one message is sent.
        """
        msg_channel = channel
        if ctx is not None:
            msg_channel = ctx.channel

        if not await self._unsilence(channel):
            overwrite = channel.overwrites_for(self._everyone_role)
            if overwrite.send_messages is False or overwrite.add_reactions is False:
                await self.send_message(MSG_UNSILENCE_MANUAL, msg_channel, channel, alert_target=False)
            else:
                await self.send_message(MSG_UNSILENCE_FAIL, msg_channel, channel, alert_target=False)

        else:
            await self.send_message(MSG_UNSILENCE_SUCCESS, msg_channel, channel, alert_target=True)

    async def _unsilence(self, channel: TextChannel) -> bool:
        """
        Unsilence `channel`.

        If `channel` has a silence task scheduled or has its previous overwrites cached, unsilence
        it, cancel the task, and remove it from the notifier. Notify admins if it has a task but
        not cached overwrites.

        Return `True` if channel permissions were changed, `False` otherwise.
        """
        # Get stored overwrites, and return if channel is unsilenced
        prev_overwrites = self.previous_overwrites.get(channel.id)
        if channel.id not in self.scheduler and prev_overwrites is None:
            logger.info(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced")
            return False

        # Select the role based on channel type, and get current overwrites
        role = self._everyone_role
        overwrite = channel.overwrites_for(role)

        # Check if old overwrites were not stored
        if prev_overwrites is None:
            logger.info(f"Missing previous overwrites for #{channel} ({channel.id}); defaulting to None")
            overwrite.update(
                send_messages=None,
                add_reactions=None,
                create_private_threads=None,
                create_public_threads=None,
                send_messages_in_threads=None,
                speak=None,
                connect=None,
            )
        else:
            overwrite.update(**prev_overwrites)

        # Update Permissions
        await channel.set_permissions(role, overwrite=overwrite)

        logger.info(f"Unsilenced channel #{channel} ({channel.id})")

        self.scheduler.cancel(channel.id)
        self.notifier.remove_channel(channel)
        del self.previous_overwrites[channel.id]
        del self.unsilence_timestamps[channel.id]

        # Alert Admin team if old overwrites were not available
        if prev_overwrites is None:
            await self._mod_alerts_channel.send(
                f"<@&{Roles.admins}> Restored overwrites with default values after unsilencing "
                f"{channel.mention}. Please check that the `Send Messages` and `Add Reactions` "
                f"overwrites for {role.mention} are at their desired values."
            )

        return True

    async def _reschedule(self) -> None:
        """Reschedules unsilencing of active silences and add permanent ones to the notifier."""
        for channel_id, timestamp in self.unsilence_timestamps.items():
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                logger.info(f"Can't reschedule silence for {channel_id}: channel not found")
                continue

            if timestamp == -1:
                logger.info(f"Adding permanent silence for #{channel} ({channel.id}) to the notifier")
                self.notifier.add_channel(channel)
                continue

            time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            delta = (time - datetime.now(tz=timezone.utc)).total_seconds()
            if delta <= 0:
                # Suppress the error since it's not being invoked by a user via the command.
                with suppress(LockedResourceError):
                    await self._unsilence_wrapper(channel)
            else:
                logger.info(f"Rescheduling silence for #{channel} ({channel.id})")
                self.scheduler.schedule_later(delta, channel_id, self._unsilence_wrapper(channel))

    def cog_unload(self) -> None:
        """Cancels the init task and scheduled tasks."""
        # It's important to wait for _init_task (specifically for _reschedule) to be cancelled
        # before cancelling scheduled tasks. Otherwise, it's possible for _reschedule to schedule
        # more tasks after cancel_all has finished, despite _init_task.cancel being called first.
        # This is cause cancel() on its own doesn't block until the task is cancelled.
        self._init_task.cancel()
        self._init_task.add_done_callback(lambda _: self.scheduler.cancel_all())

    async def cog_check(self, ctx: Context) -> bool:
        """Only allows moderators to invoke the commands in this cog."""
        # pylint: disable=invalid-overridden-method

        return await commands.has_any_role(*MODERATION_ROLES).predicate(ctx)


def setup(bot: RobobenBot) -> None:
    """Loads the Silence cog."""
    bot.add_cog(Silence(bot))
