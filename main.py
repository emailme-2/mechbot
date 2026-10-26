"""MechBot entry point: load the token from the environment (or a local .env) and run the bot."""

import os
from pathlib import Path

ENV_PATH = Path(__file__).with_name(".env")


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into the environment.

    Uses python-dotenv when it's installed; otherwise parses the file directly,
    so the token still loads on hosts that don't have that package.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    # override=True: this bot's own .env wins over anything already in the
    # container's shared environment (each bot folder has its own token).
    if load_dotenv is not None:
        load_dotenv(path, override=True)
        return

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")  # tolerate stray quotes
        os.environ[key.strip()] = value


load_env_file(ENV_PATH)

from bot import MechBot


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        where = "found" if ENV_PATH.exists() else "not found"
        raise SystemExit(
            f"DISCORD_TOKEN is not set (.env {where} at {ENV_PATH}). "
            "Add a line: DISCORD_TOKEN=your-token-here"
        )
    MechBot().run(token)


if __name__ == "__main__":
    main()
