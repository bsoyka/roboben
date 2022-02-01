"""Extension management cog."""

import functools
import typing as t
from enum import Enum

from discord import Color, Embed
from discord.ext import commands
from discord.ext.commands import Context, group
from loguru import logger

from bot import exts
from bot.bot import RobobenBot
from bot.converters import Extension
from bot.utils import LinePaginator
from bot.utils.extensions import EXTENSIONS

UNLOAD_BLOCKLIST = {f"{exts.__name__}.utils.extensions", f"{exts.__name__}.moderation.modlog"}
BASE_PATH_LEN = len(exts.__name__.split("."))


class Action(Enum):
    """An action to perform on an extension."""

    # Need to be partial otherwise they are considered to be function definitions.
    LOAD = functools.partial(RobobenBot.load_extension)
    UNLOAD = functools.partial(RobobenBot.unload_extension)
    RELOAD = functools.partial(RobobenBot.reload_extension)


class Extensions(commands.Cog):
    """Extension management commands."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @group(name="extensions", aliases=("ext", "exts"), invoke_without_command=True)
    async def extensions_group(self, ctx: Context) -> None:
        """Loads, unloads, reloads, and lists loaded extensions."""
        await ctx.send_help(ctx.command)

    @extensions_group.command(name="load", aliases=("l",))
    async def load_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""Loads extensions given their fully qualified or unqualified names.

        If '\*' or '\*\*' is given as the name, all unloaded extensions will be
        loaded.
        """
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        if "*" in extensions or "**" in extensions:
            extensions = set(EXTENSIONS) - set(self.bot.extensions.keys())

        msg = self.batch_manage(Action.LOAD, *extensions)
        await ctx.send(msg)

    @extensions_group.command(name="unload", aliases=("ul",))
    async def unload_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""Unloads currently-loaded extensions given their fully qualified or
        unqualified names.

        If '\*' or '\*\*' is given as the name, all loaded extensions will be
        unloaded.
        """
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        if blocklisted := "\n".join(UNLOAD_BLOCKLIST & set(extensions)):
            msg = f":x: The following extension(s) may not be unloaded:```\n{blocklisted}```"
        else:
            if "*" in extensions or "**" in extensions:
                extensions = set(self.bot.extensions.keys()) - UNLOAD_BLOCKLIST

            msg = self.batch_manage(Action.UNLOAD, *extensions)

        await ctx.send(msg)

    @extensions_group.command(name="reload", aliases=("r",), root_aliases=("reload",))
    async def reload_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""Reloads extensions given their fully qualified or unqualified names.

        If an extension fails to be reloaded, it will be rolled-back to the prior
        working state.

        If '\*' is given as the name, all currently loaded extensions will be
        reloaded. If '\*\*' is given as the name, all extensions, including
        unloaded ones, will be reloaded.
        """
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        if "**" in extensions:
            extensions = EXTENSIONS
        elif "*" in extensions:
            extensions = set(self.bot.extensions.keys()) | set(extensions)
            extensions.remove("*")

        msg = self.batch_manage(Action.RELOAD, *extensions)

        await ctx.send(msg)

    @extensions_group.command(name="list", aliases=("all",))
    async def list_command(self, ctx: Context) -> None:
        """Lists of all extensions, including their loaded status.

        Black indicates that the extension is unloaded. Green indicates that the extension is currently loaded.
        """
        embed = Embed(color=Color.blurple())
        embed.set_author(name="Extensions List")

        lines = []
        categories = self.group_extension_statuses()
        for category, extensions in sorted(categories.items()):
            # Treat each category as a single line by concatenating everything.
            # This ensures the paginator will not cut off a page in the middle of a category.
            category = category.replace("_", " ").title()
            extensions = "\n".join(sorted(extensions))
            lines.append(f"**{category}**\n{extensions}\n")

        logger.debug(f"{ctx.author} requested a list of all cogs. Returning a paginated list.")
        await LinePaginator.paginate(lines, ctx, embed, scale_to_size=700, empty=False)

    def group_extension_statuses(self) -> dict[str, str]:
        """Returns a mapping of extension names and statuses to their categories."""
        categories = {}

        for ext in EXTENSIONS:
            status = ":green_circle:" if ext in self.bot.extensions else ":black_circle:"

            path = ext.split(".")
            if len(path) > BASE_PATH_LEN + 1:
                category = " - ".join(path[BASE_PATH_LEN:-1])
            else:
                category = "uncategorised"

            categories.setdefault(category, []).append(f"{status}  {path[-1]}")

        return categories

    def batch_manage(self, action: Action, *extensions: str) -> str:
        """Applies an action to multiple extensions and return a message with
        the results.

        If only one extension is given, it is deferred to `manage()`.
        """
        if len(extensions) == 1:
            msg, _ = self.manage(action, extensions[0])
            return msg

        verb = action.name.lower()
        failures = {}

        for extension in extensions:
            _, error = self.manage(action, extension)
            if error:
                failures[extension] = error

        emoji = ":x:" if failures else ":ok_hand:"
        msg = f"{emoji} {len(extensions) - len(failures)} / {len(extensions)} extensions {verb}ed."

        if failures:
            failures = "\n".join(f"{ext}\n    {err}" for ext, err in failures.items())
            msg += f"\nFailures:```\n{failures}```"

        logger.debug(f"Batch {verb}ed extensions.")

        return msg

    def manage(self, action: Action, ext: str) -> t.Tuple[str, t.Optional[str]]:
        """Applies an action to an extension and returns the status message and
        any error message.
        """
        verb = action.name.lower()
        error_msg = None

        try:
            action.value(self.bot, ext)
        except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
            if action is Action.RELOAD:
                # When reloading, just load the extension if it was not loaded.
                return self.manage(Action.LOAD, ext)

            msg = f":x: Extension `{ext}` is already {verb}ed."
            logger.debug(msg[4:])
        except Exception as error:  # pylint: disable=broad-except
            if hasattr(error, "original"):
                error = error.original

            logger.exception(f"Extension '{ext}' failed to {verb}.")

            error_msg = f"{error.__class__.__name__}: {error}"
            msg = f":x: Failed to {verb} extension `{ext}`:\n```\n{error_msg}```"
        else:
            msg = f":ok_hand: Extension successfully {verb}ed: `{ext}`."
            logger.debug(msg[10:])

        return msg, error_msg

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allows moderators and core developers to invoke the commands in
        this cog.
        """
        # pylint: disable=invalid-overridden-method

        return await commands.is_owner().predicate(ctx)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Handles BadArgument errors locally to prevent the help command from
        showing.
        """
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))
            error.handled = True


def setup(bot: RobobenBot) -> None:
    """Loads the extension management cog."""
    bot.add_cog(Extensions(bot))
