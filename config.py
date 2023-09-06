import dataclasses
import dataclasses_json


@dataclasses.dataclass
class NationConfig(dataclasses_json.DataClassJsonMixin):
    role_id: int
    category_id: int
    emoji: str


@dataclasses.dataclass
class GuildConfig(dataclasses_json.DataClassJsonMixin):
    global_role_id: int
    bot_admin_notifications_channel_id: int
    nation_picker_channel_id: int
    nation_picker_message_id: int
    nations: dict[str, NationConfig]


@dataclasses.dataclass
class BotConfig(dataclasses_json.DataClassJsonMixin):
    token: str
    guilds: dict[int, GuildConfig]
