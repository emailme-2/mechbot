"""The MechBot client: discovers cogs in the cogs/ folder, loads them, and syncs slash commands."""

import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, base_embed, now

COGS_DIR = Path(__file__).with_name("cogs")


class MechTree(app_commands.CommandTree):
    """Command tree with one shared error handler, so a failing command never goes silent."""

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        print(f"Command error: {error!r}")

        embed = base_embed("Something went wrong", "That command failed. Please try again in a moment.", COLORS["red"])
        embed.set_footer(text=type(error).__name__)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class MechBot(commands.Bot):
    def __init__(self) -> None:
        # message_content lets the bot read what people type (needed to react to
        # keywords). It's a privileged intent: also enable it in the Developer
        # Portal under Bot -> Privileged Gateway Intents, or message text is empty.
        intents = discord.Intents.default()
        intents.message_content = True

        # command_prefix is required but unused: this bot is slash-command only.
        super().__init__(
            command_prefix="!",
            intents=intents,
            tree_cls=MechTree,
        )
        self.started_at = now()

    async def setup_hook(self) -> None:
        await self.load_cogs()
        await self.sync_commands()

    async def load_cogs(self) -> None:
        """Load every cogs/*.py file. Names starting with '_' are skipped (templates, helpers)."""
        for path in sorted(COGS_DIR.glob("*.py")):
            if path.stem.startswith("_"):
                continue
            await self.load_extension(f"cogs.{path.stem}")
            print(f"Loaded cog: {path.stem}")

    async def sync_commands(self) -> None:
        guild_id = os.getenv("GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash command(s) to guild {guild_id}")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s) globally (may take up to 1 hour to appear)")

    async def on_ready(self) -> None:
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="/help"),
        )
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} guild(s) - bot is ONLINE")
