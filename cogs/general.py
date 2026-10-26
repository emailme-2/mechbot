"""General-purpose commands: ping, hello, info, and the help listing."""

import platform

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, format_duration, now, panel


class General(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        color = COLORS["green"] if latency < 120 else COLORS["yellow"] if latency < 300 else COLORS["red"]

        view = panel(
            "🏓 Pong!",
            f"Gateway latency: **{latency} ms**",
            color=color,
            footer=f"Requested by {interaction.user.display_name}",
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="hello", description="Say hello with a welcome panel.")
    @app_commands.describe(member="Who to greet (defaults to you)")
    async def hello(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        target = member or interaction.user

        view = panel(
            "👋 Hello!",
            f"Hey {target.mention}, welcome aboard!",
            f"**Greeted by:** {interaction.user.mention}\n**When:** {discord.utils.format_dt(now(), 'R')}",
            thumbnail=target.display_avatar.url,
            footer="MechBot",
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="info", description="Show information about the bot.")
    async def info(self, interaction: discord.Interaction) -> None:
        me = interaction.client.user
        stats = (
            f"**Uptime:** {format_duration(now() - self.bot.started_at)}\n"
            f"**Servers:** {len(self.bot.guilds)}\n"
            f"**Latency:** {round(self.bot.latency * 1000)} ms\n"
            f"**Commands:** {len(self.bot.tree.get_commands())}\n"
            f"**Python:** {platform.python_version()}\n"
            f"**discord.py:** {discord.__version__}"
        )
        view = panel(
            "🤖 MechBot",
            "A small bot built with discord.py.",
            stats,
            thumbnail=me.display_avatar.url,
            footer="Made with discord.py",
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="help", description="List every command.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        lines = "\n".join(
            f"**/{command.name}** {command.description or ''}".rstrip()
            for command in sorted(self.bot.tree.get_commands(), key=lambda cmd: cmd.name)
        )
        view = panel("📖 Commands", "Everything this bot can do.", lines, footer="MechBot")
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
