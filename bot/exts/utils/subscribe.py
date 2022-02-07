"""Subscribable roles."""

import operator
import typing as t
from dataclasses import dataclass

import discord
from discord import Interaction
from discord.ext import commands
from loguru import logger

from bot import constants
from bot.bot import RobobenBot
from bot.utils import create_task


@dataclass(frozen=True)
class AssignableRole:
    """A role that can be assigned to a user."""

    role_id: int
    name: t.Optional[str] = None  # This gets populated within Subscribe.init_cog()


ASSIGNABLE_ROLES = (AssignableRole(constants.Roles.updates),)

ITEMS_PER_ROW = 3
DELETE_MESSAGE_AFTER = 300  # Seconds


class RoleButtonView(discord.ui.View):
    """A list of SingleRoleButtons to show to the member."""

    def __init__(self, member: discord.Member):
        super().__init__()
        self.interaction_owner = member

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Ensure that the user clicking the button is the member who invoked the command."""
        if interaction.user != self.interaction_owner:
            await interaction.response.send_message(":x: This is not your command to react to!", ephemeral=True)
            return False
        return True


class SingleRoleButton(discord.ui.Button):
    """A button that adds or removes a role from the member depending on its
    current state.
    """

    ADD_STYLE = discord.ButtonStyle.success
    REMOVE_STYLE = discord.ButtonStyle.red
    LABEL_FORMAT = "{action} role {role_name}"
    CUSTOM_ID_FORMAT = "subscribe-{role_id}"

    def __init__(self, role: AssignableRole, assigned: bool, row: int):
        style = self.REMOVE_STYLE if assigned else self.ADD_STYLE
        label = self.LABEL_FORMAT.format(action="Remove" if assigned else "Add", role_name=role.name)

        super().__init__(
            style=style,
            label=label,
            custom_id=self.CUSTOM_ID_FORMAT.format(role_id=role.role_id),
            row=row,
        )
        self.role = role
        self.assigned = assigned

        self.style = style
        self.label = label

    async def callback(self, interaction: Interaction) -> None:
        """Updates the member's role and change button text to reflect current
        text.
        """
        if isinstance(interaction.user, discord.User):
            logger.trace(f"User {interaction.user} is not a member")
            await interaction.message.delete()
            self.view.stop()
            return

        if self.assigned:
            await interaction.user.remove_roles(discord.Object(self.role.role_id))
        else:
            await interaction.user.add_roles(discord.Object(self.role.role_id))

        self.assigned = not self.assigned
        await self.update_view(interaction)
        await interaction.response.send_message(
            self.LABEL_FORMAT.format(action="Added" if self.assigned else "Removed", role_name=self.role.name),
            ephemeral=True,
        )

    async def update_view(self, interaction: Interaction) -> None:
        """Updates the original interaction message with a new view object with
        the updated buttons.
        """
        self.style = self.REMOVE_STYLE if self.assigned else self.ADD_STYLE
        self.label = self.LABEL_FORMAT.format(action="Remove" if self.assigned else "Add", role_name=self.role.name)
        try:
            await interaction.message.edit(view=self.view)
        except discord.NotFound:
            logger.debug(f"Subscribe message for {interaction.user} removed before buttons could be updated")
            self.view.stop()


class Subscribe(commands.Cog):
    """Self-assignable role management."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self.init_task = create_task(self.init_cog(), event_loop=self.bot.loop)
        self.assignable_roles: list[AssignableRole] = []
        self.guild: t.Optional[discord.Guild] = None

    async def init_cog(self) -> None:
        """Initialises the cog by resolving the role IDs in ASSIGNABLE_ROLES to
        role names.
        """
        await self.bot.wait_until_ready()

        self.guild = self.bot.get_guild(constants.Server.id)

        for role in ASSIGNABLE_ROLES:
            discord_role = self.guild.get_role(role.role_id)
            if discord_role is None:
                logger.warning(f"Could not resolve {role.role_id} to a role in the guild, skipping.")
                continue
            self.assignable_roles.append(
                AssignableRole(
                    role_id=role.role_id,
                    name=discord_role.name,
                )
            )

        # Sort by role name
        self.assignable_roles.sort(key=operator.attrgetter("name"))

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="subscribe")
    async def subscribe_command(self, ctx: commands.Context) -> None:
        """Subscribes and unsubscribes to updates."""
        await self.init_task

        button_view = RoleButtonView(ctx.author)
        author_roles = [role.id for role in ctx.author.roles]
        for index, role in enumerate(self.assignable_roles):
            row = index // ITEMS_PER_ROW
            button_view.add_item(SingleRoleButton(role, role.role_id in author_roles, row))

        await ctx.send(
            "Click the buttons below to add or remove your roles!",
            view=button_view,
            delete_after=DELETE_MESSAGE_AFTER,
        )


def setup(bot: RobobenBot) -> None:
    """Loads the subscribe cog."""
    if len(ASSIGNABLE_ROLES) > ITEMS_PER_ROW * 5:  # Discord limits views to 5 rows of buttons.
        logger.error("Too many roles for 5 rows, not loading the Subscribe cog.")
    else:
        bot.add_cog(Subscribe(bot))
