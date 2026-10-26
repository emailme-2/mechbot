"""Completed-work tracker for two channels: mechanic work and car sales.

Point the bot at the channels with /mechanic and /sale. When someone posts an
invoice screenshot in either, the bot OCRs it (via OCR.space), reads the
'Total + Fees' amount, counts it as one car for that member in that category,
and reacts with a checkmark. Totals are tracked per member and per category,
weekly (reset every Monday) and lifetime. Check a member with /checksales.

Needs the Message Content intent (to see attachments) and an OCR.space API key in
the OCRSPACE_API_KEY environment variable. Get a free key at https://ocr.space/ocrapi.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from core import panel

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / 'sales.json'
OCR_URL = 'https://api.ocr.space/parse/image'

CATEGORIES = ('mechanic', 'sale')
CATEGORY_LABELS = {'mechanic': '🔧 Mechanic', 'sale': '🚗 Sales'}

# Rank roles per department (highest first), shown on /checksales.
DEPT_RANKS = {
    'mechanic': [(1252025838405423155, 'Master Tech'), (1358223305458450593, 'Mechanic')],
    'sale': [(1289686368238440589, 'Supervisor'), (1289685969166930013, 'Salesman')],
}


def _rank_name(member, cat):
    held = {r.id for r in getattr(member, 'roles', [])}
    for rid, name in DEPT_RANKS.get(cat, []):
        if rid in held:
            return name
    return None

# Commission rate per rank. Set to the real percentages once known; 0 hides it.
DEFAULT_COMMISSION = 0.0
RANK_COMMISSION = {
    'Mechanic': 0.0,
    'Master Tech': 0.0,
    'Salesman': 0.10,
    'Supervisor': 0.10,
}


def _rate(rank) -> float:
    return RANK_COMMISSION.get(rank, DEFAULT_COMMISSION)


def _commission(total: int, rank=None) -> int:
    return round(total * _rate(rank))


def _rank_order(cat: str, dept: dict) -> list:
    """Ranks present in `dept`, lowest ladder rank first, then any extras."""
    ladder = [name for _, name in reversed(DEPT_RANKS.get(cat, []))]
    known = [r for r in ladder if r in dept]
    return known + [r for r in dept if r not in ladder]

# 'helloworld' is OCR.space's shared demo key: rate-limited and unreliable, so set
# your own free key in OCRSPACE_API_KEY. It only serves as a last-resort fallback.
API_KEY = os.getenv('OCRSPACE_API_KEY', 'helloworld')

# Dollar amounts like $38,141 or 38.141 (OCR sometimes reads the comma as a dot).
AMOUNT_RE = re.compile(r'\$?\s*([\d][\d.,]{1,})')


def _load() -> dict:
    data = {}
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    # Migrate old per-department totals into a single "(earlier)" rank bucket,
    # so totals recorded before rank tracking aren't lost.
    for g in data.values():
        if not isinstance(g, dict):
            continue
        for user in g.get('users', {}).values():
            for cat in CATEGORIES:
                d = user.get(cat)
                if isinstance(d, dict) and 'weekly_cars' in d:
                    user[cat] = {'(earlier)': d}
    return data


def _save(data: dict) -> None:
    try:
        with DATA_FILE.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as error:
        logger.error('Failed to save sales data: %s', error)


def _blank() -> dict:
    return {'weekly_cars': 0, 'weekly_total': 0, 'lifetime_cars': 0, 'lifetime_total': 0}


def _week_start() -> str:
    """ISO date of this week's Monday, in UTC. Used to detect a new week."""
    today = datetime.now(timezone.utc)
    return (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')


def _amount_from(fragment: str):
    digits = re.sub(r'\D', '', fragment)
    return int(digits) if digits else None


def extract_total(text: str):
    """Find the 'Total + Fees' amount, falling back to the largest amount seen."""
    for line in text.splitlines():
        low = line.lower()
        if 'total' in low and 'fee' in low:
            match = AMOUNT_RE.search(line)
            if match:
                value = _amount_from(match.group(1))
                if value:
                    return value

    amounts = [v for m in AMOUNT_RE.finditer(text) if (v := _amount_from(m.group(1)))]
    # Total + Fees is the sum of everything, so it's always the largest number.
    return max(amounts) if amounts else None


class Sales(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.data: dict = _load()

    def _guild(self, guild_id: int) -> dict:
        """Guild record, resetting the weekly tallies when a new week has started."""
        g = self.data.setdefault(
            str(guild_id), {'channels': {}, 'week_start': _week_start(), 'users': {}}
        )
        if g.get('week_start') != _week_start():
            g['week_start'] = _week_start()
            for user in g['users'].values():
                for cat in CATEGORIES:
                    for stats in (user.get(cat) or {}).values():
                        stats['weekly_cars'] = 0
                        stats['weekly_total'] = 0
        return g

    async def _set_channel(self, interaction: discord.Interaction, category: str, channel: discord.TextChannel):
        self._guild(interaction.guild_id).setdefault('channels', {})[category] = channel.id
        _save(self.data)
        await interaction.response.send_message(
            f'✅ Tracking {CATEGORY_LABELS[category]} work from {channel.mention}.', ephemeral=True,
        )

    async def _read_total(self, attachment: discord.Attachment):
        """Send the image to OCR.space and pull out the Total + Fees amount."""
        try:
            image = await attachment.read()
        except discord.HTTPException:
            return None

        form = aiohttp.FormData()
        form.add_field('apikey', API_KEY)
        form.add_field('language', 'eng')
        form.add_field('OCREngine', '3')  # engine 3 reads the dark-theme invoice far better
        form.add_field('scale', 'true')
        form.add_field('file', image, filename=attachment.filename,
                       content_type=attachment.content_type or 'image/png')

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(OCR_URL, data=form) as resp:
                    result = await resp.json(content_type=None)
        except (aiohttp.ClientError, json.JSONDecodeError, TimeoutError) as error:
            logger.warning('OCR request failed: %s', error)
            return None

        if result.get('IsErroredOnProcessing'):
            logger.warning('OCR error: %s', result.get('ErrorMessage'))
            return None
        parsed = result.get('ParsedResults') or []
        if not parsed:
            return None
        return extract_total(parsed[0].get('ParsedText', ''))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        g = self.data.get(str(message.guild.id))
        if not g:
            return
        channels = g.get('channels', {})
        category = next((c for c, cid in channels.items() if cid == message.channel.id), None)
        if category is None:
            return
        image = next((a for a in message.attachments if (a.content_type or '').startswith('image/')), None)
        if image is None:
            return

        total = await self._read_total(image)
        if total is None:
            await self._react(message, '⚠️')  # couldn't read a total, not counted
            return

        g = self._guild(message.guild.id)
        user = g['users'].setdefault(str(message.author.id), {})
        dept = user.setdefault(category, {})
        rank = _rank_name(message.author, category) or 'Unranked'
        stats = dept.setdefault(rank, _blank())
        stats['weekly_cars'] += 1
        stats['weekly_total'] += total
        stats['lifetime_cars'] += 1
        stats['lifetime_total'] += total
        _save(self.data)

        await self._react(message, '✅')

        if category == 'sale':
            commission = _commission(total, rank)
            if commission:
                try:
                    await message.reply(
                        f'💰 {message.author.mention} earned **${commission:,}** commission '
                        f'({round(_rate(rank) * 100)}% of ${total:,}).',
                        mention_author=False,
                    )
                except discord.HTTPException:
                    pass

    @staticmethod
    async def _react(message: discord.Message, emoji: str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass

    @app_commands.command(name='mechanic', description='Set the mechanic completed-work channel the bot watches')
    @app_commands.describe(channel='Channel where mechanic invoice screenshots are posted')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mechanic(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set_channel(interaction, 'mechanic', channel)

    @app_commands.command(name='sale', description='Set the car-sales completed-work channel the bot watches')
    @app_commands.describe(channel='Channel where sales invoice screenshots are posted')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sale(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set_channel(interaction, 'sale', channel)

    @app_commands.command(name='checksales', description='Check a member\'s mechanic and sales totals (weekly and lifetime)')
    @app_commands.describe(user='Whose totals to check (defaults to you)')
    async def checksales(self, interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        g = self._guild(interaction.guild_id)
        _save(self.data)  # persist a possible weekly reset
        stats = g['users'].get(str(target.id))

        if not stats:
            view = panel(
                '📊 Completed Work',
                f'{target.mention} has no recorded work yet.',
                thumbnail=target.display_avatar.url,
            )
            await interaction.response.send_message(view=view)
            return

        blocks = []
        for cat in CATEGORIES:
            dept = stats.get(cat) or {}
            lines = [f"### {CATEGORY_LABELS[cat]}"]
            current = _rank_name(target, cat)
            if current:
                lines.append(f"**Current rank:** {current}")

            if not dept:
                lines.append("No recorded work.")
                blocks.append("\n".join(lines))
                continue

            week_comm = life_comm = 0
            for rank in _rank_order(cat, dept):
                r = dept[rank]
                rate = _rate(rank)
                w, l = _commission(r['weekly_total'], rank), _commission(r['lifetime_total'], rank)
                week_comm += w
                life_comm += l
                pct = f" ({round(rate * 100)}%)" if rate else ""
                wc = f" (${w:,} commission)" if rate else ""
                lc = f" (${l:,} commission)" if rate else ""
                lines.append(
                    f"\n**{rank}**{pct}\n"
                    f"This week: {r['weekly_cars']} cars, ${r['weekly_total']:,}{wc}\n"
                    f"Lifetime: {r['lifetime_cars']} cars, ${r['lifetime_total']:,}{lc}"
                )

            if life_comm or week_comm:
                if cat == 'sale':
                    lines.append("\n**Your commissions**")
                    lines.append(f"**Sales Commission:** ${life_comm:,}")
                lines.append(f"**Total commission:** ${week_comm:,} this week, ${life_comm:,} lifetime")
            blocks.append("\n".join(lines))

        view = panel(
            '📊 Completed Work',
            f'Record for {target.mention}',
            *blocks,
            thumbnail=target.display_avatar.url,
            footer='Weekly totals reset every Monday',
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Sales(bot))
