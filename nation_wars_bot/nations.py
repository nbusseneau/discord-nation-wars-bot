import json
from pathlib import Path

import discord


NATIONS_FILE = Path("nations.json")
NATIONS: dict[str, str] = json.loads(NATIONS_FILE.read_bytes())
GLOBAL_NATION = "Global"
GLOBAL_NATION_EMOJI = discord.PartialEmoji(name="🌐")
GLOBAL_ROLE_NAME = f"{GLOBAL_NATION_EMOJI} {GLOBAL_NATION}"
