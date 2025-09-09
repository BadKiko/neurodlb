#!/usr/bin/env python3
"""
Main entry point for the LLM Telegram Video Bot.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import validate_config, LOG_LEVEL, LOG_FILE
from utils import setup_logging
from bot import run_bot

logger = logging.getLogger(__name__)


async def main():
    """
    Main application entry point.
    """
    try:
        # Setup logging
        setup_logging(level=LOG_LEVEL, log_file=LOG_FILE)
        logger.info("Starting LLM Telegram Video Bot...")

        # Validate configuration
        validate_config()

        # Run the bot
        await run_bot()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
