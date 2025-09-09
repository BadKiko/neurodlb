"""
Utility functions for the bot.
Helper functions for common operations.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Setup logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),  # Explicitly use stdout
            *(
                logging.FileHandler(log_file, encoding="utf-8")
                for log_file in [log_file]
                if log_file
            ),
        ],
        encoding="utf-8",  # Set UTF-8 encoding for all handlers
    )


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return ".1f"
        size_bytes /= 1024.0
    return ".1f"


def cleanup_temp_files(temp_dir: Path, pattern: str = "*") -> None:
    """
    Clean up temporary files in directory.

    Args:
        temp_dir: Directory to clean
        pattern: File pattern to match (default: all files)
    """
    try:
        for file_path in temp_dir.glob(pattern):
            if file_path.is_file():
                file_path.unlink()
                logger.info(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")


def parse_time_string(time_str: str) -> Optional[int]:
    """
    Parse time string like "1:30" or "90" into seconds.

    Args:
        time_str: Time string to parse

    Returns:
        Time in seconds or None if invalid
    """
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
        else:
            return int(time_str)
    except ValueError:
        return None
