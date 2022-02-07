"""Help command."""

import itertools
from collections import namedtuple
from contextlib import suppress
from typing import Optional

from discord import Color, Embed
from discord.ext import commands
from fuzzywuzzy import fuzz, process
from fuzzywuzzy.utils import full_process

from bot import constants
from bot.bot import RobobenBot
from bot.utils import LinePaginator

COMMANDS_PER_PAGE = 8
PREFIX = constants.Bot.prefix

NOT_ALLOWED_TO_RUN_MESSAGE = "***You cannot run this command.***\n\n"

Category = namedtuple("Category", ["name", "description", "cogs"])


class HelpQueryNotFound(ValueError):
    """Raised when a HelpSession Query doesn't match a command or cog.

    Contains the custom attribute of ``possible_matches``.

    Instances of this object contain a dictionary of any command(s) that
    were close to matching the query, where keys are the possible
    matched command names and values are the likeness match scores.
    """

    def __init__(self, arg: str, possible_matches: Optional[dict] = None):
        super().__init__(arg)
        self.possible_matches = possible_matches


class CustomHelpCommand(commands.HelpCommand):
    """An interactive instance for the bot help command.

    Cogs can be grouped into custom categories. All cogs with the same category
    will be displayed under a single category name in the help output. Custom
    categories are defined inside the cogs as a class attribute named
    `category`. A description can also be specified with the attribute
    `category_description`. If a description is not found in at least one cog,
    the default will be the regular description (class docstring) of the first
    cog found in the category.
    """

    def __init__(self):
        super().__init__(command_attrs={"help": "Shows help for bot commands"})

    async def command_callback(self, ctx: commands.Context, *, command: Optional[str] = None) -> None:
        """Attempts to match the provided query with a valid command or cog."""
        # The only reason we need to tamper with this is that d.py does not
        # support "categories", so we need to deal with them ourselves.

        bot = ctx.bot

        if command is None:
            # Send bot help if command isn't specified
            mapping = self.get_bot_mapping()
            await self.send_bot_help(mapping)
            return

        cog_matches = []
        description = None
        for cog in bot.cogs.values():
            if hasattr(cog, "category") and cog.category == command:
                cog_matches.append(cog)
                if hasattr(cog, "category_description"):
                    description = cog.category_description

        if cog_matches:
            category = Category(name=command, description=description, cogs=cog_matches)
            await self.send_category_help(category)
            return

        # It's either a cog, group, command or subcommand; let the parent class deal with it
        await super().command_callback(ctx, command=command)

    async def get_all_help_choices(self) -> set[str]:
        """Gets all the possible options for getting help in the bot.

        This will only display commands the author has permission to run.

        These include:
        - Category names
        - Cog names
        - Group command names (and aliases)
        - Command names (and aliases)
        - Subcommand names (with parent group and aliases for subcommand, but
          not including aliases for group)

        Options and choices are case sensitive.
        """
        # Get all commands, including subcommands and full command name aliases
        choices = set()
        for command in await self.filter_commands(self.context.bot.walk_commands()):
            # The command or group name
            choices.add(str(command))

            if isinstance(command, commands.Command):
                # All aliases if it's just a command
                choices.update(command.aliases)
            else:
                # Otherwise, we need to add the parent name in
                choices.update(f"{command.full_parent_name} {alias}" for alias in command.aliases)

        # All cog names
        choices.update(self.context.bot.cogs)

        # All category names
        choices.update(cog.category for cog in self.context.bot.cogs.values() if hasattr(cog, "category"))

        return choices

    async def command_not_found(self, string: str) -> HelpQueryNotFound:
        """Handles when a query does not match a valid command, group, cog, or
        category.

        Will return an instance of the `HelpQueryNotFound` exception with the
        error message and possible matches.
        """
        # pylint: disable=invalid-overridden-method

        choices = await self.get_all_help_choices()

        # Run fuzzywuzzy's processor beforehand, and avoid matching if processed string is empty
        # This avoids fuzzywuzzy from raising a warning on inputs with only non-alphanumeric characters
        if processed := full_process(string):
            result = process.extractBests(
                processed,
                choices,
                scorer=fuzz.ratio,
                score_cutoff=60,
                processor=None,
            )
        else:
            result = []

        return HelpQueryNotFound(f'Query "{string}" not found.', dict(result))

    async def subcommand_not_found(self, command: commands.Command, string: str) -> HelpQueryNotFound:
        """Redirects the error to `command_not_found`.

        `command_not_found` deals with searching and getting best choices for
        both commands and subcommands.
        """
        # pylint: disable=invalid-overridden-method

        return await self.command_not_found(f"{command.qualified_name} {string}")

    async def send_error_message(self, error: HelpQueryNotFound) -> None:
        """Sends the error message to the channel."""
        embed = Embed(colour=Color.red(), title=str(error))

        if getattr(error, "possible_matches", None):
            matches = "\n".join(f"`{match}`" for match in error.possible_matches)
            embed.description = f"**Did you mean:**\n{matches}"

        await self.context.send(embed=embed)

    async def command_formatting(self, command: commands.Command) -> Embed:
        """Turns a command into a help embed.

        It will add an author, command signature + help, aliases and a note if
        the user can't run the command.
        """
        embed = Embed()
        embed.set_author(name="Command Help")

        parent = command.full_parent_name

        name = str(command) if not parent else f"{parent} {command.name}"
        command_details = f"**```{PREFIX}{name} {command.signature}```**\n"

        # Show command aliases
        aliases = [f"`{alias}`" if not parent else f"`{parent} {alias}`" for alias in command.aliases]
        aliases += [f"`{alias}`" for alias in getattr(command, "root_aliases", ())]
        if aliases := ", ".join(sorted(aliases)):
            command_details += f"**Can also use:** {aliases}\n\n"

        # Display if the command is disabled or cannot be run by the user
        try:
            if not await command.can_run(self.context):
                command_details += NOT_ALLOWED_TO_RUN_MESSAGE
        except commands.DisabledCommand:
            command_details += "***This command is disabled.***\n\n"
        except commands.CommandError:
            command_details += NOT_ALLOWED_TO_RUN_MESSAGE

        command_details += f"*{command.help or 'No details provided.'}*\n"
        embed.description = command_details

        return embed

    async def send_command_help(self, command: commands.Command) -> None:
        """Send help for a single command."""
        embed = await self.command_formatting(command)
        await self.context.send(embed=embed)

    @staticmethod
    def get_commands_brief_details(commands_: list[commands.Command], return_as_list: bool = False) -> list[str] | str:
        """
        Formats the prefix, command name and signature, and short doc for an
        iterable of commands.

        return_as_list is helpful for passing these command details into the
        paginator as a list of command details.
        """
        details = []
        for command in commands_:
            signature = f" {command.signature}" if command.signature else ""
            details.append(
                f"\n**`{PREFIX}{command.qualified_name}{signature}`**\n*{command.short_doc or 'No details provided'}*"
            )

        return details if return_as_list else "".join(details)

    async def send_group_help(self, group: commands.Group) -> None:
        """Sends help for a group command."""
        subcommands = group.commands

        if len(subcommands) == 0:
            # no subcommands, just treat it like a regular command
            await self.send_command_help(group)
            return

        # remove commands that the user can't run and are hidden, and sort by name
        commands_ = await self.filter_commands(subcommands, sort=True)

        embed = await self.command_formatting(group)

        if command_details := self.get_commands_brief_details(commands_):
            embed.description += f"\n**Subcommands:**\n{command_details}"

        await self.context.send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        """Sends help for a cog."""
        # Sort commands by name, and remove any the user can't run or are hidden.
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)

        embed = Embed()
        embed.set_author(name="Command Help")
        embed.description = f"**{cog.qualified_name}**\n*{cog.description}*"

        if command_details := self.get_commands_brief_details(commands_):
            embed.description += f"\n\n**Commands:**\n{command_details}"

        await self.context.send(embed=embed)

    @staticmethod
    def _category_key(command: commands.Command) -> str:
        """Returns a cog name of a given command for use as a key for `sorted`
        and `groupby`.

        A zero width space is used as a prefix for results with no cogs to
        force them last in ordering.
        """
        if not command.cog:
            return "**\u200bNo Category:**"

        with suppress(AttributeError):
            if command.cog.category:
                return f"**{command.cog.category}**"
        return f"**{command.cog_name}**"

    async def send_category_help(self, category: Category) -> None:
        """Sends help for a bot category.

        This sends a brief help for all commands in all cogs registered to the
        category.
        """
        embed = Embed()
        embed.set_author(name="Command Help")

        all_commands = []
        for cog in category.cogs:
            all_commands.extend(cog.get_commands())

        filtered_commands = await self.filter_commands(all_commands, sort=True)

        command_detail_lines = self.get_commands_brief_details(filtered_commands, return_as_list=True)
        description = f"**{category.name}**\n*{category.description}*"

        if command_detail_lines:
            description += "\n\n**Commands:**"

        await LinePaginator.paginate(
            command_detail_lines,
            self.context,
            embed,
            prefix=description,
            max_lines=COMMANDS_PER_PAGE,
            max_size=2000,
        )

    async def send_bot_help(self, mapping: dict) -> None:
        """Sends help for all bot commands and cogs."""
        # pylint: disable=too-many-locals

        bot = self.context.bot

        embed = Embed()
        embed.set_author(name="Command Help")

        filter_commands = await self.filter_commands(bot.commands, sort=True, key=self._category_key)

        cog_or_category_pages = []

        for cog_or_category, _commands in itertools.groupby(filter_commands, key=self._category_key):
            sorted_commands = sorted(_commands, key=lambda c: c.name)

            if len(sorted_commands) == 0:
                continue

            command_detail_lines = self.get_commands_brief_details(sorted_commands, return_as_list=True)

            # Split cogs or categories which have too many commands to fit in one page.
            # The length of commands is included for later use when aggregating into pages for the paginator.
            for index in range(0, len(sorted_commands), COMMANDS_PER_PAGE):
                truncated_lines = command_detail_lines[index : index + COMMANDS_PER_PAGE]
                joined_lines = "".join(truncated_lines)
                cog_or_category_pages.append(
                    (
                        f"**{cog_or_category}**{joined_lines}",
                        len(truncated_lines),
                    )
                )

        pages = []
        counter = 0
        page = ""
        for page_details, length in cog_or_category_pages:
            counter += length
            if counter > COMMANDS_PER_PAGE:
                # force a new page on paginator even if it falls short of the max pages
                # since we still want to group categories/cogs.
                counter = length
                pages.append(page)
                page = f"{page_details}\n\n"
            else:
                page += f"{page_details}\n\n"

        if page:
            # add any remaining command help that didn't get added in the last iteration above.
            pages.append(page)

        await LinePaginator.paginate(pages, self.context, embed=embed, max_lines=1, max_size=2000)


class HelpCog(commands.Cog, name="Help"):
    """Custom help command for the bot."""

    category = "Information"

    def __init__(self, bot: RobobenBot) -> None:
        self.bot = bot
        self.old_help_command = bot.help_command
        bot.help_command = CustomHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self) -> None:
        """Resets the help command when the cog is unloaded."""
        self.bot.help_command = self.old_help_command


def setup(bot):
    """Loads the help command cog."""
    bot.add_cog(HelpCog(bot))
