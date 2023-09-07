#!/usr/bin/env python3
import logging

from nation_wars_bot.bot import BOT
from nation_wars_bot.config import BOT_CONFIG


BOT.run(token=BOT_CONFIG.token, log_level=logging.INFO, root_logger=True)
