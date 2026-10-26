"""The /embed command: build a custom panel with a chosen accent color."""

import discord
from discord import app_commands
from discord.ext import commands

from core import BRAND_COLOR, COLORS, panel


class Embeds(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="embed", description="Build a custom message panel.")
    @app_commands.describe(title="Panel title", description="Panel body text", color="Accent color")
    @app_commands.choices(
        color=[app_commands.Choice(name=name.title(), value=name) for name in COLORS]
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: app_commands.Choice[str] | None = None,
    ) -> None:
        accent = COLORS[color.value] if color else BRAND_COLOR

        view = panel(
            title,
            description,
            color=accent,
            footer=f"Posted by {interaction.user.display_name} with /embed",
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Embeds(bot))
