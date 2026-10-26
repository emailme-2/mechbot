# MechBot

A small Discord bot built with [discord.py](https://discordpy.readthedocs.io/) using slash commands and embeds.

## Commands

| Command | Description |
| --- | --- |
| `/ping` | Gateway latency, color-coded embed |
| `/hello [member]` | Welcome embed greeting you or another member |
| `/info` | Bot uptime, server count, latency, versions |
| `/server` | Server stats: members, owner, boosts, channels, roles |
| `/embed <title> <description> [color]` | Build a custom embed with a chosen accent color |
| `/help` | List every command |

The bot comes online with an "online" presence and a listening activity.

## Project structure

```
main.py            Entry point: loads the token and runs the bot
bot.py             The MechBot client: auto-loads cogs and syncs slash commands
core.py            Shared helpers (colors, timestamps, base_embed)
cogs/
  general.py       /ping, /hello, /info, /help
  serverinfo.py    /server
  embeds.py        /embed
  _template.py     Copy this to start a new cog
```

Every `.py` file in `cogs/` is loaded automatically on startup. Files whose name
starts with `_` are skipped, so `_template.py` stays dormant until you copy it.

## Add a command

1. Copy `cogs/_template.py` to `cogs/<yourname>.py` (without the leading underscore).
2. Rename the class and set your own command name and description.
3. Restart the bot. The new command is picked up and synced automatically.

Use the helpers in `core.py` (`base_embed`, `COLORS`, `now`, `format_duration`) so new
commands match the look of the existing ones.

## Setup

1. Create an application at <https://discord.com/developers/applications>.
2. Open the **Bot** tab, click **Reset Token**, and copy the token.
3. Paste it into `.env`:

   ```
   DISCORD_TOKEN=your-token-here
   ```

   Optionally set `GUILD_ID` to a server ID so commands sync instantly while developing
   (global commands can take up to an hour to appear).

4. Invite the bot: **OAuth2 -> URL Generator**, select the `bot` and `applications.commands`
   scopes, then use the generated URL.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

`main.py` is the bot's entry point. You should see `Logged in as ... - bot is ONLINE` and the command list in Discord.
