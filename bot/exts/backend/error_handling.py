"""Command error handling."""

from discord import Message
from discord.ext.commands import Cog, Context, errors
from loguru import logger

from bot.bot import RobobenBot
from bot.utils.messages import send_denial


class ErrorHandling(Cog):
    """The command error handler for the bot."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @staticmethod
    async def _send_error_embed(ctx: Context, title: str, body: str) -> Message:
        """Sends an error embed to the channel."""
        reason = f"{title}\n{body}"

        message = await send_denial(ctx, reason)
        return message

    @Cog.listener()
    async def on_command_error(self, ctx: Context, error: errors.CommandError) -> None:
        """Handles errors that occur while executing a command."""
        command = ctx.command

        if getattr(error, "handled", False):
            logger.trace(f"Command {command}'s error was already handled locally.")
            return

        debug_message = (
            f"Command {command} invoked by {ctx.message.author} with error " f"{error.__class__.__name__}: {error}"
        )

        if isinstance(error, errors.UserInputError):
            logger.debug(debug_message)
            await self.handle_user_input_error(ctx, error)
        elif isinstance(error, errors.CheckFailure | errors.NotOwner):
            logger.debug(debug_message)
            await self.handle_check_failure(ctx, error)
        elif isinstance(error, errors.CommandNotFound):
            logger.debug(f"Unknown command invoked by {ctx.message.author}: {ctx.message.content}")
        elif isinstance(error, errors.CommandOnCooldown):
            logger.debug(debug_message)
            await ctx.send(error)
        elif isinstance(error, errors.CommandInvokeError | errors.ConversionError):
            await self.handle_unexpected_error(ctx, error.original)
        elif isinstance(error, errors.DisabledCommand):
            logger.debug(debug_message)
        else:
            await self.handle_unexpected_error(ctx, error)

    async def handle_user_input_error(self, ctx: Context, error: errors.UserInputError) -> None:
        """Handles errors that occur while parsing user input."""
        if isinstance(error, errors.MissingRequiredArgument):
            await self._send_error_embed(ctx, "Missing required argument", error.param.name)
        elif isinstance(error, errors.TooManyArguments):
            await self._send_error_embed(ctx, "Too many arguments", str(error))
        elif isinstance(error, errors.BadArgument):
            await self._send_error_embed(ctx, "Bad argument", str(error))
        elif isinstance(error, errors.BadUnionArgument):
            await self._send_error_embed(ctx, "Bad argument", f"{error}\n{error.errors[-1]}")
        elif isinstance(error, errors.ArgumentParsingError):
            await self._send_error_embed(ctx, "Argument parsing error", str(error))
        else:
            await send_denial(
                ctx,
                "Something about your input seems off. Check the arguments and try again.",
            )

    @staticmethod
    async def handle_check_failure(ctx: Context, error: errors.CheckFailure) -> None:
        """Handles check failures."""
        bot_missing_errors = errors.BotMissingPermissions | errors.BotMissingRole | errors.BotMissingAnyRole
        user_missing_errors = errors.MissingPermissions | errors.MissingRole | errors.MissingAnyRole | errors.NotOwner

        if isinstance(error, bot_missing_errors):
            logger.opt(exception=error).warning(
                f"Missing permissions to execute command invoked by {ctx.message.author}: {ctx.message.content}"
            )
            await ctx.send("Sorry, it looks like I don't have the permissions or roles I need to do that.")
        elif isinstance(error, user_missing_errors):
            logger.debug(f"User {ctx.message.author} missing permissions to invoke command: {ctx.message.content}")
            await send_denial(ctx, "You don't have the permissions or roles you need to do that.")
        elif isinstance(error, errors.NoPrivateMessage):
            logger.debug(f"User {ctx.message.author} tried to invoke command in DM: {ctx.message.content}")
            await send_denial(ctx, "Sorry, I can't do that in DMs.")

    async def handle_unexpected_error(self, ctx: Context, error: Exception) -> None:
        """Handles unexpected errors."""
        logger.opt(exception=error).error(
            f"Error executing command invoked by {ctx.message.author}: {ctx.message.content}"
        )

        await self._send_error_embed(
            ctx,
            "An unexpected error occurred. Please let us know!",
            f"```{error.__class__.__name__}: {error}```",
        )


def setup(bot: RobobenBot):
    """Loads the error handling cog."""
    bot.add_cog(ErrorHandling(bot))
