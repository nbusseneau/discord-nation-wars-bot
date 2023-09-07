#!/usr/bin/env python3
import logging

import discord

from nation_wars_bot.bot import NationWarsBot
from nation_wars_bot.commands import JoinCommand, LeaveCommand, AdminCommands


logger = logging.getLogger()
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = NationWarsBot(intents=intents)
bot.add_command(JoinCommand(bot))
bot.add_command(LeaveCommand(bot))
bot.add_command(AdminCommands(bot))
bot.run(token=bot.bot_config.token, log_level=logging.INFO, root_logger=True)
