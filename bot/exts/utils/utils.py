"""Random utilities."""

from disnake import Embed
from disnake.ext.commands import BadArgument, Cog, Context, clean_content, command

from bot.bot import RobobenBot


class RandomUtilities(Cog):
    """Random utility commands."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @command(aliases=("vote",))
    async def poll(self, ctx: Context, title: clean_content(fix_channel_mentions=True), *options: str) -> None:
        """Builds a quick voting poll with matching reactions with the provided
        options.

        A maximum of 20 options can be provided, as Discord supports a max of 20
        reactions on a single message.
        """
        if len(title) > 256:
            raise BadArgument("The title cannot be longer than 256 characters.")
        if len(options) < 2:
            raise BadArgument("Please provide at least 2 options.")
        if len(options) > 20:
            raise BadArgument("I can only handle 20 options!")

        codepoint_start = 127462  # represents "regional_indicator_a" unicode value
        options = {chr(i): f"{chr(i)} - {v}" for i, v in enumerate(options, start=codepoint_start)}
        embed = Embed(title=title, description="\n".join(options.values()))
        message = await ctx.send(embed=embed)
        for reaction in options:
            await message.add_reaction(reaction)


def setup(bot: RobobenBot):
    """Loads the random utilities cog."""
    bot.add_cog(RandomUtilities(bot))
