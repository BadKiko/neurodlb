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

# Mistral API settings
MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")

# Video processing settings
MAX_VIDEO_DURATION: int = int(os.getenv("MAX_VIDEO_DURATION", "300"))  # 5 minutes
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

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

    # Create temp directory if it doesn't exist
    TEMP_DIR.mkdir(exist_ok=True)

    print("✅ Configuration validated successfully")
