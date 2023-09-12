import logging

import discord
from discord import app_commands
from discord.ext import tasks

from nation_wars_bot import config, commands, nations


DEFAULT_WELCOME_MESSAGE = f"""# Hello, I'm the Nation Wars bot! 🤖

## Slash Commands

- Use **`/join`** to **join your nation**: I will give you **your nation's role** and access to **your nation's channels** 🚀
  - ℹ️ You can join only **one** nation at once, use **`/leave`** first to switch!
- Use **`/global`** to enable the **{nations.GLOBAL_ROLE_NAME}** role and get access to **all nations' channels**, no matter which nation you joined.
  - 💡 Use  **`/global`** again to disable or re-enable the role at any time!

## Step-by-step join instructions

- Type **`/join`** and then **Space**.
- Start typing your nation's name in English: **3 characters** should be enough to filter the list.
- Select your nation from the list, and then **Enter**.
"""  # noqa: E501"


class NationCache:
    def __init__(
        self,
        role: discord.Role,
        category: discord.CategoryChannel,
        emoji: discord.PartialEmoji,
    ) -> None:
        if category is not None:
            self.nation_config = config.NationConfig(role.id, category.id, str(emoji))
        self.role = role
        self.category = category
        self.emoji = emoji

    @classmethod
    def from_config(
        cls, guild: discord.Guild, nation_config: config.NationConfig
    ) -> "NationCache":
        role = guild.get_role(nation_config.role_id)
        category = guild.get_channel(nation_config.category_id)
        emoji = discord.PartialEmoji(name=nation_config.emoji)
        return cls(role, category, emoji)

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, NationCache):
            return self.role == __value.role


class GuildCache:
    def __init__(
        self,
        guild: discord.Guild,
        guild_config: config.GuildConfig,
        global_role: discord.Role,
        admin_notifications_channel: discord.TextChannel,
        welcome_message: discord.Message,
    ) -> None:
        self.guild_config = guild_config
        self.global_role = global_role
        self.admin_notifications_channel = admin_notifications_channel
        self.welcome_message = welcome_message
        self.nations: dict[str, NationCache] = {}
        for nation, nation_config in guild_config.nations.items():
            self.nations[nation] = NationCache.from_config(guild, nation_config)

    def add_nation(
        self,
        nation: str,
        role: discord.Role,
        category: discord.CategoryChannel,
        emoji: discord.PartialEmoji,
    ) -> None:
        self.nations[nation] = NationCache(role, category, emoji)
        self.guild_config.nations[nation] = self.nations[nation].nation_config

    def remove_nation(self, nation: str) -> None:
        del self.nations[nation]
        del self.guild_config.nations[nation]


