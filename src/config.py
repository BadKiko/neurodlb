"""
Configuration management for the bot.
Handles environment variables and settings.
"""

import os
from pathlib import Path
from typing import Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"

# Telegram settings
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_API_URL: Optional[str] = os.getenv(
    "TELEGRAM_BOT_API_URL", "http://localhost:8081"
)  # For local Bot API server

# Telegram API credentials for local server
TELEGRAM_API_ID: Optional[str] = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH: Optional[str] = os.getenv("TELEGRAM_API_HASH")

# Mistral API settings
MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")

# Video processing settings
MAX_VIDEO_DURATION: int = int(os.getenv("MAX_VIDEO_DURATION", "600"))  # 10 minutes
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "2048"))  # 2GB for local API

# Logging settings
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")


def validate_config() -> None:
    """
    Validate required configuration parameters.
    Raises ValueError if required parameters are missing.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY is required")

    # Check if local API server is configured
    if TELEGRAM_BOT_API_URL and TELEGRAM_BOT_API_URL != "http://localhost:8081":
        if not TELEGRAM_API_ID:
            raise ValueError("TELEGRAM_API_ID is required for local Bot API server")
        if not TELEGRAM_API_HASH:
            raise ValueError("TELEGRAM_API_HASH is required for local Bot API server")

    # Create temp directory if it doesn't exist
    TEMP_DIR.mkdir(exist_ok=True)

    print("✅ Configuration validated successfully")
