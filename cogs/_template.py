"""Starter template for a new cog.

To add a command group:
  1. Copy this file to cogs/<yourname>.py (drop the leading underscore).
  2. Rename the class and set your own command name and description.
  3. Save and restart the bot. The loader finds the file and syncs the command.

Files whose name starts with '_' are skipped by the loader, so this one never
runs as-is. Shared helpers live in core.py: base_embed, COLORS, now, format_duration.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core import base_embed


class Template(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="example", description="An example command to copy.")
    async def example(self, interaction: discord.Interaction) -> None:
        embed = base_embed("Example", "Replace this with your own command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Template(bot))
