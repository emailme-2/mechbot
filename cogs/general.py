"""General-purpose commands: ping, hello, info, and the help listing."""

import platform

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, base_embed, format_duration, now


class General(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        color = COLORS["green"] if latency < 120 else COLORS["yellow"] if latency < 300 else COLORS["red"]

        embed = base_embed("🏓 Pong!", f"Gateway latency: **{latency} ms**", color)
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="hello", description="Say hello with a welcome embed.")
    @app_commands.describe(member="Who to greet (defaults to you)")
    async def hello(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        target = member or interaction.user

        embed = base_embed("👋 Hello!", f"Hey {target.mention}, welcome aboard!")
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Greeted by", value=interaction.user.mention, inline=True)
        embed.add_field(name="When", value=discord.utils.format_dt(now(), "R"), inline=True)
        embed.set_footer(text="MechBot", icon_url=interaction.client.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Show information about the bot.")
    async def info(self, interaction: discord.Interaction) -> None:
        me = interaction.client.user
        embed = base_embed("🤖 MechBot", "A small demo bot running on slash commands and embeds.")
        embed.set_author(name=me.name, icon_url=me.display_avatar.url)
        embed.set_thumbnail(url=me.display_avatar.url)
        embed.add_field(name="Uptime", value=format_duration(now() - self.bot.started_at), inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.tree.get_commands())), inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.set_footer(text="Made with discord.py", icon_url=me.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="List every command.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = base_embed("📖 Commands", "Everything this bot can do.")
        for command in sorted(self.bot.tree.get_commands(), key=lambda cmd: cmd.name):
            embed.add_field(name=f"/{command.name}", value=command.description or "No description", inline=False)
        embed.set_footer(text="MechBot", icon_url=interaction.client.user.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
