"""Utilities for Discord messages."""

import random

from discord import Color, Embed, Message
from discord.abc import User
from discord.ext.commands import Context

NEGATIVE_REPLIES = {
    "Noooooo!!",
    "Nope.",
    "I'm sorry Dave, I'm afraid I can't do that.",
    "I don't think so.",
    "Not gonna happen.",
    "Out of the question.",
    "Huh? No.",
    "Nah.",
    "Naw.",
    "Not likely.",
    "No way, José.",
    "Not in a million years.",
    "Fat chance.",
    "Certainly not.",
    "NEGATORY.",
    "Nuh-uh.",
    "Not in my house!",
}


async def send_denial(ctx: Context, reason: str) -> Message:
    """Sends an embed denying the user with the given reason."""
    embed = Embed(description=reason, color=Color.red())
    embed.title = random.choice(tuple(NEGATIVE_REPLIES))

    return await ctx.send(embed=embed)


def format_user(user: User) -> str:
    """Returns a string for `user` which has their mention and ID."""
    return f"{user.mention} (`{user.id}`)"
