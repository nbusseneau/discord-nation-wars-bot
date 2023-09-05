import discord
from discord import app_commands
from discord.ext import commands
import json
from pathlib import Path

import config


nations_file = Path('nations.json')
nations: dict[str, str] = json.loads(nations_file.read_bytes())


class NationCache():
    nation_config: config.NationConfig
    role: discord.Role
    category: discord.CategoryChannel
    emoji: discord.PartialEmoji

    def __init__(self, role: discord.Role, category: discord.CategoryChannel, emoji: discord.PartialEmoji) -> None:
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


class GuildCache():
    guild_config: config.GuildConfig
    nation_picker_message: discord.Message
    registered_nations: dict[str, NationCache]

    def __init__(self, guild: discord.Guild, config: config.GuildConfig, nation_picker_message: discord.Message) -> None:
        self.guild_config = config
        self.nation_picker_message = nation_picker_message
        self.registered_nations = {}
        for nation, nation_config in config.registered_nations.items():
            self.registered_nations[nation] = NationCache.from_config(guild, nation_config)

    def add_nation(self, nation: str, role: discord.Role, category: discord.CategoryChannel, emoji: discord.PartialEmoji) -> None:
        self.registered_nations[nation] = NationCache(role, category, emoji)
        self.guild_config.registered_nations[nation] = self.registered_nations[nation].nation_config

    def remove_nation(self, nation: str) -> None:
        del self.registered_nations[nation]
        del self.guild_config.registered_nations[nation]


class CustomBot(commands.Bot):
    guild_cache: dict[discord.Guild, GuildCache]

    def __init__(self, config_filepath: str='config.json', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_file = Path(config_filepath)
        self.bot_config = config.BotConfig.from_json(self.config_file.read_bytes())
        self.guild_cache = {}

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_ready(self) -> None:
        for guild_id, guild_config in self.bot_config.guilds.items():
            guild = discord.utils.get(self.guilds, id=guild_id)
            nation_picker_channel = guild.get_channel(guild_config.nation_picker_channel_id)
            nation_picker_message = await nation_picker_channel.fetch_message(guild_config.nation_picker_message_id)
            self.guild_cache[guild] = GuildCache(guild, guild_config, nation_picker_message)

    async def on_guild_join(self, guild: discord.Guild):
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False),
            guild.me: discord.PermissionOverwrite(send_messages=True),
        }
        nation_picker_channel = await guild.create_text_channel(name="🚩│choose-country", overwrites=overwrites)
        nation_picker_message = await nation_picker_channel.send("Click on a flag to choose your nation! 🚀")
        guild_config = config.GuildConfig(nation_picker_channel.id, nation_picker_message.id, {})
        self.guild_cache[guild] = GuildCache(guild, guild_config, nation_picker_message)
        self.save_config()

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id:
            return

        guild = self.get_guild(payload.guild_id)
        if guild is None or not guild in self.guild_cache:
            return

        if payload.message_id != self.bot_config.guilds[guild.id].nation_picker_message_id:
            return

        role = next((nation.role for nation in self.guild_cache[guild].registered_nations.values() if payload.emoji == nation.emoji), None)
        if role is None:
            return

        try:
            await payload.member.add_roles(role)
        except discord.HTTPException:
            pass

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id:
            return

        guild = self.get_guild(payload.guild_id)
        if guild is None or not guild in self.guild_cache:
            return

        if payload.message_id != self.bot_config.guilds[guild.id].nation_picker_message_id:
            return

        role = next((nation.role for nation in self.guild_cache[guild].registered_nations.values() if payload.emoji == nation.emoji), None)
        if role is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            return

        try:
            await member.remove_roles(role)
        except discord.HTTPException:
            pass

    def save_config(self) -> None:
        self.bot_config = config.BotConfig(self.bot_config.token, {})
        for guild, discord_config in self.guild_cache.items():
            self.bot_config.guilds[guild.id] = discord_config.guild_config
        self.config_file.write_text(self.bot_config.to_json(indent=2))


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = CustomBot(command_prefix='$', intents=intents)

@bot.hybrid_group()
@commands.guild_only()
@commands.has_permissions(manage_channels=True, manage_roles=True, manage_messages=True)
@app_commands.default_permissions(manage_channels=True, manage_roles=True, manage_messages=True)
async def nation(ctx):
    pass


def to_title(arg: str):
    return arg.title()


@nation.command()
async def add(ctx: commands.Context, nation: to_title):
    if not nation in nations:
        await ctx.send(f"❌ invalid nation '{nation}' -- pick a valid nation from the list")
        return
    
    emoji = discord.PartialEmoji(name=nations[nation])
    role = await ctx.guild.create_role(name=nation, hoist=True, mentionable=True)

    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        ctx.guild.me: discord.PermissionOverwrite(view_channel=True),
        role: discord.PermissionOverwrite(view_channel=True)
    }
    category = await ctx.guild.create_category(name=nation, overwrites=overwrites)
    await ctx.guild.create_text_channel(name=nation, category=category)
    await ctx.guild.create_voice_channel(name="players", category=category)
    await ctx.guild.create_voice_channel(name="spectators", category=category)

    nation_picker_message = bot.guild_cache[ctx.guild].nation_picker_message
    reaction = discord.utils.get(nation_picker_message.reactions, emoji=emoji)
    if reaction:
        async for user in reaction.users():
            await user.add_roles(role)
    await nation_picker_message.add_reaction(emoji)

    bot.guild_cache[ctx.guild].add_nation(nation, role, category, emoji)
    bot.save_config()
    await ctx.send(f"✅ added nation: {nation} {emoji}")


@add.autocomplete('nation')
async def add_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name=f"{nation} {emoji}", value=nation) for nation, emoji in nations.items() if current.lower() in nation.lower() and not nation in bot.guild_cache[interaction.guild].registered_nations]
    return choices[:25]


@nation.command()
async def remove(ctx: commands.Context, nation: to_title):
    if not nation in bot.guild_cache[ctx.guild].registered_nations:
        await ctx.send(f"ℹ️ nation '{nation}' was not registered -- nothing to do!")
        return
    
    discord_registered_nation = bot.guild_cache[ctx.guild].registered_nations[nation]
    await discord_registered_nation.role.delete()

    category = discord.utils.get(ctx.guild.categories, name=nation)
    if category:
        for channel in category.channels:
            await channel.delete()
        await category.delete()

    emoji = discord_registered_nation.emoji
    try:
        await bot.guild_cache[ctx.guild].nation_picker_message.clear_reaction(emoji)
    except discord.NotFound:
        pass

    bot.guild_cache[ctx.guild].remove_nation(nation)
    bot.save_config()
    await ctx.send(f"✅ removed nation: {nation} {emoji}")


@remove.autocomplete('nation')
async def remove_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=f"{nation} {discord_registered_nation.emoji}", value=nation) for nation, discord_registered_nation in bot.guild_cache[interaction.guild].registered_nations.items()]


@add.error
@remove.error
async def nation_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("⛔ Check your privileges!")
    else:
        raise error


if __name__ == "__main__":
    bot.run(bot.bot_config.token)