"""Infractions and related utilities."""

import textwrap
from typing import Awaitable, Optional

import arrow
import disnake
from discord_timestamps import TimestampType, format_timestamp
from disnake import Embed, Member
from disnake.ext.commands import Cog, Context, command, has_any_role
from loguru import logger

from bot.bot import RobobenBot
from bot.constants import MODERATION_ROLES, Colors, Event
from bot.converters import Duration
from bot.models import Infraction
from bot.utils.messages import format_user

SUPPORTED_INFRACTIONS = {}

INFRACTION_TITLE = "Please review our rules"
INFRACTION_APPEAL_SERVER_FOOTER = "\nTo appeal this infraction, email appeals@bsoyka.me."
INFRACTION_APPEAL_MODMAIL_FOOTER = (
    "\nIf you would like to discuss or appeal this infraction, send a message to the ModMail bot."
)
INFRACTION_AUTHOR_NAME = "Infraction information"

LONGEST_EXTRAS = max(len(INFRACTION_APPEAL_SERVER_FOOTER), len(INFRACTION_APPEAL_MODMAIL_FOOTER))

INFRACTION_DESCRIPTION_TEMPLATE = "**Type:** {type}\n**Expires:** {expires}\n**Reason:** {reason}\n"


class Infractions(Cog):
    """Infractions and related utilities."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @property
    def mod_log(self) -> Cog:
        """Gets the currently loaded mod log cog instance."""
        return self.bot.get_cog("ModLog")

    @staticmethod
    async def send_private_embed(user: Member, embed: Embed) -> bool:
        """Sends an embed to a user's DMs and returns whether the DM was successful."""
        try:
            await user.send(embed=embed)
            return True
        except (disnake.HTTPException, disnake.Forbidden, disnake.NotFound):
            logger.debug(
                f"Infraction-related information could not be sent to user {user} ({user.id}). "
                "The user either could not be retrieved or probably disabled their DMs."
            )
            return False

    async def notify_infraction(
        self,
        user: Member,
        infraction: Infraction,
        infraction_type: str,
        reason: Optional[str] = None,
        expiry: Optional[str] = None,
    ) -> bool:
        """Notifies a user of an infraction.

        Returns whether the DM succeeded.
        """
        # pylint: disable=too-many-arguments

        logger.trace(f"Sending {user} a DM about their {infraction_type} infraction.")

        text = INFRACTION_DESCRIPTION_TEMPLATE.format(
            type=infraction_type, expires=expiry or "N/A", reason=reason or "No reason provided."
        )

        # For case when other fields than reason is too long and this reach limit, then force-shorten string
        if len(text) > 4096 - LONGEST_EXTRAS:
            text = f"{text[:4093 - LONGEST_EXTRAS]}..."

        text += (
            INFRACTION_APPEAL_SERVER_FOOTER if infraction_type.lower() == "ban" else INFRACTION_APPEAL_MODMAIL_FOOTER
        )

        embed = disnake.Embed(description=text, colour=Colors.red)

        embed.set_author(name=INFRACTION_AUTHOR_NAME)
        embed.title = INFRACTION_TITLE

        dm_sent = await self.send_private_embed(user, embed)
        if dm_sent:
            infraction.sent_dm = True
            await infraction.save()

            logger.debug(f"Updated infraction #{infraction.id} dm_sent field to True.")

        return dm_sent

    async def apply_infraction(
        self,
        ctx: Context,
        infraction: Infraction,
        user: Member,
        action_coro: Optional[Awaitable] = None,
        user_reason: Optional[str] = None,
        additional_info: str = "",
    ) -> bool:
        """Applies an infraction to the user, logs the infraction, and
        optionally notifies the user.

        `action_coro`, if not provided, will result in the infraction not getting scheduled for deletion.
        `user_reason`, if provided, will be sent to the user in place of the infraction reason.
        `additional_info` will be attached to the text field in the mod-log embed.

        Returns whether the infraction succeeded.
        """
        # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements

        await infraction.save()

        infraction_type = infraction.type
        reason = infraction.reason
        timestamp = arrow.get(infraction.expires_at)
        expiry = (
            f"{format_timestamp(timestamp, TimestampType.LONG_DATETIME)}"
            f" ({format_timestamp(timestamp, TimestampType.RELATIVE)})"
            if infraction.expires_at
            else None
        )
        id_ = str(infraction.id)

        if user_reason is None:
            user_reason = reason

        logger.trace(f"Applying {infraction_type} infraction #{id_} to {user}.")

        # Default values for the confirmation message and mod log.
        confirm_msg = ":ok_hand: applied"

        # Specifying an expiry for a note or warning makes no sense.
        if infraction_type in {"note", "warning"}:
            expiry_msg = ""
        else:
            expiry_msg = f" until {expiry}" if expiry else " permanently"

        expiry_log_text = f"\nExpires: {expiry}" if expiry else ""
        log_title = "applied"
        log_content = None
        failed = False

        # DM the user about the infraction.
        dm_result = ":warning: "
        dm_log_text = "\nDM: **Failed**"

        # Accordingly, update whether the user was successfully notified via DM.
        if await self.notify_infraction(
            user, infraction, infraction_type.replace("_", " ").title(), user_reason, expiry
        ):
            dm_result = ":incoming_envelope: "
            dm_log_text = "\nDM: Sent"

        end_msg = ""

        if infraction.actor == self.bot.user.id:
            logger.trace(f"Infraction #{id_} actor is bot; including the reason in the confirmation message.")
            if reason:
                end_msg = f" (reason: {textwrap.shorten(reason, width=1500, placeholder='...')})"

        # Execute the necessary actions to apply the infraction on Discord.
        if action_coro:
            logger.trace(f"Awaiting the infraction #{id_} application action coroutine.")

            try:
                await action_coro
            except disnake.HTTPException as error:
                # Accordingly, display that applying the infraction failed.
                confirm_msg = ":x: failed to apply"
                expiry_msg = ""
                log_content = ctx.author.mention
                log_title = "failed to apply"

                log_msg = f"Failed to apply {' '.join(infraction_type.split('_'))} infraction #{id_} to {user}"

                if isinstance(error, disnake.Forbidden):
                    logger.warning(f"{log_msg}: bot lacks permissions.")
                elif error.code == 10007 or error.status == 404:
                    logger.info(f"Can't apply {infraction.type} to user {infraction.user} because user left the guild.")
                else:
                    logger.exception(log_msg)

                failed = True

        if failed:
            logger.trace(f"Trying to delete infraction {id_} from database because applying infraction failed.")

            try:
                await infraction.delete()
            except Exception:  # pylint: disable=broad-except
                confirm_msg += " and failed to delete"
                log_title += " and failed to delete"
                logger.exception(f"Deletion of {infraction_type} infraction #{id_} failed.")
            infraction_message = ""
        else:
            infraction_message = f" **{' '.join(infraction_type.split('_'))}** to {user.mention}{expiry_msg}{end_msg}"

        # Send a confirmation message to the invoking context.
        logger.trace(f"Sending infraction #{id_} confirmation message.")
        await ctx.send(f"{dm_result}{confirm_msg}{infraction_message}.")

        # Send a log message to the mod log.
        logger.trace(f"Sending apply mod log for infraction #{id_}.")
        await self.mod_log.send_log_message(
            color=Colors.red,
            title=f"Infraction {log_title}: {' '.join(infraction_type.split('_'))}",
            thumbnail=user.display_avatar.url,
            text=textwrap.dedent(
                f"""
                Member: {format_user(user)}
                Actor: {ctx.author.mention}{dm_log_text}{expiry_log_text}
                Reason: {reason}
                {additional_info}
            """
            ),
            content=log_content,
            footer=f"ID: {id_}",
        )

        logger.info(f"Applied {infraction_type} infraction #{id_} to {user}.")
        return not failed

    @command()
    async def warn(self, ctx: Context, user: Member, *, reason: str):
        """Warns a member for a given reason."""
        infraction = Infraction(type="warning", user=user.id, actor=ctx.author.id, reason=reason)
        await self.apply_infraction(ctx, infraction, user)

    @command(aliases=["mute"])
    async def timeout(
        self, ctx: Context, user: Member, duration: Optional[Duration] = None, *, reason: Optional[str] = None
    ) -> None:
        """Temporarily timeouts a user for the given reason and duration.

        A unit of time should be appended to the duration.

        If no duration is given, a one-hour duration is used by default.
        """
        if duration is None:
            duration = await Duration().convert(ctx, "1h")

        if user.timed_out:
            await ctx.send(f":x: {user.mention} is already timed out.")
            return

        infraction = Infraction(
            type="timeout", user=user.id, actor=ctx.author.id, reason=reason, expires_at=duration.datetime
        )

        self.mod_log.ignore(Event.member_update, user.id)

        async def action() -> None:
            """Times out the user."""
            await user.timeout(duration.datetime, reason=reason)

        await self.apply_infraction(ctx, infraction, user, action())

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        # pylint: disable=invalid-overridden-method

        return await has_any_role(*MODERATION_ROLES).predicate(ctx)


def setup(bot: RobobenBot) -> None:
    """Loads the infractions cog."""
    bot.add_cog(Infractions(bot))
