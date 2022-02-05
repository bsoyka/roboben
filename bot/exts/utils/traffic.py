"""Traffic watching cog."""

from discord import Color, Embed, Member
from discord.ext.commands import Cog
from loguru import logger

from bot import constants
from bot.bot import RobobenBot


class Traffic(Cog):
    """Watching member joins and leaves."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Welcomes new members."""
        if member.bot:
            return

        logger.debug(f"{member} ({member.id}) has joined {member.guild}, sending welcome in #off-topic")

        channel = member.guild.get_channel(constants.Channels.off_topic)

        embed = Embed(color=Color.green(), description=f"Welcome to **{member.guild.name}**, {member.mention}!")
        embed.set_author(name="Welcome!", icon_url=member.display_avatar.url)

        message = await channel.send(embed=embed)

        await message.add_reaction("👋")

    @Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        """Posts notifications when members leave."""
        logger.debug(f"{member} ({member.id}) has left {member.guild}, sending goodbye in #off-topic")

        channel = member.guild.get_channel(constants.Channels.off_topic)

        embed = Embed(color=Color.red(), description=f"Goodbye, {member.mention}!")
        embed.set_author(name="Goodbye!", icon_url=member.display_avatar.url)

        await channel.send(embed=embed)


def setup(bot: RobobenBot) -> None:
    """Loads the traffic cog."""
    bot.add_cog(Traffic(bot))
