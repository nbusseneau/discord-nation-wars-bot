import json
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import config


logger = logging.getLogger()


NATIONS_FILE = Path("nations.json")
NATIONS: dict[str, str] = json.loads(NATIONS_FILE.read_bytes())
GLOBAL_NATION = "Global"
GLOBAL_NATION_EMOJI = discord.PartialEmoji(name="🌐")
GLOBAL_ROLE_NAME = f"{GLOBAL_NATION_EMOJI} {GLOBAL_NATION}"


class NationCache:
    nation_config: config.NationConfig
    role: discord.Role
    category: discord.CategoryChannel
    emoji: discord.PartialEmoji

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
    def from_config(cls, guild: discord.Guild, config: config.NationConfig) -> None:
        role = guild.get_role(config.role_id)
        category = guild.get_channel(config.category_id)
        emoji = discord.PartialEmoji(name=config.emoji)
        return cls(role, category, emoji)


class GuildCache:
    guild_config: config.GuildConfig
    global_role: discord.Role
    admin_notifications_channel: discord.TextChannel
    welcome_message: discord.Message
    nations: dict[str, NationCache]

    def __init__(
        self,
        guild: discord.Guild,
        config: config.GuildConfig,
        global_role: discord.Role,
        admin_notifications_channel: discord.TextChannel,
        welcome_message: discord.Message,
    ) -> None:
        self.guild_config = config
        self.global_role = global_role
        self.admin_notifications_channel = admin_notifications_channel
        self.welcome_message = welcome_message
        self.nations = {}
        for nation, nation_config in config.nations.items():
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


class CustomBot(commands.Bot):
    cache: dict[discord.Guild, GuildCache]

    def __init__(self, config_filepath: str = "config.json", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.config_file = Path(config_filepath)
        self.bot_config = config.BotConfig.from_json(self.config_file.read_bytes())
        self.cache = {}

    def save_config(self) -> None:
        self.bot_config = config.BotConfig(self.bot_config.token, {})
        for guild, discord_config in self.cache.items():
            self.bot_config.guilds[guild.id] = discord_config.guild_config
        self.config_file.write_text(self.bot_config.to_json(indent=2))

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_ready(self) -> None:
        for guild_id, guild_config in self.bot_config.guilds.items():
            guild = discord.utils.get(self.guilds, id=guild_id)
            admin_notifications_channel = guild.get_channel(
                guild_config.admin_notifications_channel_id
            )
            welcome_channel = guild.get_channel(
                guild_config.welcome_channel_id
            )
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

    async def on_guild_join(self, guild: discord.Guild) -> None:
        global_role = await guild.create_role(
            name=GLOBAL_ROLE_NAME,
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
            name="🚩│choose-country",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(send_messages=True),
            },
        )
        msg = f"""## Hello, I'm the Nation Wars bot! 🤖
- **Join your nation** by typing **`/nation join`**: I will give you **your nation's role** and access to **your nation's channels** 🚀
- Optionally, join the special **{GLOBAL_ROLE_NAME}** nation to get access to **all nations' channels** without grabbing the roles."""  # noqa: E501"
        welcome_message = await welcome_channel.send(msg)
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

    async def try_get_nation(
        self, guild: discord.Guild, nation: str, create_if_not_exists=False
    ) -> NationCache:
        guild_cache = self.cache[guild]

        # special handling for "Global" nation
        if nation == GLOBAL_NATION:
            return NationCache(guild_cache.global_role, None, GLOBAL_NATION_EMOJI)

        try:
            return guild_cache.nations[nation]
        except KeyError:
            if create_if_not_exists:
                return await self._add_nation(guild, nation)
            else:
                return None

    async def _add_nation(self, guild: discord.Guild, nation: str) -> NationCache:
        try:
            emoji = discord.PartialEmoji(name=NATIONS[nation])
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


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = CustomBot(command_prefix="$", intents=intents)
admin_commands_required_permissions = {
    "manage_channels": True,
    "manage_roles": True,
}


@bot.hybrid_group(name="nation")
@commands.guild_only()
async def nation_group(ctx: commands.Context) -> None:
    pass


def to_title(arg: str) -> str:
    return arg.title()


