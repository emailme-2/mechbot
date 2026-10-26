"""The /embed command: build a custom embed with a chosen accent color."""

import discord
from discord import app_commands
from discord.ext import commands

from core import BRAND_COLOR, COLORS, base_embed


class Embeds(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="embed", description="Build a custom embed.")
    @app_commands.describe(title="Embed title", description="Embed body text", color="Accent color")
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

        embed = base_embed(title, description, accent)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Posted with /embed", icon_url=interaction.client.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Embeds(bot))
