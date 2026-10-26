"""Helpers shared across every cog: the color set, UTC time, and embed scaffolding."""

from datetime import datetime, timedelta, timezone

import discord

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
    """Render a timedelta as '2d 3h 4m 5s', dropping leading units that are zero."""
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


def panel(title: str, *blocks: str, color: int = BRAND_COLOR, thumbnail: str | None = None,
          footer: str | None = None) -> discord.ui.LayoutView:
    """Build a Components V2 container (the new 'embed' style the whole bot uses).

    `blocks` are markdown sections stacked under the title with a divider between
    each; `thumbnail` puts an image beside the title; `footer` is small grey text.
    """
    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_colour=color)

    heading = discord.ui.TextDisplay(f"## {title}")
    if thumbnail:
        container.add_item(discord.ui.Section(heading, accessory=discord.ui.Thumbnail(media=thumbnail)))
    else:
        container.add_item(heading)

    for block in blocks:
        if block:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(block))

    if footer:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {footer}"))

    view.add_item(container)
    return view
