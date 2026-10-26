"""The /server command: stats about the guild it's run in."""

import discord
from discord import app_commands
from discord.ext import commands

from core import BRAND_COLOR, COLORS, panel


class ServerInfo(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="server", description="Show information about this server.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            view = panel("Server only", "This command can only be used inside a server.", color=COLORS["red"])
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        stats = (
            f"**Members:** {guild.member_count:,}\n"
            f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"**Boosts:** {guild.premium_subscription_count} (Tier {guild.premium_tier})\n"
            f"**Channels:** {len(guild.channels):,}\n"
            f"**Roles:** {len(guild.roles):,}\n"
            f"**Created:** {discord.utils.format_dt(guild.created_at, 'R')}"
        )
        view = panel(
            guild.name,
            guild.description or None,
            stats,
            thumbnail=guild.icon.url if guild.icon else None,
            footer=f"Server ID: {guild.id}",
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="servericon", description="Show the server's icon.")
    @app_commands.guild_only()
    async def servericon(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or guild.icon is None:
            view = panel("No icon", "This server doesn't have an icon set.", color=COLORS["red"])
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        url = guild.icon.replace(size=1024).url
        view = discord.ui.LayoutView()
        container = discord.ui.Container(accent_colour=BRAND_COLOR)
        container.add_item(discord.ui.TextDisplay(f"## {guild.name} icon"))
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=url)
        container.add_item(gallery)
        container.add_item(discord.ui.TextDisplay(f"-# [Open full size]({url})"))
        view.add_item(container)
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerInfo(bot))
