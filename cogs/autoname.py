"""Auto-name channel: rename members who post their name and bank number.

Point the bot at a channel with /autoname channel. Each message there is read as
'<name> <number>', and the member's nickname becomes 'Name | number'. Handy for a
FiveM bank-registration channel. Needs the Message Content intent to read posts.
"""

import json
import logging
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / 'autoname.json'
NICK_MAX = 32  # Discord's hard limit on nickname length.

# Name first, then a trailing run of digits (the account number). Any spaces,
# dashes, pipes or commas between the two are treated as separators and dropped.
PATTERN = re.compile(r'^\s*(.+?)[\s\-|,]*(\d{2,})\s*$')


def _load() -> dict:
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    try:
        with DATA_FILE.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as error:
        logger.error('Failed to save autoname data: %s', error)


def _build_nick(name: str, number: str) -> str:
    """'Name | number', trimming the name if needed so the number always fits."""
    suffix = f' | {number}'
    if len(name) + len(suffix) > NICK_MAX:
        name = name[:NICK_MAX - len(suffix)].rstrip()
    return f'{name}{suffix}'


class AutoName(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # { guild_id_str: channel_id_int }
        self.channels: dict[str, int] = _load()

    group = app_commands.Group(
        name='autoname',
        description='Auto-rename members who post their name and bank number',
        guild_only=True,
        default_permissions=discord.Permissions(manage_nicknames=True),
    )

    @group.command(name='channel', description='Set the channel that renames members to "Name | number"')
    @app_commands.describe(channel='The channel people post their name and bank number in')
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.channels[str(interaction.guild_id)] = channel.id
        _save(self.channels)
        await interaction.response.send_message(
            f'✅ Members who post in {channel.mention} will be renamed to "Name | number".',
            ephemeral=True,
        )

    @group.command(name='disable', description='Stop auto-renaming in this server')
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def disable(self, interaction: discord.Interaction):
        if self.channels.pop(str(interaction.guild_id), None) is None:
            await interaction.response.send_message('Auto-naming is not set up here.', ephemeral=True)
            return
        _save(self.channels)
        await interaction.response.send_message('✅ Auto-naming turned off.', ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if self.channels.get(str(message.guild.id)) != message.channel.id:
            return
        if not isinstance(message.author, discord.Member):
            return

        match = PATTERN.match(message.content)
        if not match:
            return
        name = ' '.join(match.group(1).split()).title()
        if not any(c.isalpha() for c in name):  # a bare number is not a name
            return
        nick = _build_nick(name, match.group(2))

        try:
            await message.author.edit(nick=nick, reason='Auto-name channel')
        except discord.Forbidden:
            # Missing Manage Nicknames, or the member outranks the bot / is the owner.
            await self._react(message, '⚠️')
            return
        except discord.HTTPException:
            return
        await self._react(message, '✅')

    @staticmethod
    async def _react(message: discord.Message, emoji: str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoName(bot))
