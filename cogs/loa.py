import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

ACCENT_COLOR = 0xF3C22E  # Royal gold, same brand accent the /message panels use.
DATA_FILE = Path(__file__).resolve().parent.parent / 'loa_panels.json'

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
        logger.error('Failed to save LOA panel data: %s', error)


class LOAButton(discord.ui.DynamicItem[discord.ui.Button], template=r'loa:open'):
    """The button that lives on the sticky panel. Opens the request form."""

    def __init__(self):
        super().__init__(
            discord.ui.Button(
                label='LOA',
                style=discord.ButtonStyle.primary,
                emoji='🗓️',
                custom_id='loa:open',
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('LOA')
        if cog is None:
            await interaction.response.send_message('The LOA form is unavailable right now.', ephemeral=True)
            return
        # Pick a department first; the form then opens with that choice attached.
        await interaction.response.send_message(
            'Which department are you requesting leave from?',
            view=DepartmentView(cog),
            ephemeral=True,
        )


class LOAModal(discord.ui.Modal, title='Request a leave of absence'):
    def __init__(self, cog: 'LOA', *, department: str):
        super().__init__()
        self.cog = cog
        self.department = department
        self.starting = discord.ui.TextInput(
            label='Starting',
            placeholder='e.g. tomorrow, or Oct 20',
            max_length=100,
            required=True,
        )
        self.ending = discord.ui.TextInput(
            label='Ending',
            placeholder='e.g. Monday, or Oct 27',
            max_length=100,
            required=True,
        )
        self.reason = discord.ui.TextInput(
            label='Reason',
            style=discord.TextStyle.paragraph,
            placeholder='Out of town, exams, work, holiday, etc.',
            max_length=500,
            required=True,
        )
        self.add_item(self.starting)
        self.add_item(self.ending)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.submit_request(
            interaction,
            department=self.department,
            starting=str(self.starting).strip(),
            ending=str(self.ending).strip(),
            reason=str(self.reason).strip(),
        )


class DepartmentSelect(discord.ui.Select):
    """Dropdown for choosing which department the leave is for."""

    def __init__(self, cog: 'LOA'):
        self.cog = cog
        super().__init__(
            placeholder='Choose your department',
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label='Dealership', value='Dealership', emoji='🚗'),
                discord.SelectOption(label='Mechanic', value='Mechanic', emoji='🔧'),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LOAModal(self.cog, department=self.values[0]))


class DepartmentView(discord.ui.View):
    """Short-lived ephemeral view that holds the department dropdown."""

    def __init__(self, cog: 'LOA'):
        super().__init__(timeout=120)
        self.add_item(DepartmentSelect(cog))


class LOA(commands.Cog):
    """A sticky panel with an LOA button. Members tap it to post a leave request."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # { channel_id_str: { "message_id": int } }
        self.panels: dict[str, dict] = _load_data()
        # Channels currently being reposted, so the listener doesn't loop on itself.
        self._reposting: set[int] = set()
        # Channel id -> the pending repost task, so a burst queues only one.
        self._pending: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        try:
            self.bot.add_dynamic_items(LOAButton)
        except Exception as error:
            logger.warning('Failed to register LOA button: %s', error)

    async def cog_unload(self):
        for task in list(self._pending.values()):
            task.cancel()
        self._pending.clear()

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, 'guild_permissions', None)
        return bool(perms and (perms.administrator or perms.manage_messages))

    # --- Rendering ----------------------------------------------------------------

    def _build_panel(self) -> discord.ui.LayoutView:
        """The sticky panel that holds the LOA button."""
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        container.add_item(discord.ui.TextDisplay('## 🗓️ Request a Leave of Absence'))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            'Going to be away? Tap **LOA** below, pick your department, and fill in '
            'your dates and reason. Your request gets posted right here in this channel.'
        ))
        container.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        row.add_item(LOAButton())
        container.add_item(row)

        view.add_item(container)
        return view

    def _build_request(self, user: discord.abc.User, *, department, starting, ending, reason) -> discord.ui.LayoutView:
        """The posted leave request, in the same gold panel style."""
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        container.add_item(discord.ui.TextDisplay('## 🗓️ Leave of Absence'))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f'**Member:** {user.mention}\n'
            f'**Department:** {department}\n\n'
            f'**Starting:** {starting}\n'
            f'**Ending:** {ending}\n'
            f'**Reason:** {reason}'
        ))
        stamp = discord.utils.format_dt(discord.utils.utcnow(), 'R')
        container.add_item(discord.ui.TextDisplay(f'-# Submitted {stamp}'))

        view.add_item(container)
        return view

    # --- Sticky handling ----------------------------------------------------------

    async def _repost_panel(self, channel: discord.abc.Messageable):
        """Delete the old panel in this channel and post a fresh one at the bottom."""
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

            sent = await channel.send(view=self._build_panel())
            self.panels[key]['message_id'] = sent.id
            _save_data(self.panels)
        except Exception as error:
            logger.error('Error reposting LOA panel in channel %s: %s', channel.id, error)
        finally:
            self._reposting.discard(channel.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs, bots, and channels without a panel. The request the bot
        # posts is re-stickied directly in submit_request, so bot messages are
        # safe to skip here and this avoids a repost loop.
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

    # --- Interaction handlers -----------------------------------------------------

    async def submit_request(self, interaction: discord.Interaction, *, department, starting, ending, reason):
        channel = interaction.channel
        if channel is None or not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                "I can't post your request here, the channel is missing permissions.", ephemeral=True,
            )
            return

        await interaction.response.send_message('✅ Your LOA request has been posted.', ephemeral=True)

        await channel.send(
            view=self._build_request(
                interaction.user, department=department, starting=starting, ending=ending, reason=reason,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        # Keep the button panel as the last message in the channel.
        await self._repost_panel(channel)

    # --- Commands -----------------------------------------------------------------

    @app_commands.command(name='loachannel', description='Set the channel where the LOA button panel stays at the bottom')
    @app_commands.describe(channel='The channel to post the LOA panel in')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def loachannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return

        key = str(channel.id)
        existing = self.panels.get(key)
        if existing and existing.get('message_id'):
            try:
                old_msg = await channel.fetch_message(existing['message_id'])
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        await interaction.response.send_message(f'✅ LOA panel set in {channel.mention}.', ephemeral=True)

        sent = await channel.send(view=self._build_panel())
        self.panels[key] = {'message_id': sent.id}
        _save_data(self.panels)
        logger.info('LOA panel set in #%s (%s) by %s', channel.name, channel.id, interaction.user)

    @app_commands.command(name='loaremove', description='Remove the LOA button panel from a channel')
    @app_commands.describe(channel='The channel to remove the LOA panel from (defaults to here)')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def loaremove(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        key = str(channel.id)
        entry = self.panels.get(key)
        if not entry:
            await interaction.response.send_message(f'There is no LOA panel in {channel.mention}.', ephemeral=True)
            return

        if entry.get('message_id'):
            try:
                msg = await channel.fetch_message(entry['message_id'])
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        del self.panels[key]
        _save_data(self.panels)
        await interaction.response.send_message(f'✅ LOA panel removed from {channel.mention}.', ephemeral=True)
        logger.info('LOA panel removed from #%s (%s) by %s', channel.name, channel.id, interaction.user)


async def setup(bot: commands.Bot):
    await bot.add_cog(LOA(bot))
