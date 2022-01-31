"""Security-related helpers."""

from discord.ext.commands import Cog, Context, NoPrivateMessage

from bot.bot import RobobenBot


class Security(Cog):
    """Security-related checks for the bot."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self.bot.check(self.check_not_bot)  # Global commands check - no bots can run any commands at all
        self.bot.check(self.check_on_guild)  # Global commands check - commands can't be run in a DM

    def check_not_bot(self, ctx: Context) -> bool:
        """Check if the context is a bot user."""
        return not ctx.author.bot

    def check_on_guild(self, ctx: Context) -> bool:
        """Check if the context is in a guild."""
        if ctx.guild is None:
            raise NoPrivateMessage("This command cannot be used in private messages.")
        return True


def setup(bot: RobobenBot) -> None:
    """Loads the security cog."""
    bot.add_cog(Security(bot))
