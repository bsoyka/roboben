"""The main interface for the bot."""

from bot import constants
from bot.bot import RobobenBot

instance = RobobenBot.create()
instance.load_extensions()
instance.run(constants.Bot.token)
