"""Server information command."""

from discord import Color, Embed
from discord.ext.commands import Cog, Context, command

from bot import constants
from bot.bot import RobobenBot


class ServerInfo(Cog):
    """Server information command for the bot."""

    category = "Information"

    def __init__(self, bot: RobobenBot):
        self.bot = bot

    @command(name="server", aliases=["server_info", "guild", "guild_info"])
    async def server_info(self, ctx: Context) -> None:
        """Displays information about the server."""
        embed = Embed(title="Server Information", color=Color.blurple())

        creation_time = int(ctx.guild.created_at.replace(tzinfo=None).timestamp())
        created = f"<t:{creation_time}:R>"

        # Member status
        py_invite = await self.bot.fetch_invite(constants.Server.invite)
        online_presences = py_invite.approximate_presence_count
        offline_presences = py_invite.approximate_member_count - online_presences
        member_status = f":green_circle: {online_presences:,} " f":black_circle: {offline_presences:,}"

        embed.description = f"Created: {created}\nMember status: {member_status}"
        embed.set_thumbnail(url=ctx.guild.icon_url)

        # Members
        total_members = f"{ctx.guild.member_count:,}"
        embed.add_field(name="Members", value=total_members)

        # Channels
        total_channels = len(ctx.guild.channels)
        embed.add_field(name="Channels", value=str(total_channels))

        # Roles
        total_roles = len(ctx.guild.roles)
        embed.add_field(name="Roles", value=str(total_roles))

        await ctx.send(embed=embed)


def setup(bot: RobobenBot):
    """Loads the server information cog."""
    bot.add_cog(ServerInfo(bot))
