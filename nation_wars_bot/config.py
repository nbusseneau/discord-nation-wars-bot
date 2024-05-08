import dataclasses
from pathlib import Path

import dataclasses_json


@dataclasses.dataclass
class NationConfig(dataclasses_json.DataClassJsonMixin):
    role_id: int
    channel_id: int
    emoji: str


@dataclasses.dataclass
class GuildConfig(dataclasses_json.DataClassJsonMixin):
    global_role_id: int
    admin_notifications_channel_id: int
    welcome_channel_id: int
    welcome_message_id: int
    nations_category_id: int
    nations: dict[str, NationConfig]


@dataclasses.dataclass
class BotConfig(dataclasses_json.DataClassJsonMixin):
    token: str
    guilds: dict[int, GuildConfig]


CONFIG_FILE = Path("config.json")
BOT_CONFIG = BotConfig.from_json(CONFIG_FILE.read_bytes())
