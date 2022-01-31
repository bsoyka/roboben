"""Custom converters for the bot."""

from discord.ext.commands import BadArgument, Context, Converter

from bot import exts
from bot.utils.extensions import EXTENSIONS, unqualify


class Extension(Converter):
    """
    Fully qualify the name of an extension and ensure it exists.
    The * and ** values bypass this when used with the reload command.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        """Fully qualify the name of an extension and ensure it exists."""
        # Special values to reload all extensions
        if argument in {"*", "**"}:
            return argument

        argument = argument.lower()

        if argument in EXTENSIONS:
            return argument
        if (qualified_arg := f"{exts.__name__}.{argument}") in EXTENSIONS:
            return qualified_arg

        matches = [ext for ext in EXTENSIONS if argument == unqualify(ext)]

        if len(matches) > 1:
            matches.sort()
            names = "\n".join(matches)
            raise BadArgument(
                f":x: `{argument}` is an ambiguous extension name. "
                f"Please use one of the following fully-qualified names.```\n{names}```"
            )
        if matches:
            return matches[0]

        raise BadArgument(f":x: Could not find the extension `{argument}`.")
