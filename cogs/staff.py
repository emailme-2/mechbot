"""Mech-shop staff management: /hire, /promote, /demote.

Only two people can run these (the owners). Each department is a rank ladder the
bot manages; the Manager roles above them are assigned manually and left alone.
Hiring/promoting also keeps the shared Accepted role and the department role in
sync. The bot needs Manage Roles, with its own role above every role listed here.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, panel

# Who may run these commands.
ALLOWED_USERS = {1317971108829597746, 1275730902105849949}

# Rank ladders, lowest to highest (the Manager tier above these is manual).
MECH_LADDER = [1358223305458450593, 1252025838405423155]   # Mechanic, Master Tech
SALES_LADDER = [1289685969166930013, 1289686368238440589]  # Autos Salesman, Autos Supervisor
LADDERS = {"mechanic": MECH_LADDER, "sales": SALES_LADDER}

RANK_NAMES = {
    1358223305458450593: "Mechanic",
    1252025838405423155: "Master Tech",
    1289685969166930013: "Autos Salesman",
    1289686368238440589: "Autos Supervisor",
}

ACCEPTED = 1412165063527366687                              # shared by both departments
DEPT_ROLE = {"mechanic": 1298451074423853117, "sales": 1298450888846999583}  # [Mechanic], Dealer

ALL_RANKS = set(MECH_LADDER) | set(SALES_LADDER)
# Every role the bot owns the state of, so hire/fire can wipe a clean slate.
ALL_MANAGED = ALL_RANKS | {ACCEPTED} | set(DEPT_ROLE.values())

HIRE_CHOICES = [app_commands.Choice(name=RANK_NAMES[rid], value=str(rid)) for rid in ALL_RANKS]


def _dept_of(role_id: int) -> str:
    return "mechanic" if role_id in MECH_LADDER else "sales"


def _current_rank(member: discord.Member):
    """The member's managed rank as (dept, tier, role_id), or None if not employed."""
    member_role_ids = {r.id for r in member.roles}
    for dept, ladder in LADDERS.items():
        for tier, rid in enumerate(ladder):
            if rid in member_role_ids:
                return dept, tier, rid
    return None


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in ALLOWED_USERS:
            return False
        view = panel("⛔ Not allowed", "You can't use this command.", color=COLORS["red"])
        await interaction.response.send_message(view=view, ephemeral=True)
        return True

    async def _apply_roles(self, member: discord.Member, add_ids, remove_ids) -> str | None:
        """Add/remove the given role ids. Returns None on success, else an error key."""
        guild = member.guild
        add = [role for rid in add_ids if (role := guild.get_role(rid))]
        remove = [role for rid in remove_ids if (role := guild.get_role(rid))]
        try:
            if add:
                await member.add_roles(*add, reason="Staff command")
            if remove:
                await member.remove_roles(*remove, reason="Staff command")
        except discord.Forbidden:
            return "forbidden"
        except discord.HTTPException:
            return "error"
        return None

    async def _report_role_error(self, interaction: discord.Interaction, key: str) -> None:
        text = {
            "forbidden": "I need **Manage Roles**, and my role must sit above those roles in Server Settings.",
            "error": "Discord rejected the role change. Try again in a moment.",
        }[key]
        view = panel("Couldn't update roles", text, color=COLORS["red"])
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="hire", description="Hire a member at a rank (sets all their shop roles)")
    @app_commands.describe(member="Who to hire", rank="Which rank to give them")
    @app_commands.choices(rank=HIRE_CHOICES)
    @app_commands.guild_only()
    async def hire(self, interaction: discord.Interaction, member: discord.Member, rank: app_commands.Choice[str]):
        if await self._deny(interaction):
            return
        await interaction.response.defer()

        role_id = int(rank.value)
        dept = _dept_of(role_id)
        desired = {role_id, ACCEPTED, DEPT_ROLE[dept]}
        held = {r.id for r in member.roles}

        error = await self._apply_roles(member, desired - held, (ALL_MANAGED & held) - desired)
        if error:
            await self._report_role_error(interaction, error)
            return

        view = panel(
            "✅ Hired",
            f"{member.mention} is now **{RANK_NAMES[role_id]}**.",
            color=COLORS["green"],
            footer=f"By {interaction.user.display_name}",
        )
        await interaction.followup.send(view=view)

    @app_commands.command(name="promote", description="Promote a member one rank up in their department")
    @app_commands.describe(member="Who to promote")
    @app_commands.guild_only()
    async def promote(self, interaction: discord.Interaction, member: discord.Member):
        if await self._deny(interaction):
            return

        current = _current_rank(member)
        if current is None:
            view = panel("Not employed", f"{member.mention} has no rank yet. Use **/hire** first.", color=COLORS["yellow"])
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        dept, tier, old_id = current
        ladder = LADDERS[dept]
        if tier >= len(ladder) - 1:
            view = panel(
                "Already at the top",
                f"{member.mention} is at **{RANK_NAMES[old_id]}**, the highest rank I manage. "
                "Promote to Manager manually.",
                color=COLORS["yellow"],
            )
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        await interaction.response.defer()
        new_id = ladder[tier + 1]
        error = await self._apply_roles(member, {new_id, ACCEPTED, DEPT_ROLE[dept]}, {old_id})
        if error:
            await self._report_role_error(interaction, error)
            return

        view = panel(
            "⬆️ Promoted",
            f"{member.mention}: **{RANK_NAMES[old_id]}** → **{RANK_NAMES[new_id]}**.",
            color=COLORS["green"],
            footer=f"By {interaction.user.display_name}",
        )
        await interaction.followup.send(view=view)

    @app_commands.command(name="demote", description="Demote a member one rank down (removes them if at the lowest)")
    @app_commands.describe(member="Who to demote")
    @app_commands.guild_only()
    async def demote(self, interaction: discord.Interaction, member: discord.Member):
        if await self._deny(interaction):
            return

        current = _current_rank(member)
        if current is None:
            view = panel("Not employed", f"{member.mention} has no rank to demote.", color=COLORS["yellow"])
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        dept, tier, old_id = current
        ladder = LADDERS[dept]
        await interaction.response.defer()

        if tier == 0:
            # Lowest rank: remove every shop role.
            held = {r.id for r in member.roles}
            error = await self._apply_roles(member, set(), ALL_MANAGED & held)
            if error:
                await self._report_role_error(interaction, error)
                return
            view = panel(
                "📤 Removed",
                f"{member.mention} was at **{RANK_NAMES[old_id]}** and has been removed from the shop.",
                color=COLORS["red"],
                footer=f"By {interaction.user.display_name}",
            )
            await interaction.followup.send(view=view)
            return

        new_id = ladder[tier - 1]
        error = await self._apply_roles(member, {new_id, ACCEPTED, DEPT_ROLE[dept]}, {old_id})
        if error:
            await self._report_role_error(interaction, error)
            return

        view = panel(
            "⬇️ Demoted",
            f"{member.mention}: **{RANK_NAMES[old_id]}** → **{RANK_NAMES[new_id]}**.",
            color=COLORS["yellow"],
            footer=f"By {interaction.user.display_name}",
        )
        await interaction.followup.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Staff(bot))
