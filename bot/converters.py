"""Custom converters for the bot."""

import re

import arrow
from dateutil.relativedelta import relativedelta
from disnake.ext.commands import BadArgument, Context, Converter

from bot import exts
from bot.utils import time
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


class DurationDelta(Converter):
    """Convert duration strings into dateutil.relativedelta.relativedelta objects."""

    async def convert(self, ctx: Context, duration: str) -> relativedelta:
        """
        Converts a `duration` string to a relativedelta object.
        The converter supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`
        The units need to be provided in descending order of magnitude.
        """
        if not (delta := time.parse_duration_string(duration)):
            raise BadArgument(f"`{duration}` is not a valid duration string.")

        return delta


class Duration(DurationDelta):
    """Convert duration strings into UTC datetime.datetime objects."""

    async def convert(self, ctx: Context, duration: str) -> arrow.Arrow:
        """
        Converts a `duration` string to a datetime object that's `duration` in the future.
        The converter supports the same symbols for each unit of time as its parent class.
        """
        delta = await super().convert(ctx, duration)
        now = arrow.utcnow()

        try:
            return now + delta
        except (ValueError, OverflowError) as error:
            raise BadArgument(f"`{duration}` results in a datetime outside the supported range.") from error


class HushDurationConverter(Converter):
    """Convert passed duration to `int` minutes or `None`."""

    MINUTES_RE = re.compile(r"(\d+)(?:M|m|$)")

    async def convert(self, ctx: Context, argument: str) -> int:
        """
        Convert `argument` to a duration that's max 15 minutes or None.

        If `"forever"` is passed, -1 is returned; otherwise an int of the extracted time.
        Accepted formats are:
        * <duration>,
        * <duration>m,
        * <duration>M,
        * forever.
        """
        if argument == "forever":
            return -1

        match = self.MINUTES_RE.match(argument)
        if not match:
            raise BadArgument(f"{argument} is not a valid minutes duration.")

        duration = int(match.group(1))
        if duration > 15:
            raise BadArgument("Duration must be at most 15 minutes.")
        return duration
