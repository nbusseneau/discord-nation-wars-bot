import json
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import config


logger = logging.getLogger()


nations_file = Path("nations.json")
nations: dict[str, str] = json.loads(nations_file.read_bytes())


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
    bot_admin_notifications_channel: discord.TextChannel
    nation_picker_message: discord.Message
    nations: dict[str, NationCache]

    def __init__(
        self,
        guild: discord.Guild,
        config: config.GuildConfig,
        bot_admin_notifications_channel: discord.TextChannel,
        nation_picker_message: discord.Message,
    ) -> None:
        self.guild_config = config
        self.bot_admin_notifications_channel = bot_admin_notifications_channel
        self.nation_picker_message = nation_picker_message
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
            bot_admin_notifications_channel = guild.get_channel(
                guild_config.bot_admin_notifications_channel_id
            )
            nation_picker_channel = guild.get_channel(
                guild_config.nation_picker_channel_id
            )
            nation_picker_message = await nation_picker_channel.fetch_message(
                guild_config.nation_picker_message_id
            )
            self.cache[guild] = GuildCache(
                guild,
                guild_config,
                bot_admin_notifications_channel,
                nation_picker_message,
            )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        bot_admin_notifications_channel = await guild.create_text_channel(
            name="🤖│nation-wars-bot",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True),
            },
        )
        nation_picker_channel = await guild.create_text_channel(
            name="🚩│choose-country",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(send_messages=True),
            },
        )
        msg = """Set your nation by **clicking on an existing flag** or **adding a new one**! 🚀
Any nation with **at least 4 members** will automatically get a **nation role** and **nation channels**! 😉"""  # noqa: E501"
        nation_picker_message = await nation_picker_channel.send(msg)
        guild_config = config.GuildConfig(
            bot_admin_notifications_channel.id,
            nation_picker_channel.id,
            nation_picker_message.id,
            {},
        )
        self.cache[guild] = GuildCache(
            guild, guild_config, bot_admin_notifications_channel, nation_picker_message
        )
        self.save_config()

    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.user_id == self.user.id:
            return

        guild = discord.utils.get(self.guilds, id=payload.guild_id)
        if guild is None or guild not in self.cache:
            return

        nation_picker_message = self.cache[guild].nation_picker_message
        if payload.message_id != nation_picker_message.id:
            return

        role = next(
            (
                nation.role
                for nation in self.cache[guild].nations.values()
                if payload.emoji == nation.emoji
            ),
            None,
        )
        # when nation is already registered
        if role is not None:
            try:
                await payload.member.add_roles(role)
            except discord.HTTPException:
                pass
            return

        # when nation is not registered
        nation = next(
            (
                nation
                for nation, emoji in nations.items()
                if payload.emoji == discord.PartialEmoji(name=emoji)
            ),
            None,
        )
        if nation is not None:
            emoji = discord.PartialEmoji(name=nations[nation])
            nation_picker_message = await nation_picker_message.channel.fetch_message(
                nation_picker_message.id
            )
            self.cache[guild].nation_picker_message = nation_picker_message
            reaction = discord.utils.get(
                nation_picker_message.reactions, emoji=str(emoji)
            )
            # as soon as 4 members have reacted
            if reaction and reaction.count >= 4:
                name = await self.add_nation(guild, nation)
                await self.cache[guild].bot_admin_notifications_channel.send(
                    f"ℹ️ Automatically added (4+ reactions): **{name}**"
                )

    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.user_id == self.user.id:
            return

        guild = discord.utils.get(self.guilds, id=payload.guild_id)
        if guild is None or guild not in self.cache:
            return

        if payload.message_id != self.cache[guild].nation_picker_message.id:
            return

        role = next(
            (
                nation.role
                for nation in self.cache[guild].nations.values()
                if payload.emoji == nation.emoji
            ),
            None,
        )
        if role is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            return

        try:
            await member.remove_roles(role)
        except discord.HTTPException:
            pass

    async def add_nation(self, guild: discord.Guild, nation: str):
        emoji = discord.PartialEmoji(name=nations[nation])
        name = f"{emoji} {nation}"

        role = await guild.create_role(name=name, hoist=True, mentionable=True)
        category = await guild.create_category(
            name=name,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True),
                role: discord.PermissionOverwrite(view_channel=True),
            },
        )
        await guild.create_text_channel(name=f"{emoji}│{nation}", category=category)
        await guild.create_voice_channel(name="players", category=category)
        await guild.create_voice_channel(name="spectators", category=category)

        cache = bot.cache[guild]
        nation_picker_message = await cache.nation_picker_message.channel.fetch_message(
            cache.nation_picker_message.id
        )
        reaction = discord.utils.get(nation_picker_message.reactions, emoji=str(emoji))
        if reaction:
            async for user in reaction.users():
                await user.add_roles(role)
        await nation_picker_message.add_reaction(emoji)
        cache.nation_picker_message = nation_picker_message

        cache.add_nation(nation, role, category, emoji)
        self.save_config()
        return name


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
@commands.has_permissions(**admin_commands_required_permissions)
@app_commands.default_permissions(**admin_commands_required_permissions)
async def nation_group(ctx: commands.Context) -> None:
    pass


def to_title(arg: str) -> str:
    return arg.title()


@nation_group.command()
async def add(ctx: commands.Context, nation: to_title) -> None:
    if nation not in nations:
        await ctx.send(
            f"❌ Invalid nation **{nation}** -- please pick a valid nation from the list 😤"  # noqa: E501
        )
        return

    await ctx.defer()
    name = await bot.add_nation(ctx.guild, nation)
    await ctx.send(f"✅ Added: **{name}**")


@add.autocomplete("nation")
async def add_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = [
        app_commands.Choice(name=f"{emoji} {nation}", value=nation)
        for nation, emoji in nations.items()
        if current.lower() in nation.lower()
        and nation not in bot.cache[interaction.guild].nations
    ]
    return choices[:25]


@nation_group.command()
async def remove(ctx: commands.Context, nation: to_title) -> None:
    cache = bot.cache[ctx.guild]
    if nation not in cache.nations:
        await ctx.send(f"ℹ️ **{nation}** is not registered -- nothing to do 😴")
        return

    await ctx.defer()

    nation_cache = cache.nations[nation]
    await nation_cache.role.delete()

    category = nation_cache.category
    for channel in category.channels:
        await channel.delete()
    await category.delete()

    emoji = nation_cache.emoji
    await cache.nation_picker_message.remove_reaction(emoji, bot.user)

    cache.remove_nation(nation)
    bot.save_config()
    await ctx.send(f"✅ Removed: **{emoji} {nation}**")


@remove.autocomplete("nation")
async def remove_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
        for nation, nation_cache in bot.cache[interaction.guild].nations.items()
        if current.lower() in nation.lower()
    ]


@nation_group.command(name="edit-picker-message")
async def edit_picker_message(ctx: commands.Context, message: str) -> None:
    cache = bot.cache[ctx.guild]
    cache.nation_picker_message = await cache.nation_picker_message.edit(
        content=message
    )
    await ctx.send(f"✅ Edited picker message: {cache.nation_picker_message.jump_url}")


@add.error
@remove.error
@edit_picker_message.error
async def nation_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingRole):
        await ctx.send("⛔ Check your privileges!")
    else:
        logger.exception(error)
        await ctx.send("⚠️ Something went wrong -- check the logs... 😖")


if __name__ == "__main__":
    bot.run(token=bot.bot_config.token, log_level=logging.INFO, root_logger=True)
