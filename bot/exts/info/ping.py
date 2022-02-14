"""Ping command."""

from disnake import Color, Embed
from disnake.ext.commands import Cog, Context, command

from bot.bot import RobobenBot

ROUND_LATENCY = 2


class Latency(Cog):
    """The bot's ping command."""

    category = "Information"

    def __init__(self, bot):
        self.bot = bot

    @command()
    async def ping(self, ctx: Context) -> None:
        """Shows the Discord API latency"""
        embed = Embed(title="Pong!", color=Color.green())

        embed.add_field(
            name="Discord API latency",
            value=f"{self.bot.latency * 1000:.{ROUND_LATENCY}f} ms",
            inline=False,
        )

        await ctx.send(embed=embed)


def setup(bot: RobobenBot):
    """Loads the latency cog."""
    bot.add_cog(Latency(bot))
