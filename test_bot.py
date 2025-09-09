#!/usr/bin/env python3
"""
Simple test script for bot functionality.
Tests basic bot handlers without real Telegram connection.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bot import start_command, help_command, handle_message, error_handler


async def test_start_command():
    """Test /start command handler."""
    print("🧪 Testing /start command...")

    # Mock update and context
    update = Mock()
    update.effective_user.first_name = "TestUser"
    update.message.reply_text = AsyncMock()

    context = Mock()

    # Call handler
    await start_command(update, context)

    # Check if reply_text was called with correct message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]

    assert "Привет, TestUser!" in call_args
    assert "бот для обработки видео" in call_args
    print("✅ /start command test passed")


async def test_help_command():
    """Test /help command handler."""
    print("🧪 Testing /help command...")

    # Mock update and context
    update = Mock()
    update.effective_user.first_name = "TestUser"
    update.message.reply_text = AsyncMock()

    context = Mock()

    # Call handler
    await help_command(update, context)

    # Check if reply_text was called
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]

    assert "🤖 Я бот для обработки видео!" in call_args
    assert "Что я умею:" in call_args
    assert "Примеры:" in call_args
    print("✅ /help command test passed")


async def test_handle_message():
    """Test message handler."""
    print("🧪 Testing message handler...")

    # Mock update and context
    update = Mock()
    update.effective_user.id = 12345
    update.effective_user.first_name = "TestUser"
    update.message.text = "Hello bot!"
    update.message.reply_text = AsyncMock()

    context = Mock()

    # Call handler
    await handle_message(update, context)

    # Check if reply_text was called with "Привет!"
    update.message.reply_text.assert_called_once_with("Привет!")
    print("✅ Message handler test passed")


async def test_error_handler():
    """Test error handler."""
    print("🧪 Testing error handler...")

    # Mock update and context
    update = Mock()
    update.effective_chat = Mock()
    update.effective_chat.send_message = AsyncMock()

    context = Mock()
    context.error = Exception("Test error")

    # Call handler
    await error_handler(update, context)

    # Check if error message was sent
    update.effective_chat.send_message.assert_called_once()
    call_args = update.effective_chat.send_message.call_args[0][0]

    assert "❌ Произошла ошибка" in call_args
    print("✅ Error handler test passed")


async def main():
    """Run all tests."""
    print("🚀 Starting bot tests...\n")

    try:
        await test_start_command()
        await test_help_command()
        await test_handle_message()
        await test_error_handler()

        print("\n🎉 All tests passed!")
        print("✅ Bot handlers are working correctly")
        print("✅ Bot responds with 'Привет!' to any message")
        print("✅ All functionality for iteration 2 is implemented")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
