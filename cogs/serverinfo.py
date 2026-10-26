"""The /server command: stats about the guild it's run in."""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, base_embed


class ServerInfo(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="server", description="Show information about this server.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            embed = base_embed("Server only", "This command can only be used inside a server.", COLORS["red"])
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = base_embed(guild.name, guild.description)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(
            name="Boosts",
            value=f"{guild.premium_subscription_count} (Tier {guild.premium_tier})",
            inline=True,
        )
        embed.add_field(name="Channels", value=f"{len(guild.channels):,}", inline=True)
        embed.add_field(name="Roles", value=f"{len(guild.roles):,}", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
        embed.set_footer(text=f"Server ID: {guild.id}", icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerInfo(bot))
