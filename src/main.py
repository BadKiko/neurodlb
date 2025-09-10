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

from config import (
    validate_config,
    LOG_LEVEL,
    LOG_FILE,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_BOT_API_URL,
)
from utils import setup_logging
from bot import run_bot
from local_api_server import LocalAPIServer

logger = logging.getLogger(__name__)


async def main():
    """
    Main application entry point.
    """
    local_api_server = None

    try:
        # Setup logging
        setup_logging(level=LOG_LEVEL, log_file=LOG_FILE)
        logger.info("Starting LLM Telegram Video Bot...")

        # Validate configuration
        validate_config()

        # Start local API server if configured
        if TELEGRAM_BOT_API_URL and TELEGRAM_BOT_API_URL.startswith("http://localhost"):
            if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
                logger.error(
                    "TELEGRAM_API_ID and TELEGRAM_API_HASH are required for local server"
                )
                sys.exit(1)

            logger.info("Starting local Telegram Bot API server...")
            local_api_server = LocalAPIServer(
                api_id=TELEGRAM_API_ID,
                api_hash=TELEGRAM_API_HASH,
                port=8081,
                max_file_size=2 * 1024 * 1024 * 1024,  # 2GB
            )

            server_started = await local_api_server.start()
            if not server_started:
                logger.warning(
                    "Failed to start local API server - falling back to standard Telegram API"
                )
                logger.warning("File size limit will be 50MB instead of 2GB")
                # Continue without local API server
                local_api_server = None

        # Run the bot
        await run_bot()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)
    finally:
        # Stop local API server if it was started
        if local_api_server:
            await local_api_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
