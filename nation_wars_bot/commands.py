import discord
from discord import app_commands

from nation_wars_bot import bot


class CommandGroup(app_commands.Group):
    def __init__(self, bot: bot.NationWarsBot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot


@app_commands.guild_only()
class NationCommand(CommandGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(name="nation", description="user commands", *args, **kwargs)

    @app_commands.command()
    async def join(self, interaction: discord.Interaction, nation: str) -> None:
        """🎉 Join a nation

        Args:
            nation: 💡 Find the nation by typing its name (in English, sorry!)
        """
        nation = nation.title()
        await interaction.response.defer(ephemeral=True)
        nation_cache = await self.bot.try_get_nation(
            interaction.guild, nation, create_if_not_exists=True
        )

        if nation_cache is None or nation_cache.role in interaction.user.roles:
            await interaction.followup.send(
                f"❌ Invalid value **{nation}** -- please pick a valid value from the list 😤",  # noqa: E501
            )
            return

        await interaction.user.add_roles(nation_cache.role)
        await interaction.followup.send(
            content=f"✅ Joined **{nation_cache.role.name}**", ephemeral=True
        )

    @join.autocomplete("nation")
    async def _(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_cache = self.bot.cache[interaction.guild]
        choices = [
            app_commands.Choice(name=f"{emoji} {nation}", value=nation)
            for nation, emoji in bot.NATIONS.items()
            if not (
                nation in guild_cache.nations
                and guild_cache.nations[nation].role in interaction.user.roles
            )
        ]
        # special handling for "Global" nation
        if guild_cache.global_role not in interaction.user.roles:
            choices.insert(
                0,
                app_commands.Choice(name=bot.GLOBAL_ROLE_NAME, value=bot.GLOBAL_NATION),
            )
        choices = [
            choice for choice in choices if current.lower() in choice.name.lower()
        ]
        return choices[:25]

    @app_commands.command()
    async def leave(self, interaction: discord.Interaction, nation: str) -> None:
        """👋 Leave a nation

        Args:
            nation: 💡 Find the nation by typing its name (in English, sorry!)
        """
        nation = nation.title()
        await interaction.response.defer(ephemeral=True)
        nation_cache = await self.bot.try_get_nation(interaction.guild, nation)

        if nation_cache is None or nation_cache.role not in interaction.user.roles:
            await interaction.followup.send(
                f"❌ Invalid value **{nation}** -- please pick a valid value from the list 😤",  # noqa: E501
            )
            return

        await interaction.user.remove_roles(nation_cache.role)
        await interaction.followup.send(f"✅ Removed from **{nation_cache.role.name}**")

    @leave.autocomplete("nation")
    async def _(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_cache = self.bot.cache[interaction.guild]
        choices = [
            app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
            for nation, nation_cache in guild_cache.nations.items()
            if nation_cache.role in interaction.user.roles
        ]
        # special handling for "Global" nation
        if guild_cache.global_role in interaction.user.roles:
            choices.insert(
                0,
                app_commands.Choice(name=bot.GLOBAL_ROLE_NAME, value=bot.GLOBAL_NATION),
            )
        choices = [
            choice for choice in choices if current.lower() in choice.name.lower()
        ]
        return choices[:25]


@app_commands.guild_only()
@app_commands.default_permissions(manage_channels=True, manage_roles=True)
class AdminCommand(CommandGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(
            name="admin", description="admin-only commands", *args, **kwargs
        )

    @app_commands.command()
    async def remove(self, interaction: discord.Interaction, nation: str) -> None:
        """💀 Remove a nation (admin only)

        Args:
            nation: 💡 Find the nation by typing its name (in English, sorry!)
        """
        nation = nation.title()
        await interaction.response.defer(ephemeral=True)
        nation_cache = await self.bot.try_get_nation(interaction.guild, nation)

        if nation_cache is None or nation == bot.GLOBAL_NATION:
            await interaction.followup.send(
                f"ℹ️ **{nation}** is not registered -- nothing to do 😴"
            )
            return

        await self.bot.remove_nation(interaction.guild, nation)
        await interaction.followup.send(f"✅ Removed **{nation_cache.role.name}**")

    @remove.autocomplete("nation")
    async def _(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_cache = self.bot.cache[interaction.guild]
        choices = [
            app_commands.Choice(name=f"{nation_cache.emoji} {nation}", value=nation)
            for nation, nation_cache in guild_cache.nations.items()
            if current.lower() in nation.lower()
        ]
        return choices[:25]

    @app_commands.command(name="edit-welcome")
    async def edit_welcome(
        self, interaction: discord.Interaction, line1: str, line2: str, line3: str
    ) -> None:
        """Edit welcome message (admin only)

        Args:
            line1: First line
            line2: Second line
            line3: Third line
        """
        await interaction.response.defer(ephemeral=True)
        guild_cache = self.bot.cache[interaction.guild]
        guild_cache.welcome_message = await guild_cache.welcome_message.edit(
            content=f"{line1}\n{line2}\n{line3}"
        )
        await interaction.followup.send(
            f"✅ Edited message {guild_cache.welcome_message.jump_url}"
        )