class NationWarsBot(discord.Client):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cache: dict[discord.Guild, GuildCache] = {}
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(commands.join)
        self.tree.add_command(commands.leave)
        self.tree.add_command(commands.global_command)
        self.tree.add_command(commands.admin)
        self.tree.on_error = self._tree_error_handler

    async def _tree_error_handler(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        logging.exception(error)
        await interaction.followup.send(
            "⚠️ Something went wrong -- check the logs... 😖"
        )

    async def setup_hook(self) -> None:
        await self.tree.sync()
        self.sync_flags.start()

    async def load_config(self) -> None:
        self.cache = {}
        for guild_id, guild_config in config.BOT_CONFIG.guilds.items():
            guild = discord.utils.get(self.guilds, id=guild_id)
            admin_notifications_channel = guild.get_channel(
                guild_config.admin_notifications_channel_id
            )
            welcome_channel = guild.get_channel(guild_config.welcome_channel_id)
            welcome_message = await welcome_channel.fetch_message(
                guild_config.welcome_message_id
            )
            global_role = guild.get_role(guild_config.global_role_id)
            self.cache[guild] = GuildCache(
                guild,
                guild_config,
                global_role,
                admin_notifications_channel,
                welcome_message,
            )

    def save_config(self) -> None:
        config.BOT_CONFIG = config.BotConfig(config.BOT_CONFIG.token, {})
        for guild, discord_config in self.cache.items():
            config.BOT_CONFIG.guilds[guild.id] = discord_config.guild_config
        config.CONFIG_FILE.write_text(config.BOT_CONFIG.to_json(indent=2))

    async def on_ready(self) -> None:
        await self.load_config()
        await self.tree.sync()
        await self.sync_flags()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        global_role = await guild.create_role(
            name=nations.GLOBAL_ROLE_NAME,
            hoist=False,
            mentionable=False,
        )
        admin_notifications_channel = await guild.create_text_channel(
            name="🤖│nation-wars-bot",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True),
            },
        )
        welcome_channel = await guild.create_text_channel(
            name="🚩│join-nation",
            overwrites={
                guild.me: discord.PermissionOverwrite(send_messages=True),
            },
            slowmode_delay=60,
        )
        welcome_message = await welcome_channel.send(DEFAULT_WELCOME_MESSAGE)
        guild_config = config.GuildConfig(
            global_role.id,
            admin_notifications_channel.id,
            welcome_channel.id,
            welcome_message.id,
            {},
        )
        self.cache[guild] = GuildCache(
            guild,
            guild_config,
            global_role,
            admin_notifications_channel,
            welcome_message,
        )
        self.save_config()

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        before_nation_cache = self.try_get_user_nation(before)
        after_nation_cache = self.try_get_user_nation(after)

        user_left_nation = (
            before_nation_cache is not None and after_nation_cache is None
        )
        user_joined_nation = (
            before_nation_cache is None and after_nation_cache is not None
        )
        user_switched_nation = before_nation_cache != after_nation_cache

        user_changed_name = before.display_name != after.display_name
        before_nation_in_username = (
            before_nation_cache is not None
            and str(before_nation_cache.emoji) in after.display_name
        )
        after_nation_not_in_username = (
            after_nation_cache is not None
            and str(after_nation_cache.emoji) not in after.display_name
        )

        new_name = after.display_name
        if (user_left_nation or user_switched_nation) and before_nation_in_username:
            new_name = new_name.strip(str(before_nation_cache.emoji))
        if (
            user_joined_nation or user_changed_name or user_switched_nation
        ) and after_nation_not_in_username:
            new_name = f"{after_nation_cache.emoji} {new_name}"
        if new_name != after.display_name:
            try:
                await after.edit(nick=new_name)
            except discord.errors.Forbidden as e:
                logging.warning(f"`{e}` while trying to edit `{after}`'s name")
                logging.warning(
                    "note that the bot can never edit the owner's name, even with full permissions"  # noqa: E501
                )

    @tasks.loop(hours=1)
    async def sync_flags(self):
        for guild in self.guilds:
            for member in guild.members:
                nation_cache = self.try_get_user_nation(member)
                if (
                    nation_cache is not None
                    and str(nation_cache.emoji) not in member.display_name
                ):
                    try:
                        await member.edit(
                            nick=f"{nation_cache.emoji} {member.display_name}"
                        )
                    except discord.errors.Forbidden as e:
                        # bot can never edit owner's name, even with full permissions
                        if member is not guild.owner:
                            logging.warning(
                                f"`{e}` while trying to edit `{member}`'s name"
                            )
                    except Exception as e:  # noqa: E722
                        logging.exception(e)

    async def try_get_nation(
        self, guild: discord.Guild, nation: str, create_if_not_exists=False
    ) -> NationCache | None:
        guild_cache = self.cache[guild]

        try:
            return guild_cache.nations[nation]
        except KeyError:
            if create_if_not_exists:
                return await self._add_nation(guild, nation)
            else:
                return None

    async def _add_nation(
        self, guild: discord.Guild, nation: str
    ) -> NationCache | None:
        try:
            emoji = discord.PartialEmoji(name=nations.NATIONS[nation])
        except KeyError:
            return None

        guild_cache = self.cache[guild]
        name = f"{emoji} {nation}"

        role = await guild.create_role(name=name, hoist=True, mentionable=True)
        category = await guild.create_category(
            name=name,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True),
                role: discord.PermissionOverwrite(view_channel=True),
                guild_cache.global_role: discord.PermissionOverwrite(view_channel=True),
            },
        )
        await guild.create_text_channel(name=f"{emoji}│{nation}", category=category)
        await guild.create_voice_channel(name="players", category=category)
        await guild.create_voice_channel(name="spectators", category=category)

        guild_cache.add_nation(nation, role, category, emoji)
        self.save_config()
        await guild_cache.admin_notifications_channel.send(f"ℹ️ Added **{name}**")
        return guild_cache.nations[nation]

    async def remove_nation(self, guild: discord.Guild, nation: str) -> None:
        guild_cache = self.cache[guild]
        nation_cache = guild_cache.nations[nation]

        await nation_cache.role.delete()
        for channel in nation_cache.category.channels:
            await channel.delete()
        await nation_cache.category.delete()

        guild_cache.remove_nation(nation)
        self.save_config()
        await guild_cache.admin_notifications_channel.send(
            f"ℹ️ Removed **{nation_cache.role.name}**"
        )

    def try_get_user_nation(self, user: discord.Member) -> NationCache | None:
        guild_cache = self.cache[user.guild]
        return next(
            (
                nation_cache
                for nation_cache in guild_cache.nations.values()
                if nation_cache.role in user.roles
            ),
            None,
        )

    def get_global_role(self, guild: discord.Guild) -> discord.Role:
        return self.cache[guild].global_role


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
BOT = NationWarsBot(intents=intents)
