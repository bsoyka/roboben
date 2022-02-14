"""Internal administration tools."""

import contextlib
import inspect
import pprint
import re
import textwrap
import traceback
from io import StringIO
from typing import Any, Optional

import disnake
from disnake.ext.commands import Cog, Context, group, is_owner

from bot.bot import RobobenBot
from bot.utils import find_nth_occurrence


class Internal(Cog):
    """Administrator and developer commands."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self.env = {}
        self.line = 0
        self.stdout = StringIO()

        self._ = None

    def _format(self, inp: str, out: Any) -> tuple[str, Optional[disnake.Embed]]:
        """Formats the eval output into a string and attempts to format it into
        an Embed.
        """
        # pylint: disable=too-many-branches

        self._ = out

        res = ""

        # Erase temp input we made
        if inp.startswith("_ = "):
            inp = inp[4:]

        # Get all non-empty lines
        lines = [line for line in inp.split("\n") if line.strip()]
        if len(lines) != 1:
            lines += [""]

        # Create the input dialog
        for i, line in enumerate(lines):
            # Indent the three dots correctly
            start = f"In [{self.line}]: " if i == 0 else "...: ".rjust(len(str(self.line)) + 7)

            if i == len(lines) - 2 and line.startswith("return"):
                line = line[6:].strip()

            # Combine everything
            res += start + line + "\n"

        self.stdout.seek(0)
        text = self.stdout.read()
        self.stdout.close()
        self.stdout = StringIO()

        if text:
            res += text + "\n"

        if out is None:
            # No output, return the input statement
            return res, None

        res += f"Out[{self.line}]: "

        if isinstance(out, disnake.Embed):
            # We made an embed? Send that as embed
            res += "<Embed>"
            res = (res, out)

        else:
            if isinstance(out, str) and out.startswith("Traceback (most recent call last):\n"):
                # Leave out the traceback message
                out = "\n" + "\n".join(out.split("\n")[1:])

            if isinstance(out, str):
                pretty = out
            else:
                pretty = pprint.pformat(out, compact=True, width=60)

            if pretty != str(out):
                # We're using the pretty version, start on the next line
                res += "\n"

            if pretty.count("\n") > 20:
                # Text too long, shorten
                output_lines = pretty.split("\n")

                pretty = (
                    "\n".join(output_lines[:3])  # First 3 lines
                    + "\n ...\n"  # Ellipsis to indicate removed lines
                    + "\n".join(output_lines[-3:])
                )  # last 3 lines

            # Add the output
            res += pretty
            res = (res, None)

        return res  # Return (text, embed)

    async def _eval(self, ctx: Context, code: str) -> Optional[disnake.Message]:
        """Evaluates the input code string and sends an embed to the invoking
        context.
        """
        self.line += 1

        if code.startswith("exit"):
            self.line = 0
            self.env = {}
            return await ctx.send("```Reset history!```")

        env = {
            "message": ctx.message,
            "author": ctx.message.author,
            "channel": ctx.channel,
            "guild": ctx.guild,
            "ctx": ctx,
            "self": self,
            "bot": self.bot,
            "inspect": inspect,
            "disnake": disnake,
            "contextlib": contextlib,
        }

        self.env.update(env)

        # Ignore this code, it works
        code_ = f"""
async def func():  # (None,) -> Any
    try:
        with contextlib.redirect_stdout(self.stdout):
{textwrap.indent(code, " " * 12)}
        if '_' in locals():
            if inspect.isawaitable(_):
                _ = await _
            return _
    finally:
        self.env.update(locals())
"""

        try:
            exec(code_, self.env)  # pylint: disable=exec-used
            func = self.env["func"]
            res = await func()
        except Exception:  # pylint: disable=broad-except
            res = traceback.format_exc()

        out, embed = self._format(code, res)
        out = out.rstrip("\n")  # Strip empty lines from output

        # Truncate output to max 15 lines or 1500 characters
        newline_truncate_index = find_nth_occurrence(out, "\n", 15)

        if newline_truncate_index is None or newline_truncate_index > 1500:
            truncate_index = 1500
        else:
            truncate_index = newline_truncate_index

        if len(out) > truncate_index:
            await ctx.send(f"```py\n{out[:truncate_index]}\n```" f"... response truncated", embed=embed)
            return

        await ctx.send(f"```py\n{out}```", embed=embed)

    @group(name="internal", aliases=("int",))
    @is_owner()
    async def internal_group(self, ctx: Context) -> None:
        """Internal commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @internal_group.command(name="eval", aliases=("e",))
    @is_owner()
    async def eval(self, ctx: Context, *, code: str) -> None:
        """Runs `eval` in a REPL-like format."""
        code = code.strip("`")
        if re.match("py(thon)?\n", code):
            code = "\n".join(code.split("\n")[1:])

        if (
            not re.search(  # Check if it's an expression
                r"^(return|import|for|while|def|class|" r"from|exit|[a-zA-Z0-9]+\s*=)", code, re.M
            )
            and len(code.split("\n")) == 1
        ):
            code = "_ = " + code

        await self._eval(ctx, code)


def setup(bot: RobobenBot) -> None:
    """Loads the internal tools cog."""
    bot.add_cog(Internal(bot))
