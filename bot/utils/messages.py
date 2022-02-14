"""Utilities for Discord messages."""

import random

from disnake import Color, Embed, Message
from disnake.abc import User
from disnake.ext.commands import Context

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


def format_user(user: User, *, include_username: bool = False) -> str:
    """Returns a string for `user` which has their mention and ID."""
    if include_username:
        return f"{user.mention} (`{user}`, `{user.id}`)"
    return f"{user.mention} (`{user.id}`)"
