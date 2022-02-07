"""Moderation and server logging."""

import asyncio
import difflib
import itertools
from datetime import timedelta
from typing import Optional

import arrow
import discord
from deepdiff import DeepDiff
from discord import Color, Message, Thread
from discord.abc import GuildChannel
from discord.ext.commands import Cog, Context
from discord.utils import escape_markdown
from discord_timestamps import TimestampType, format_timestamp
from loguru import logger

from bot.bot import RobobenBot
from bot.constants import Channels, Colors, Event, Roles, Server
from bot.utils.messages import format_user

GUILD_CHANNEL = discord.CategoryChannel | discord.TextChannel | discord.VoiceChannel

CHANNEL_CHANGES_UNSUPPORTED = ("permissions",)
CHANNEL_CHANGES_SUPPRESSED = ("_overwrites", "position")
ROLE_CHANGES_UNSUPPORTED = ("color", "permissions")

VOICE_STATE_ATTRIBUTES = {
    "channel.name": "Channel",
    "self_stream": "Streaming",
    "self_video": "Broadcasting",
}


class ModLog(Cog):
    """Logging for server events and staff actions."""

    # pylint: disable=too-many-public-methods

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self._ignored = {event: [] for event in Event}

        self._cached_edits = []

    def ignore(self, event: Event, *items: int) -> None:
        """Adds an event to ignored events to suppress log emission."""
        for item in items:
            if item not in self._ignored[event]:
                self._ignored[event].append(item)

    async def send_log_message(
        self,
        text: str,
        title: str,
        *,
        color: discord.Color | int = Color.blurple(),
        thumbnail: Optional[str | discord.Asset] = None,
        channel_id: int = Channels.mod_log,
        ping_everyone: bool = False,
        files: Optional[list[discord.File]] = None,
        content: Optional[str] = None,
        additional_embeds: Optional[list[discord.Embed]] = None,
        footer: Optional[str] = None,
    ) -> Context:
        """Generates a log embed and sends it to a logging channel."""
        await self.bot.wait_until_guild_available()
        # Truncate string directly here to avoid removing newlines
        embed = discord.Embed(description=text[:4093] + "..." if len(text) > 4096 else text, color=color)

        embed.set_author(name=title)

        if footer:
            embed.set_footer(text=footer)

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        if ping_everyone:
            if content:
                content = f"<@&{Roles.moderators}>\n{content}"
            else:
                content = f"<@&{Roles.moderators}>"

        # Truncate content to 2000 characters and append an ellipsis.
        if content and len(content) > 2000:
            content = content[: 2000 - 3] + "..."

        channel = self.bot.get_channel(channel_id)
        log_message = await channel.send(content=content, embed=embed, files=files)

        if additional_embeds:
            for additional_embed in additional_embeds:
                await channel.send(embed=additional_embed)

        return await self.bot.get_context(log_message)  # Optionally return for use with antispam

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GUILD_CHANNEL) -> None:
        """Logs channel create events to the mod log."""
        if channel.guild.id != Server.id:
            return

        if isinstance(channel, discord.CategoryChannel):
            title = "Category created"
            message = f"{channel.name} (`{channel.id}`)"
        elif isinstance(channel, discord.VoiceChannel):
            title = "Voice channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"
        else:
            title = "Text channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(message, title, color=Colors.green, channel_id=Channels.server_log)

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: GUILD_CHANNEL) -> None:
        """Logs channel delete events to the mod log."""
        if channel.guild.id != Server.id:
            return

        if isinstance(channel, discord.CategoryChannel):
            title = "Category deleted"
        elif isinstance(channel, discord.VoiceChannel):
            title = "Voice channel deleted"
        else:
            title = "Text channel deleted"

        if channel.category and not isinstance(channel, discord.CategoryChannel):
            message = f"{channel.category}/{channel.name} (`{channel.id}`)"
        else:
            message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(message, title, color=Colors.red, channel_id=Channels.server_log)

    @Cog.listener()
    async def on_guild_channel_update(self, before: GUILD_CHANNEL, after: GuildChannel) -> None:
        """Logs channel update events to the mod log."""
        if before.guild.id != Server.id:
            return

        if before.id in self._ignored[Event.guild_channel_update]:
            self._ignored[Event.guild_channel_update].remove(before.id)
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key in CHANNEL_CHANGES_SUPPRESSED:
                continue

            if key in CHANNEL_CHANGES_UNSUPPORTED:
                changes.append(f"**{key.title()}** updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                # Discord does not treat consecutive backticks ("``") as an empty inline code block, so the markdown
                # formatting is broken when `new` and/or `old` are empty values. "None" is used for these cases so
                # formatting is preserved.
                changes.append(f"**{key.title()}:** `{old or 'None'}` **→** `{new or 'None'}`")

            done.append(key)

        if not changes:
            return

        message = "\n".join(f"• {item}" for item in sorted(changes))

        if after.category:
            message = f"**{after.category}/#{after.name} (`{after.id}`)**\n{message}"
        else:
            message = f"**#{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(message, "Channel updated", channel_id=Channels.server_log)

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Logs role create events to the mod log."""
        if role.guild.id != Server.id:
            return

        await self.send_log_message(
            f"`{role.id}`",
            "Role created",
            color=Colors.green,
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Log role delete event to mod log."""
        if role.guild.id != Server.id:
            return

        await self.send_log_message(
            f"{role.name} (`{role.id}`)",
            "Role removed",
            color=Colors.red,
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Logs role update events to the mod log."""
        if before.guild.id != Server.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key == "color":
                continue

            if key in ROLE_CHANGES_UNSUPPORTED:
                changes.append(f"**{key.title()}** updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"**{key.title()}:** `{old}` **→** `{new}`")

            done.append(key)

        if not changes:
            return

        message = "\n".join(f"• {item}" for item in sorted(changes))

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(message, "Role updated", channel_id=Channels.server_log)

    @Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Logs guild update events to the mod log."""
        if before.id != Server.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done:
                continue

            new = value["new_value"]
            old = value["old_value"]

            changes.append(f"**{key.title()}:** `{old}` **→** `{new}`")

            done.append(key)

        if not changes:
            return

        message = "\n".join(f"• {item}" for item in sorted(changes))

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            message,
            "Guild updated",
            thumbnail=after.icon.with_static_format("png"),
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, member: discord.Member) -> None:
        """Logs ban events to the user log."""
        if guild.id != Server.id:
            return

        if member.id in self._ignored[Event.member_ban]:
            self._ignored[Event.member_ban].remove(member.id)
            return

        await self.send_log_message(
            format_user(member),
            "User banned",
            color=Colors.red,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log,
        )

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Logs member join events to the user log."""
        if member.guild.id != Server.id:
            return

        created_at = arrow.get(member.created_at)
        timestamp = format_timestamp(created_at, TimestampType.RELATIVE)

        message = format_user(member) + "\n\n**Account created:** " + timestamp

        age = arrow.utcnow() - created_at

        if age < timedelta(days=1):  # New user account!
            message = f"🐥 {message}"

        await self.send_log_message(
            message,
            "User joined",
            color=Colors.green,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log,
        )

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Logs member leave events to the user log."""
        if member.guild.id != Server.id:
            return

        if member.id in self._ignored[Event.member_remove]:
            self._ignored[Event.member_remove].remove(member.id)
            return

        await self.send_log_message(
            format_user(member),
            "User left",
            color=Colors.red,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log,
        )

    @Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, member: discord.User) -> None:
        """Logs member unban events to the mod log."""
        if guild.id != Server.id:
            return

        if member.id in self._ignored[Event.member_unban]:
            self._ignored[Event.member_unban].remove(member.id)
            return

        await self.send_log_message(
            format_user(member),
            "User unbanned",
            thumbnail=member.display_avatar.url,
        )

    @staticmethod
    def get_role_diff(before: list[discord.Role], after: list[discord.Role]) -> list[str]:
        """Returns a list of strings describing the roles added and removed."""
        before_roles = set(before)
        after_roles = set(after)

        changes = []

        for role in before_roles - after_roles:
            changes.append(f"**Role removed:** {role.name} (`{role.id}`)")

        for role in after_roles - before_roles:
            changes.append(f"**Role added:** {role.name} (`{role.id}`)")

        return changes

    async def log_member_timeout_change(self, member: discord.Member) -> None:
        """Logs member (un-)timeouts to the mod log.

        `member` is the member after the action occurred.
        """
        if member.timed_out:
            # Member was timed out
            timestamp = arrow.get(member.communication_disabled_until)

            short_datetime = format_timestamp(timestamp)
            relative_time = format_timestamp(timestamp, TimestampType.RELATIVE)

            message = f"{format_user(member)}\n\n" f"**Until:** {short_datetime} ({relative_time})"
            await self.send_log_message(
                message,
                "User timed out",
                color=Colors.red,
                thumbnail=member.display_avatar.url,
                channel_id=Channels.mod_log,
            )
        else:
            # Member was un-timed out
            await self.send_log_message(
                format_user(member),
                "User timeout ended manually",
                color=Colors.green,
                thumbnail=member.display_avatar.url,
                channel_id=Channels.mod_log,
            )

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Logs member update events to the user log."""
        if before.guild.id != Server.id:
            return

        if before.id in self._ignored[Event.member_update]:
            self._ignored[Event.member_update].remove(before.id)
            return

        if before.timed_out != after.timed_out:
            await self.log_member_timeout_change(after)
            return

        changes = self.get_role_diff(before.roles, after.roles)

        # The regex is a simple way to exclude all sequence and mapping types.
        diff = DeepDiff(before, after, exclude_regex_paths=r".*\[.*")

        # A type change seems to always take precedent over a value change. Furthermore, it will
        # include the value change along with the type change anyway. Therefore, it's OK to
        # "overwrite" values_changed; in practice there will never even be anything to overwrite.
        diff_values = {**diff.get("values_changed", {}), **diff.get("type_changes", {})}

        for attr, value in diff_values.items():
            if not attr:  # Not sure why, but it happens.
                continue

            attr = attr[5:]  # Remove "root." prefix.
            attr = attr.replace("_", " ").replace(".", " ").capitalize()

            new = value.get("new_value")
            old = value.get("old_value")

            changes.append(f"**{attr}:** `{old}` **→** `{new}`")

        if not changes:
            return

        message = "\n".join(f"• {item}" for item in sorted(changes))

        message = f"{format_user(after)}\n{message}"

        await self.send_log_message(
            message,
            "Member updated",
            thumbnail=after.display_avatar.url,
            channel_id=Channels.user_log,
        )

    def is_message_blocklisted(self, message: Message) -> bool:
        """Return true if the message is in a blocklisted thread or channel."""
        # Ignore bots or DMs
        if message.author.bot or not message.guild:
            return True

        return self.is_channel_ignored(message.channel.id)

    def is_channel_ignored(self, channel_id: int) -> bool:
        """
        Return True if the channel, or parent channel in the case of threads,
        passed should be ignored by modlog.

        Currently ignored channels are:
        1. Channels not in the guild we care about (constants.Guild.id).
        2. Channels that mods do not have view permissions to
        3. Channels in constants.Guild.modlog_blacklist
        """
        channel = self.bot.get_channel(channel_id)

        # Ignore not found channels, DMs, and messages outside of the main guild.
        if not channel or not hasattr(channel, "guild") or channel.guild.id != Server.id:
            return True

        # Look at the parent channel of a thread.
        if isinstance(channel, Thread):
            channel = channel.parent

        # Mod team doesn't have view permission to the channel.
        if not channel.permissions_for(channel.guild.get_role(Roles.moderators)).view_channel:
            return True

        return channel.id in Server.modlog_blocklist

    async def log_cached_deleted_message(self, message: discord.Message) -> None:
        """Logs the message's details to the message change log.

        This is called when a cached message is deleted.
        """
        channel = message.channel
        author = message.author

        if self.is_message_blocklisted(message):
            return

        if message.id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(message.id)
            return

        if channel.category:
            response = (
                f"**Author:** {format_user(author)}\n"
                f"**Channel:** {channel.category}/{channel.mention} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                f"[Jump to message]({message.jump_url})\n"
                "\n"
            )
        else:
            response = (
                f"**Author:** {format_user(author)}\n"
                f"**Channel:** {channel.mention} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                f"[Jump to message]({message.jump_url})\n"
                "\n"
            )

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        # Shorten the message content if necessary
        content = message.clean_content
        remaining_chars = 4090 - len(response)

        if len(content) > remaining_chars:
            ending = "\n\nMessage truncated."
            truncation_point = remaining_chars - len(ending)
            content = f"{content[:truncation_point]}...{ending}"

        response += f"{content}"

        await self.send_log_message(
            response,
            "Message deleted",
            color=Colors.red,
            channel_id=Channels.message_log,
        )

    async def log_uncached_deleted_message(self, event: discord.RawMessageDeleteEvent) -> None:
        """Logs the message's details to the message change log.

        This is called when a message absent from the cache is deleted. Hence,
        the message contents aren't logged.
        """
        await self.bot.wait_until_guild_available()
        if self.is_channel_ignored(event.channel_id):
            return

        if event.message_id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(event.message_id)
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            response = (
                f"**Channel:** {channel.category}/{channel.mention} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )
        else:
            response = (
                f"**Channel:** {channel.mention} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

        await self.send_log_message(
            response,
            "Message deleted",
            color=Colors.red,
            channel_id=Channels.message_log,
        )

    @Cog.listener()
    async def on_raw_message_delete(self, event: discord.RawMessageDeleteEvent) -> None:
        """Logs message deletions to the message change log."""
        if event.cached_message is not None:
            await self.log_cached_deleted_message(event.cached_message)
        else:
            await self.log_uncached_deleted_message(event)

    @Cog.listener()
    async def on_message_edit(self, msg_before: discord.Message, msg_after: discord.Message) -> None:
        """Logs message edit events to the message change log."""
        # pylint: disable=too-many-locals

        if self.is_message_blocklisted(msg_before):
            return

        self._cached_edits.append(msg_before.id)

        if msg_before.content == msg_after.content:
            return

        channel = msg_before.channel
        channel_name = f"{channel.category}/{channel.mention}" if channel.category else f"{channel.mention}"

        cleaned_contents = (escape_markdown(msg.clean_content).split() for msg in (msg_before, msg_after))
        # Getting the difference per words and group them by type - add, remove, same
        # Note that this is intended grouping without sorting
        diff = difflib.ndiff(*cleaned_contents)
        diff_groups = tuple(
            (diff_type, tuple(s[2:] for s in diff_words))
            for diff_type, diff_words in itertools.groupby(diff, key=lambda s: s[0])
        )

        content_before: list[str] = []
        content_after: list[str] = []

        for index, (diff_type, words) in enumerate(diff_groups):
            sub = " ".join(words)
            if diff_type == " ":
                if len(words) > 2:
                    sub = (
                        f"{words[0] if index > 0 else ''}"
                        " ... "
                        f"{words[-1] if index < len(diff_groups) - 1 else ''}"
                    )
                content_before.append(sub)
                content_after.append(sub)
            elif diff_type == "+":
                content_after.append(f"[{sub}](http://o.hi)")
            elif diff_type == "-":
                content_before.append(f"[{sub}](http://o.hi)")
        response = (
            f"**Author:** {format_user(msg_before.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{msg_before.id}`\n"
            "\n"
            f"**Before**:\n{' '.join(content_before)}\n"
            f"**After**:\n{' '.join(content_after)}\n"
            "\n"
            f"[Jump to message]({msg_after.jump_url})"
        )

        if msg_before.edited_at:
            # Message was previously edited, to assist with self-bot detection, use the edited_at
            # datetime as the baseline and create a human-readable delta between this edit event
            # and the last time the message was edited
            timestamp = arrow.get(msg_before.edited_at).humanize()
            footer = f"Last edited {timestamp}"
        else:
            # Message was not previously edited, use the created_at datetime as the baseline, no
            # delta calculation needed
            footer = None

        await self.send_log_message(
            response,
            "Message edited",
            channel_id=Channels.message_log,
            footer=footer,
        )

    @Cog.listener()
    async def on_raw_message_edit(self, event: discord.RawMessageUpdateEvent) -> None:
        """Logs raw message edit events to the message change log."""
        await self.bot.wait_until_guild_available()
        try:
            channel = self.bot.get_channel(int(event.data["channel_id"]))
            message = await channel.fetch_message(event.message_id)
        except discord.NotFound:  # Was deleted before we got the event
            return

        if self.is_message_blocklisted(message):
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_edits:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_edits.remove(event.message_id)
            return

        channel = message.channel
        channel_name = f"{channel.category}/{channel.mention}" if channel.category else f"{channel.mention}"

        before_response = (
            f"**Author:** {format_user(message.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{message.id}`\n"
            "\n"
            "This message was not cached, so the message content cannot be displayed."
        )

        after_response = (
            f"**Author:** {format_user(message.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{message.id}`\n"
            "\n"
            f"{message.clean_content}"
        )

        await self.send_log_message(
            before_response,
            "Message edited (Before)",
            channel_id=Channels.message_log,
        )

        await self.send_log_message(
            after_response,
            "Message edited (After)",
            channel_id=Channels.message_log,
        )

    @Cog.listener()
    async def on_thread_update(self, before: Thread, after: Thread) -> None:
        """Logs thread archiving, un-archiving and name edits."""
        if self.is_channel_ignored(after.id):
            logger.trace(f"Ignoring update of thread {after.name} ({after.id})")
            return

        if before.name != after.name:
            await self.send_log_message(
                (
                    f"Thread {after.mention} (`{after.id}`) from {after.parent.mention} (`{after.parent.id}`): "
                    f"`{before.name}` -> `{after.name}`"
                ),
                "Thread name edited",
                channel_id=Channels.server_log,
            )
            return

        if not before.archived and after.archived:
            color = Colors.red
            action = "archived"
        elif before.archived and not after.archived:
            color = Colors.green
            action = "un-archived"
        else:
            return

        await self.send_log_message(
            (
                f"Thread {after.mention} ({after.name}, `{after.id}`) from {after.parent.mention} "
                f"(`{after.parent.id}`) was {action}"
            ),
            f"Thread {action}",
            color=color,
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_thread_delete(self, thread: Thread) -> None:
        """Log thread deletion."""
        if self.is_channel_ignored(thread.id):
            logger.trace(f"Ignoring deletion of thread {thread.name} ({thread.id})")
            return

        await self.send_log_message(
            (
                f"Thread {thread.mention} ({thread.name}, `{thread.id}`) from {thread.parent.mention} "
                f"(`{thread.parent.id}`) deleted"
            ),
            "Thread deleted",
            color=Colors.red,
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_thread_join(self, thread: Thread) -> None:
        """Logs thread creation."""
        # If we are in the thread already we can most probably assume we already logged it?
        # We don't really have a better way of doing this since the API doesn't make any difference between the two
        if thread.me:
            return

        if self.is_channel_ignored(thread.id):
            logger.trace(f"Ignoring creation of thread {thread.name} ({thread.id})")
            return

        await self.send_log_message(
            (
                f"Thread {thread.mention} ({thread.name}, `{thread.id}`) from {thread.parent.mention} "
                f"(`{thread.parent.id}`) created"
            ),
            "Thread created",
            color=Colors.green,
            channel_id=Channels.server_log,
        )

    @Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Logs member voice state changes to the voice log channel."""
        if (
            member.guild.id != Server.id
            or (before.channel and self.is_channel_ignored(before.channel.id))
            or (after.channel and self.is_channel_ignored(after.channel.id))
        ):
            return

        if member.id in self._ignored[Event.voice_state_update]:
            self._ignored[Event.voice_state_update].remove(member.id)
            return

        # Exclude all channel attributes except the name.
        diff = DeepDiff(
            before,
            after,
            exclude_paths=("root.session_id", "root.afk"),
            exclude_regex_paths=r"root\.channel\.(?!name)",
        )

        # A type change seems to always take precedent over a value change. Furthermore, it will
        # include the value change along with the type change anyway. Therefore, it's OK to
        # "overwrite" values_changed; in practice there will never even be anything to overwrite.
        diff_values = {**diff.get("values_changed", {}), **diff.get("type_changes", {})}

        color = Colors.blurple
        changes = []

        for attr, values in diff_values.items():
            if not attr:  # Not sure why, but it happens.
                continue

            old = values["old_value"]
            new = values["new_value"]

            attr = attr[5:]  # Remove "root." prefix.
            attr = VOICE_STATE_ATTRIBUTES.get(attr, attr.replace("_", " ").capitalize())

            changes.append(f"**{attr}:** `{old}` **→** `{new}`")

            # Set the embed icon and color depending on which attribute changed.
            if any(name in attr for name in ("Channel", "deaf", "mute")):
                if new is None or new is True:
                    # Left a channel or was muted/deafened.
                    color = Colors.red
                elif old is None or old is True:
                    # Joined a channel or was unmuted/undeafened.
                    color = Colors.green

        if not changes:
            return

        message = "\n".join(f"• {item}" for item in sorted(changes))
        message = f"{format_user(member)}\n{message}"

        await self.send_log_message(
            message,
            "Voice state updated",
            color=color,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.voice_log,
        )


def setup(bot: RobobenBot) -> None:
    """Loads the mod log cog."""
    bot.add_cog(ModLog(bot))
