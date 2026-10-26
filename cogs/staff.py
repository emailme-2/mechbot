"""Mech-shop staff management: /hire, /promote, /demote.

Only members holding an authorized role can run these. Each department is a rank
ladder the bot manages; the Manager roles above them are assigned manually and
left alone. A member can be in both departments at once. Hiring/promoting keeps
the shared Accepted role and the department role in sync. The bot needs Manage
Roles, with its own role above every role listed here.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLORS, panel

# Roles allowed to run these commands (a member needs to hold one of them).
ALLOWED_ROLES = {1317971108829597746, 1275730902105849949}

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
DEPT_LABEL = {"mechanic": "🔧 Mechanic", "sales": "🚗 Sales"}

ACCEPTED = 1412165063527366687                              # shared by both departments
DEPT_ROLE = {"mechanic": 1298451074423853117, "sales": 1298450888846999583}  # [Mechanic], Dealer

ALL_RANKS = set(MECH_LADDER) | set(SALES_LADDER)
ALL_MANAGED = ALL_RANKS | {ACCEPTED} | set(DEPT_ROLE.values())

MECH_CHOICES = [app_commands.Choice(name=RANK_NAMES[r], value=str(r)) for r in MECH_LADDER]
SALES_CHOICES = [app_commands.Choice(name=RANK_NAMES[r], value=str(r)) for r in SALES_LADDER]
DEPT_CHOICES = [app_commands.Choice(name=DEPT_LABEL[d].split()[-1], value=d) for d in LADDERS]


def _depts_held(member: discord.Member) -> set[str]:
    ids = {r.id for r in member.roles}
    return {dept for dept, ladder in LADDERS.items() if ids & set(ladder)}


def _rank_in(member: discord.Member, dept: str):
    """The member's (tier, role_id) in a department, or None if they have no rank there."""
    ids = {r.id for r in member.roles}
    for tier, rid in enumerate(LADDERS[dept]):
        if rid in ids:
            return tier, rid
    return None


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        member_roles = {r.id for r in getattr(interaction.user, "roles", [])}
        if member_roles & ALLOWED_ROLES:
            return False
        view = panel("⛔ Not allowed", "You can't use this command.", color=COLORS["red"])
        await interaction.response.send_message(view=view, ephemeral=True)
        return True

    async def _note(self, interaction: discord.Interaction, title: str, body: str, color=None) -> None:
        view = panel(title, body, color=color or COLORS["yellow"])
        await interaction.response.send_message(view=view, ephemeral=True)

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

    def _resolve_dept(self, member: discord.Member, choice):
        """Pick the department to act on: ('ok', dept) or ('none'|'both'|'missing', dept?)."""
        held = _depts_held(member)
        if choice is not None:
            dept = choice.value
            return ("ok", dept) if dept in held else ("missing", dept)
        if not held:
            return ("none", None)
        if len(held) == 1:
            return ("ok", next(iter(held)))
        return ("both", None)

    @app_commands.command(name="hire", description="Hire a member for mechanic, sales, or both")
    @app_commands.describe(member="Who to hire", mechanic="Mechanic rank (optional)", sales="Sales rank (optional)")
    @app_commands.choices(mechanic=MECH_CHOICES, sales=SALES_CHOICES)
    @app_commands.guild_only()
    async def hire(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        mechanic: app_commands.Choice[str] | None = None,
        sales: app_commands.Choice[str] | None = None,
    ):
        if await self._deny(interaction):
            return
        if mechanic is None and sales is None:
            await self._note(interaction, "Pick a rank", "Choose a mechanic rank, a sales rank, or both.")
            return

        add_ids: set[int] = set()
        remove_ids: set[int] = set()
        chosen: list[str] = []

        for choice, dept, ladder in ((mechanic, "mechanic", MECH_LADDER), (sales, "sales", SALES_LADDER)):
            if choice is None:
                continue  # additive: leave the other department untouched
            rid = int(choice.value)
            add_ids |= {rid, ACCEPTED, DEPT_ROLE[dept]}
            remove_ids |= {r for r in ladder if r != rid}  # drop any other rank in this department
            chosen.append(f"{DEPT_LABEL[dept].split()[0]} {RANK_NAMES[rid]}")

        held = {r.id for r in member.roles}
        await interaction.response.defer()
        error = await self._apply_roles(member, add_ids - held, (remove_ids - add_ids) & held)
        if error:
            await self._report_role_error(interaction, error)
            return

        view = panel(
            "✅ Hired",
            f"{member.mention} is now: {', '.join(chosen)}.",
            color=COLORS["green"],
            footer=f"By {interaction.user.display_name}",
        )
        await interaction.followup.send(view=view)

    @app_commands.command(name="promote", description="Promote a member one rank up in a department")
    @app_commands.describe(member="Who to promote", department="Which department (needed only if they're in both)")
    @app_commands.choices(department=DEPT_CHOICES)
    @app_commands.guild_only()
    async def promote(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        department: app_commands.Choice[str] | None = None,
    ):
        if await self._deny(interaction):
            return

        status, dept = self._resolve_dept(member, department)
        if status == "none":
            await self._note(interaction, "Not employed", f"{member.mention} has no rank yet. Use **/hire** first.")
            return
        if status == "both":
            await self._note(interaction, "Pick a department", f"{member.mention} is in both. Add the **department** option.")
            return
        if status == "missing":
            await self._note(interaction, "Not in that department", f"{member.mention} has no {DEPT_LABEL[dept]} rank.")
            return

        tier, old_id = _rank_in(member, dept)
        ladder = LADDERS[dept]
        if tier >= len(ladder) - 1:
            await self._note(
                interaction, "Already at the top",
                f"{member.mention} is at **{RANK_NAMES[old_id]}**, the highest {DEPT_LABEL[dept]} rank I manage. "
                "Promote to Manager manually.",
            )
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

    @app_commands.command(name="demote", description="Demote a member one rank (removes the department if at the lowest)")
    @app_commands.describe(member="Who to demote", department="Which department (needed only if they're in both)")
    @app_commands.choices(department=DEPT_CHOICES)
    @app_commands.guild_only()
    async def demote(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        department: app_commands.Choice[str] | None = None,
    ):
        if await self._deny(interaction):
            return

        status, dept = self._resolve_dept(member, department)
        if status == "none":
            await self._note(interaction, "Not employed", f"{member.mention} has no rank to demote.")
            return
        if status == "both":
            await self._note(interaction, "Pick a department", f"{member.mention} is in both. Add the **department** option.")
            return
        if status == "missing":
            await self._note(interaction, "Not in that department", f"{member.mention} has no {DEPT_LABEL[dept]} rank.")
            return

        tier, old_id = _rank_in(member, dept)
        ladder = LADDERS[dept]
        await interaction.response.defer()

        if tier == 0:
            # Lowest rank: remove this department. Drop Accepted only if they have no other department.
            remove = {old_id, DEPT_ROLE[dept]}
            if not (_depts_held(member) - {dept}):
                remove.add(ACCEPTED)
            held = {r.id for r in member.roles}
            error = await self._apply_roles(member, set(), remove & held)
            if error:
                await self._report_role_error(interaction, error)
                return
            view = panel(
                "📤 Removed",
                f"{member.mention} was at **{RANK_NAMES[old_id]}** and has been removed from {DEPT_LABEL[dept]}.",
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
