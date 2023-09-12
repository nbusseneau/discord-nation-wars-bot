import discord
from discord import app_commands

from nation_wars_bot import bot
from nation_wars_bot.nations import NATIONS, GLOBAL_ROLE_NAME


@app_commands.command()
@app_commands.guild_only()
async def join(interaction: discord.Interaction, nation: str) -> None:
    """🎉 Join your nation

    Args:
        nation: 💡 Find your nation by typing its name (in English, sorry!)
    """
    await interaction.response.defer(ephemeral=True)

    existing_nation = bot.BOT.try_get_user_nation(interaction.user)
    if existing_nation is not None:
        await interaction.followup.send(
            f"⛔ Already joined **{existing_nation.role.name}** -- you can join only **one** nation at once, use **`/leave`** first to switch!"  # noqa: E501"
        )
        return

    nation = nation.title()
    nation_cache = await bot.BOT.try_get_nation(
        interaction.guild, nation, create_if_not_exists=True
    )
    if nation_cache is None:
        await interaction.followup.send(
            f"❌ Invalid value **{nation}** -- please pick a valid value from the list 😤"  # noqa: E501
        )
        return

    await interaction.user.add_roles(nation_cache.role)
    await interaction.followup.send(
        content=f"✅ Joined **{nation_cache.role.name}**", ephemeral=True
    )


@join.autocomplete("nation")
async def _(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = [
        app_commands.Choice(name=f"{emoji} {nation}", value=nation)
        for nation, emoji in NATIONS.items()
        if current.lower() in nation.lower()
    ]
    return choices[:25]


@app_commands.command()
@app_commands.guild_only()
async def leave(interaction: discord.Interaction) -> None:
    """👋 Leave current nation"""
    await interaction.response.defer(ephemeral=True)

    existing_nation = bot.BOT.try_get_user_nation(interaction.user)
    if existing_nation is None:
        await interaction.followup.send(
            "ℹ️ You haven't joined any nation -- nothing to do 😴"
        )
        return

    await interaction.user.remove_roles(existing_nation.role)
    await interaction.followup.send(f"✅ Left **{existing_nation.role.name}**")


@app_commands.command(
    name="global", description=f"Enable / disable the {GLOBAL_ROLE_NAME} role"
)
@app_commands.guild_only()
async def global_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)

    global_role = bot.BOT.get_global_role(interaction.guild)
    if global_role not in interaction.user.roles:
        await interaction.user.add_roles(global_role)
        await interaction.followup.send(
            content=f"✅ Enabled **{global_role.name}**", ephemeral=True
        )
    else:
        await interaction.user.remove_roles(global_role)
        await interaction.followup.send(
            content=f"✅ Disabled **{global_role.name}**", ephemeral=True
        )


@app_commands.guild_only()
@app_commands.default_permissions(manage_channels=True, manage_roles=True)
class Admin(app_commands.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(
            name="admin", description="admin-only command group", *args, **kwargs
        )

    @app_commands.command()
    async def remove(self, interaction: discord.Interaction, nation: str) -> None:
        """💀 Remove a nation

        Args:
            nation: 💡 Find the nation by typing its name (in English)
        """
        await interaction.response.defer(ephemeral=True)

        nation = nation.title()
        nation_cache = await bot.BOT.try_get_nation(interaction.guild, nation)
        if nation_cache is None:
            await interaction.followup.send(
                f"ℹ️ **{nation}** is not registered -- nothing to do 😴"
            )
            return

        await bot.BOT.remove_nation(interaction.guild, nation)
        await interaction.followup.send(f"✅ Removed **{nation_cache.role.name}**")

    @remove.autocomplete("nation")
    async def _(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_cache = bot.BOT.cache[interaction.guild]
        choices = [
            app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
            for nation, nation_cache in guild_cache.nations.items()
            if current.lower() in nation.lower()
        ]
        return sorted(choices[:25], key=lambda c: c.name)

    @app_commands.command(name="reset-welcome")
    async def reset_welcome(self, interaction: discord.Interaction) -> None:
        """🔄 Reset welcome message to its default value"""
        await interaction.response.defer(ephemeral=True)
        guild_cache = bot.BOT.cache[interaction.guild]
        guild_cache.welcome_message = await guild_cache.welcome_message.edit(
            content=bot.DEFAULT_WELCOME_MESSAGE
        )
        await interaction.followup.send(
            f"✅ Reset {guild_cache.welcome_message.jump_url}"
        )

    @app_commands.command(name="replace-welcome-with")
    async def replace_welcome_with(
        self, interaction: discord.Interaction, message_id: str
    ) -> None:
        """⏭️ Replace welcome message with a new one

        Args:
            message_id: ID of the message to replace with (must be in the admin notifications channel)
        """  # noqa: E501
        await interaction.response.defer(ephemeral=True)
        guild_cache = bot.BOT.cache[interaction.guild]
        message = await guild_cache.admin_notifications_channel.fetch_message(
            int(message_id)
        )
        guild_cache.welcome_message = await guild_cache.welcome_message.edit(
            content=message.content
        )
        await interaction.followup.send(
            f"✅ Replaced {guild_cache.welcome_message.jump_url}"
        )


admin = Admin()
