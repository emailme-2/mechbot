"""MechBot - a small Discord bot built on slash commands and embeds."""

import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands

try:
    from dotenv import load_dotenv
except ImportError:  # hosting panels often inject env vars directly
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).with_name(".env"))

BRAND_COLOR = 0x5865F2
COLORS = {
    "blurple": 0x5865F2,
    "green": 0x57F287,
    "yellow": 0xFEE75C,
    "red": 0xED4245,
    "purple": 0x9B59B6,
    "dark": 0x2B2D31,
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def format_duration(delta: timedelta) -> str:
    total = max(int(delta.total_seconds()), 0)
    days, rest = divmod(total, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, seconds = divmod(rest, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def base_embed(title: str, description: str = "", color: int = BRAND_COLOR) -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=color, timestamp=now())


class MechBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.started_at = now()

    async def setup_hook(self) -> None:
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


bot = MechBot()


@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction) -> None:
    latency = round(bot.latency * 1000)
    color = COLORS["green"] if latency < 120 else COLORS["yellow"] if latency < 300 else COLORS["red"]

    embed = base_embed("🏓 Pong!", f"Gateway latency: **{latency} ms**", color)
    embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="hello", description="Say hello with a welcome embed.")
@app_commands.describe(member="Who to greet (defaults to you)")
async def hello(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
    target = member or interaction.user

    embed = base_embed("👋 Hello!", f"Hey {target.mention}, welcome aboard!")
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Greeted by", value=interaction.user.mention, inline=True)
    embed.add_field(name="When", value=discord.utils.format_dt(now(), "R"), inline=True)
    embed.set_footer(text="MechBot", icon_url=interaction.client.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="info", description="Show information about the bot.")
async def info(interaction: discord.Interaction) -> None:
    me = interaction.client.user
    embed = base_embed("🤖 MechBot", "A small demo bot running on slash commands and embeds.")
    embed.set_author(name=me.name, icon_url=me.display_avatar.url)
    embed.set_thumbnail(url=me.display_avatar.url)
    embed.add_field(name="Uptime", value=format_duration(now() - bot.started_at), inline=True)
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)} ms", inline=True)
    embed.add_field(name="Commands", value=str(len(bot.tree.get_commands())), inline=True)
    embed.add_field(name="Python", value=platform.python_version(), inline=True)
    embed.add_field(name="discord.py", value=discord.__version__, inline=True)
    embed.set_footer(text="Made with discord.py", icon_url=me.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="server", description="Show information about this server.")
async def server(interaction: discord.Interaction) -> None:
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
    embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Tier {guild.premium_tier})", inline=True)
    embed.add_field(name="Channels", value=f"{len(guild.channels):,}", inline=True)
    embed.add_field(name="Roles", value=f"{len(guild.roles):,}", inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
    embed.set_footer(text=f"Server ID: {guild.id}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="embed", description="Build a custom embed.")
@app_commands.describe(title="Embed title", description="Embed body text", color="Accent color")
@app_commands.choices(
    color=[app_commands.Choice(name=name.title(), value=name) for name in COLORS]
)
async def custom_embed(
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


@bot.tree.command(name="help", description="List every command.")
async def help_command(interaction: discord.Interaction) -> None:
    embed = base_embed("📖 Commands", "Everything this bot can do.")
    for command in sorted(bot.tree.get_commands(), key=lambda cmd: cmd.name):
        embed.add_field(name=f"/{command.name}", value=command.description or "No description", inline=False)
    embed.set_footer(text="MechBot", icon_url=interaction.client.user.display_avatar.url)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    print(f"Command error: {error!r}")

    embed = base_embed("Something went wrong", "That command failed. Please try again in a moment.", COLORS["red"])
    embed.set_footer(text=type(error).__name__)

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and paste your bot token."
        )
    bot.run(token)


if __name__ == "__main__":
    main()
