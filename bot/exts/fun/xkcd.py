"""XKCD interface."""

import re
from random import randint
from typing import Optional, Union

from disnake import Color, Embed
from disnake.ext import tasks
from disnake.ext.commands import Cog, Context, command
from loguru import logger

from bot.bot import RobobenBot

COMIC_FORMAT = re.compile(r"latest|[0-9]+")
BASE_URL = "https://xkcd.com"


class XKCD(Cog):
    """XKCD interface for the bot."""

    def __init__(self, bot: RobobenBot):
        self.bot = bot
        self.latest_comic_info: dict[str, Union[str, int]] = {}
        self.get_latest_comic_info.start()  # pylint: disable=no-member

    def cog_unload(self) -> None:
        """Cancels refreshing of the task for refreshing the most recent comic info."""
        self.get_latest_comic_info.cancel()  # pylint: disable=no-member

    @tasks.loop(minutes=30)
    async def get_latest_comic_info(self) -> None:
        """Refreshes the latest comic's information every 30 minutes."""
        async with self.bot.http_session.get(f"{BASE_URL}/info.0.json") as resp:
            if resp.ok:
                self.latest_comic_info = await resp.json()
            else:
                logger.warning(f"Failed to get latest XKCD comic information. Status code {resp.status}")

    @command(name="xkcd")
    async def fetch_xkcd_comics(self, ctx: Context, comic: Optional[str] = None) -> None:
        """
        Gets an XKCD comic's information along with the image.

        To get a random comic, don't type any number as an argument. To get the latest, type 'latest'.
        """
        embed = Embed(title=f"XKCD comic '{comic}'")

        embed.colour = Color.red()

        if comic and (comic := re.match(COMIC_FORMAT, comic)) is None:
            embed.description = "Comic parameter should either be an integer or 'latest'."
            await ctx.send(embed=embed)
            return

        comic = randint(1, self.latest_comic_info["num"]) if comic is None else comic.group(0)

        if comic == "latest":
            info = self.latest_comic_info
        else:
            async with self.bot.http_session.get(f"{BASE_URL}/{comic}/info.0.json") as resp:
                if resp.ok:
                    info = await resp.json()
                else:
                    embed.title = f"XKCD comic #{comic}"
                    embed.description = f"{resp.status}: Could not retrieve xkcd comic #{comic}."
                    logger.debug(f"Retrieving xkcd comic #{comic} failed with status code {resp.status}.")
                    await ctx.send(embed=embed)
                    return

        embed.title = f"XKCD comic #{info['num']}"
        embed.description = info["alt"]
        embed.url = f"{BASE_URL}/{info['num']}"

        if info["img"][-3:] in ("jpg", "png", "gif"):
            embed.set_image(url=info["img"])
            date = f"{info['year']}/{info['month']}/{info['day']}"
            embed.set_footer(text=f"{date} - #{info['num']}, '{info['safe_title']}'")
            embed.colour = Color.green()
        else:
            embed.description = (
                "The selected comic is interactive, and cannot be displayed within an embed.\n"
                f"Comic can be viewed [here](https://xkcd.com/{info['num']})."
            )

        await ctx.send(embed=embed)


def setup(bot: RobobenBot) -> None:
    """Loads the XKCD cog."""
    bot.add_cog(XKCD(bot))
