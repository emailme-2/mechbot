"""Two auto-updating rosters: mechanic and sales.

Each roster is a list of rank roles (top to bottom) the admins set with
/<roster> ranks. /<roster> show prints it; /<roster> display pins a message in a
channel that re-renders itself whenever someone's roles change. Starts blank.
"""

import json
import logging
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import BRAND_COLOR, COLORS, panel

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "roster.json"
DEPTS = ("mechanic", "sales", "both")
DEPT_TITLE = {"mechanic": "🔧 Mechanic", "sales": "🚗 Sales", "both": "📋 Full"}
DEPT_CMD = {"mechanic": "mechroster", "sales": "salesroster", "both": "bothroster"}

# Members holding this role may configure the rosters.
ROSTER_ROLE = 1412488659097358376


def _blank_dept() -> dict:
    return {"roles": [], "display_channel": None, "message_id": None}


def _load() -> dict:
    data = {dept: _blank_dept() for dept in DEPTS}
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            for dept in DEPTS:
                if isinstance(loaded.get(dept), dict):
                    data[dept].update(loaded[dept])
        except (json.JSONDecodeError, OSError):
            pass
    return data


def _save(data: dict) -> None:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as error:
        logger.error("Failed to save roster data: %s", error)


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cfg = _load()

    mechroster = app_commands.Group(name="mechroster", description="Mechanic roster")
    salesroster = app_commands.Group(name="salesroster", description="Sales roster")
    bothroster = app_commands.Group(name="bothroster", description="Combined roster")

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if ROSTER_ROLE in {r.id for r in getattr(interaction.user, "roles", [])}:
            return False
        await interaction.response.send_message(
            view=panel("⛔ Not allowed", "You don't have the role to manage the roster.", color=COLORS["red"]),
            ephemeral=True,
        )
        return True

    # ── Rendering ───────────────────────────────────────────────────────────────
    def _build_view(self, guild, dept) -> discord.ui.LayoutView:
        roles = self.cfg[dept]["roles"]
        shown, blocks, total = set(), [], 0
        for rid in roles:
            role = guild.get_role(rid)
            if not role:
                continue
            members = [m for m in role.members if not m.bot and m.id not in shown]
            if not members:
                continue
            blocks.append((role.name, members))
            shown.update(m.id for m in members)
            total += len(members)

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=BRAND_COLOR)
        container.add_item(discord.ui.TextDisplay(f"## {DEPT_TITLE[dept]} Roster"))
        container.add_item(discord.ui.Separator())

        if not roles:
            container.add_item(discord.ui.TextDisplay(f"No ranks set. Use `/{DEPT_CMD[dept]} ranks`."))
        elif not blocks:
            container.add_item(discord.ui.TextDisplay("No members on the roster yet."))
        else:
            budget, used, truncated = 3600, 0, False
            for role_name, members in blocks:
                block = f"**{role_name}**\n" + "\n".join(m.mention for m in members)
                if used + len(block) > budget or len(container.children) >= 35:
                    truncated = True
                    break
                container.add_item(discord.ui.TextDisplay(block))
                used += len(block)
            if truncated:
                container.add_item(discord.ui.TextDisplay("-# More members not shown (roster too long)."))

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"\U0001F465 **{total}** total\n-# Updates automatically when roles change"
        ))
        view.add_item(container)
        return view

    async def _refresh(self, guild, dept) -> None:
        cfg = self.cfg[dept]
        if not cfg.get("display_channel") or not cfg.get("message_id"):
            return
        channel = guild.get_channel(cfg["display_channel"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(cfg["message_id"])
            await message.edit(view=self._build_view(guild, dept))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    def _parse_roles(self, guild, text):
        ids, invalid = [], []
        for part in filter(None, re.split(r"[\s,]+", text.strip())):
            role = None
            mention = re.fullmatch(r"<@&(\d+)>", part)
            if mention:
                role = guild.get_role(int(mention.group(1)))
            elif part.isdigit():
                role = guild.get_role(int(part))
            else:
                role = discord.utils.find(lambda x: x.name.lower() == part.lower(), guild.roles)
            if role:
                if role.id not in ids:
                    ids.append(role.id)
            else:
                invalid.append(part)
        return ids, invalid

    # ── Shared command bodies ───────────────────────────────────────────────────
    async def _show(self, interaction: discord.Interaction, dept: str):
        if not self.cfg[dept]["roles"]:
            await interaction.response.send_message(
                view=panel(f"{DEPT_TITLE[dept]} Roster", f"No ranks set yet. Use `/{DEPT_CMD[dept]} ranks`.",
                           color=COLORS["red"]),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(view=self._build_view(interaction.guild, dept))

    async def _set_ranks(self, interaction: discord.Interaction, dept: str, roles: str):
        if await self._deny(interaction):
            return
        ids, invalid = self._parse_roles(interaction.guild, roles)
        if invalid:
            await interaction.response.send_message(
                view=panel("Invalid roles", "Couldn't find:\n" + "\n".join(f"• {x}" for x in invalid),
                           color=COLORS["red"]),
                ephemeral=True,
            )
            return
        if not ids:
            await interaction.response.send_message(
                "Mention the rank roles in order (highest first).", ephemeral=True)
            return

        self.cfg[dept]["roles"] = ids
        _save(self.cfg)
        order = "\n".join(f"{i + 1}. {interaction.guild.get_role(r).mention}" for i, r in enumerate(ids))
        await interaction.response.send_message(
            view=panel(f"✅ {DEPT_TITLE[dept]} Ranks Set", f"Top to bottom:\n{order}", color=COLORS["green"]))
        await self._refresh(interaction.guild, dept)

    async def _set_display(self, interaction: discord.Interaction, dept: str, channel: discord.TextChannel):
        if await self._deny(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            message = await channel.send(view=self._build_view(interaction.guild, dept))
        except discord.Forbidden:
            await interaction.followup.send(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return
        self.cfg[dept]["display_channel"] = channel.id
        self.cfg[dept]["message_id"] = message.id
        _save(self.cfg)
        await interaction.followup.send(
            f"✅ {DEPT_TITLE[dept]} roster set up in {channel.mention}. It auto-updates when roles change.",
            ephemeral=True,
        )

    # ── Mechanic roster ─────────────────────────────────────────────────────────
    @mechroster.command(name="show", description="Show the mechanic roster")
    @app_commands.guild_only()
    async def mech_show(self, interaction: discord.Interaction):
        await self._show(interaction, "mechanic")

    @mechroster.command(name="ranks", description="Set the mechanic rank roles (highest first)")
    @app_commands.describe(roles="Mention the rank roles in order, highest first")
    @app_commands.guild_only()
    async def mech_ranks(self, interaction: discord.Interaction, roles: str):
        await self._set_ranks(interaction, "mechanic", roles)

    @mechroster.command(name="display", description="Post an auto-updating mechanic roster in a channel")
    @app_commands.describe(channel="The channel to post it in")
    @app_commands.guild_only()
    async def mech_display(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set_display(interaction, "mechanic", channel)

    # ── Sales roster ────────────────────────────────────────────────────────────
    @salesroster.command(name="show", description="Show the sales roster")
    @app_commands.guild_only()
    async def sales_show(self, interaction: discord.Interaction):
        await self._show(interaction, "sales")

    @salesroster.command(name="ranks", description="Set the sales rank roles (highest first)")
    @app_commands.describe(roles="Mention the rank roles in order, highest first")
    @app_commands.guild_only()
    async def sales_ranks(self, interaction: discord.Interaction, roles: str):
        await self._set_ranks(interaction, "sales", roles)

    @salesroster.command(name="display", description="Post an auto-updating sales roster in a channel")
    @app_commands.describe(channel="The channel to post it in")
    @app_commands.guild_only()
    async def sales_display(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set_display(interaction, "sales", channel)

    # ── Combined roster ─────────────────────────────────────────────────────────
    @bothroster.command(name="show", description="Show the combined roster")
    @app_commands.guild_only()
    async def both_show(self, interaction: discord.Interaction):
        await self._show(interaction, "both")

    @bothroster.command(name="ranks", description="Set the combined roster rank roles (highest first)")
    @app_commands.describe(roles="Mention the rank roles in order, highest first")
    @app_commands.guild_only()
    async def both_ranks(self, interaction: discord.Interaction, roles: str):
        await self._set_ranks(interaction, "both", roles)

    @bothroster.command(name="display", description="Post an auto-updating combined roster in a channel")
    @app_commands.describe(channel="The channel to post it in")
    @app_commands.guild_only()
    async def both_display(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set_display(interaction, "both", channel)

    # ── Auto-update ─────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return
        changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        for dept in DEPTS:
            cfg = self.cfg[dept]
            if cfg.get("message_id") and changed & set(cfg.get("roles", [])):
                await self._refresh(after.guild, dept)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        for dept in DEPTS:
            if self.cfg[dept].get("message_id"):
                await self._refresh(member.guild, dept)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roster(bot))