@nation_group.command()
async def join(ctx: commands.Context, nation: to_title) -> None:
    """🎉 Join a nation

    Args:
        nation: 💡 Start typing to filter the list
    """
    await ctx.defer(ephemeral=True)
    nation_cache = await bot.try_get_nation(
        ctx.guild, nation, create_if_not_exists=True
    )

    if nation_cache is None or nation_cache.role in ctx.author.roles:
        await ctx.send(
            f"❌ Invalid value **{nation}** -- please pick a valid value from the list 😤",  # noqa: E501
        )
        return

    await ctx.author.add_roles(nation_cache.role)
    await ctx.send(f"✅ Joined **{nation_cache.role.name}**")


@join.autocomplete("nation")
async def _(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild_cache = bot.cache[interaction.guild]
    choices = [
        app_commands.Choice(name=f"{emoji} {nation}", value=nation)
        for nation, emoji in NATIONS.items()
        if not (
            nation in guild_cache.nations
            and guild_cache.nations[nation].role in interaction.user.roles
        )
    ]
    # special handling for "Global" nation
    if guild_cache.global_role not in interaction.user.roles:
        choices.insert(
            0, app_commands.Choice(name=GLOBAL_ROLE_NAME, value=GLOBAL_NATION)
        )
    choices = [choice for choice in choices if current.lower() in choice.name.lower()]
    return choices[:25]


@nation_group.command()
async def leave(ctx: commands.Context, nation: to_title) -> None:
    """👋 Leave a nation

    Args:
        nation: 💡 Start typing to filter the list
    """
    await ctx.defer(ephemeral=True)
    nation_cache = await bot.try_get_nation(ctx.guild, nation)

    if nation_cache is None or nation_cache.role not in ctx.author.roles:
        await ctx.send(
            f"❌ Invalid value **{nation}** -- please pick a valid value from the list 😤",  # noqa: E501
        )
        return

    await ctx.author.remove_roles(nation_cache.role)
    await ctx.send(f"✅ Removed from **{nation_cache.role.name}**")


@leave.autocomplete("nation")
async def _(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild_cache = bot.cache[interaction.guild]
    choices = [
        app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
        for nation, nation_cache in guild_cache.nations.items()
        if nation_cache.role in interaction.user.roles
    ]
    # special handling for "Global" nation
    if guild_cache.global_role in interaction.user.roles:
        choices.insert(
            0, app_commands.Choice(name=GLOBAL_ROLE_NAME, value=GLOBAL_NATION)
        )
    choices = [choice for choice in choices if current.lower() in choice.name.lower()]
    return choices[:25]


@nation_group.group()
@commands.has_permissions(**admin_commands_required_permissions)
@app_commands.default_permissions(**admin_commands_required_permissions)
async def admin(ctx: commands.Context) -> None:
    pass


@admin.command(name="remove")
async def admin_remove(ctx: commands.Context, nation: to_title) -> None:
    """💀 Remove a nation (admin only)

    Args:
        nation: 💡 Start typing to filter the list
    """
    await ctx.defer(ephemeral=True)
    nation_cache = await bot.try_get_nation(ctx.guild, nation)

    if nation_cache is None or nation == GLOBAL_NATION:
        await ctx.send(f"ℹ️ **{nation}** is not registered -- nothing to do 😴")
        return

    await bot.remove_nation(ctx.guild, nation)
    await ctx.send(f"✅ Removed **{nation_cache.role.name}**")


@admin_remove.autocomplete("nation")
async def _(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild_cache = bot.cache[interaction.guild]
    choices = [
        app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
        for nation, nation_cache in guild_cache.nations.items()
        if current.lower() in nation.lower()
    ]
    return choices[:25]


@admin.command(name="edit-welcome")
async def edit_welcome(
    ctx: commands.Context, line1: str, line2: str, line3: str
) -> None:
    """Edit welcome message (admin only)

    Args:
        line1: First line
        line2: Second line
        line3: Third line
    """
    await ctx.defer(ephemeral=True)
    guild_cache = bot.cache[ctx.guild]
    guild_cache.welcome_message = await guild_cache.welcome_message.edit(
        content=f"{line1}\n{line2}\n{line3}"
    )
    await ctx.send(f"✅ Edited message {guild_cache.welcome_message.jump_url}")


@join.error
@leave.error
@admin_remove.error
@edit_welcome.error
async def nation_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingRole):
        await ctx.send("⛔ Check your privileges!")
    else:
        logger.exception(error)
        await ctx.send("⚠️ Something went wrong -- check the logs... 😖")


if __name__ == "__main__":
    bot.run(token=bot.bot_config.token, log_level=logging.INFO, root_logger=True)
