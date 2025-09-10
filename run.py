#!/usr/bin/env python3
"""
Simple launcher script for the LLM Telegram Video Bot.
Supports both local and cloud deployment modes.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import and run main
from main import main
import asyncio

if __name__ == "__main__":
    print("🤖 Starting LLM Telegram Video Bot...")
    print("📹 Features: Large files (2GB), thumbnails, streaming support")
    print("=" * 60)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
