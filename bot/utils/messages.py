"""Utilities for Discord messages."""

import random

import discord
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


async def send_denial(ctx: Context, reason: str) -> discord.Message:
    """Sends an embed denying the user with the given reason."""
    embed = discord.Embed(description=reason, color=discord.Color.red())
    embed.title = random.choice(tuple(NEGATIVE_REPLIES))

    return await ctx.send(embed=embed)
