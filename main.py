"""MechBot entry point: load the token from the environment and run the bot."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # hosting panels often inject env vars directly
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).with_name(".env"))

from bot import MechBot


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and paste your bot token."
        )
    MechBot().run(token)


if __name__ == "__main__":
    main()
