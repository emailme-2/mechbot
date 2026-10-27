"""A sticky guide that explains the ✅ and ⚠️ reactions on invoice screenshots.

The Sales cog (cogs/sales.py) reacts to every invoice image posted in a tracked
channel: ✅ when it read the total and counted the car, ⚠️ when it couldn't read
a total. New members don't know what those mean, so /salesmessage drops a short
guide in the channel and keeps it at the bottom as people post, in as many
channels as you set it up in.

Keeping a message at the bottom means deleting and reposting it, so a busy
channel could rack up API calls fast. Reposts are batched: one per quiet window
(REPOST_DELAY_SECONDS) rather than one per message, which is what keeps this off
Discord's rate limits. This mirrors the sticky handling in cogs/loa.py.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core import panel

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / 'sales_messages.json'

# Batch panel reposts during a burst of messages: one repost per quiet window
# instead of one per message, so a chatty channel doesn't get rate limited.
REPOST_DELAY_SECONDS = 3.0


def _load_data() -> dict:
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_data(data: dict):
    try:
        with DATA_FILE.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as error:
        logger.error('Failed to save sales message data: %s', error)


def _build_panel() -> discord.ui.LayoutView:
    """The guide shown to anyone posting invoices, explaining the two reactions."""
    return panel(
        '📋 How invoice tracking works',
        'Post your invoice screenshot in this channel and the bot reads it for '
        'you. It then adds one of two reactions to your message:',
        "✅  **Counted.** The bot read the total and logged the car under your "
        "name, for this week and all-time.\n\n"
        "⚠️  **Couldn't read it.** No total was found on the image, so nothing "
        "was counted. Post a clear, full screenshot and the bot will try again.",
        'Only image attachments are read. Check your own totals any time with '
        '`/checksales`.',
        footer='This note stays at the bottom of the channel.',
    )


class SalesMessage(commands.Cog):
    """Keeps the invoice-reaction guide at the bottom of one or more channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # { channel_id_str: { "message_id": int } }
        self.panels: dict[str, dict] = _load_data()
        # Channels mid-repost, so the listener doesn't loop on its own message.
        self._reposting: set[int] = set()
        # Channel id -> the pending repost task, so a burst queues only one.
        self._pending: dict[int, asyncio.Task] = {}

    async def cog_unload(self):
        for task in list(self._pending.values()):
            task.cancel()
        self._pending.clear()

    # --- Sticky handling ----------------------------------------------------------

    async def _repost_panel(self, channel: discord.abc.Messageable):
        """Delete the old guide in this channel and post a fresh one at the bottom."""
        key = str(channel.id)
        entry = self.panels.get(key)
        if entry is None:
            return
        if channel.id in self._reposting:
            return
        self._reposting.add(channel.id)
        try:
            old_id = entry.get('message_id')
            if old_id:
                try:
                    # Delete via a partial message so we don't spend a fetch call first.
                    await channel.get_partial_message(old_id).delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            sent = await channel.send(view=_build_panel())
            self.panels[key]['message_id'] = sent.id
            _save_data(self.panels)
        except Exception as error:
            logger.error('Error reposting sales guide in channel %s: %s', channel.id, error)
        finally:
            self._reposting.discard(channel.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs, bots (our own repost included, so we don't loop), and
        # channels with no guide set.
        if not message.guild or message.author.bot:
            return

        entry = self.panels.get(str(message.channel.id))
        if not entry or message.id == entry.get('message_id'):
            return

        channel = message.channel
        # A repost is already queued for this channel; let it handle this message.
        if channel.id in self._pending:
            return
        self._pending[channel.id] = self.bot.loop.create_task(self._repost_after_delay(channel))

    async def _repost_after_delay(self, channel: discord.abc.Messageable):
        try:
            await asyncio.sleep(REPOST_DELAY_SECONDS)
            await self._repost_panel(channel)
        finally:
            self._pending.pop(channel.id, None)

    # --- Commands -----------------------------------------------------------------

    @app_commands.command(
        name='salesmessage',
        description='Keep a sticky guide for the ✅ / ⚠️ invoice reactions in a channel',
    )
    @app_commands.describe(channel='Channel to keep the guide in (defaults to where you run this)')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    async def salesmessage(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                'Run this in a text channel, or pass one with the channel option.', ephemeral=True,
            )
            return
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return

        key = str(channel.id)
        existing = self.panels.get(key)
        if existing and existing.get('message_id'):
            # Already set here: clear the old copy so we don't leave two behind.
            try:
                old_msg = await channel.fetch_message(existing['message_id'])
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        await interaction.response.send_message(
            f'✅ Invoice guide set in {channel.mention}. It will stay at the bottom as people post.',
            ephemeral=True,
        )

        sent = await channel.send(view=_build_panel())
        self.panels[key] = {'message_id': sent.id}
        _save_data(self.panels)
        logger.info('Sales guide set in #%s (%s) by %s', channel.name, channel.id, interaction.user)

    @app_commands.command(name='salesmessageremove', description='Remove the invoice-reaction guide from a channel')
    @app_commands.describe(channel='Channel to remove the guide from (defaults to here)')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    async def salesmessageremove(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        key = str(channel.id)
        entry = self.panels.get(key)
        if not entry:
            await interaction.response.send_message(f'There is no invoice guide in {channel.mention}.', ephemeral=True)
            return

        # Stop a queued repost so it can't recreate the message after removal.
        pending = self._pending.pop(channel.id, None)
        if pending:
            pending.cancel()

        if entry.get('message_id'):
            try:
                msg = await channel.fetch_message(entry['message_id'])
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        del self.panels[key]
        _save_data(self.panels)
        await interaction.response.send_message(f'✅ Invoice guide removed from {channel.mention}.', ephemeral=True)
        logger.info('Sales guide removed from #%s (%s) by %s', channel.name, channel.id, interaction.user)


async def setup(bot: commands.Bot):
    await bot.add_cog(SalesMessage(bot))
