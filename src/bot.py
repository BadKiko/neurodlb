"""
Telegram bot implementation using aiogram.
AI-powered bot for video processing.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_API_URL,
    MISTRAL_API_KEY,
    get_telegram_proxy_url,
)
from video_processor import VideoProcessor
from llm_handler import LLMHandler

logger = logging.getLogger(__name__)

# Global instances
llm_handler = LLMHandler(MISTRAL_API_KEY) if MISTRAL_API_KEY else None
video_processor = VideoProcessor(llm_handler)


def get_max_file_size() -> int:
    """Get maximum file size based on bot configuration."""
    # If using local Bot API, allow up to 2GB
    if TELEGRAM_BOT_API_URL:
        return 2 * 1024 * 1024 * 1024  # 2GB
    else:
        return 50 * 1024 * 1024  # 50MB for standard Telegram API


def get_recommended_max_size() -> int:
    """Get recommended maximum file size for reliable sending."""
    # Even with local Bot API, large files can cause issues
    # Recommend 500MB as a safe limit for most cases
    if TELEGRAM_BOT_API_URL:
        return 500 * 1024 * 1024  # 500MB for reliability with local API
    else:
        return 45 * 1024 * 1024  # 45MB for standard API (leave some margin)


def check_file_size_for_telegram(file_size: int) -> tuple[bool, str]:
    """
    Check if file size is suitable for Telegram and return appropriate message.

    Returns:
        tuple: (is_acceptable, message)
    """
    max_size = get_max_file_size()
    recommended_size = get_recommended_max_size()

    if file_size > max_size:
        max_size_mb = max_size // (1024 * 1024)
        return (
            False,
            f"❌ Видео слишком большое ({file_size // (1024*1024)}MB).\nМаксимальный размер: {max_size_mb}MB.",
        )

    if file_size > recommended_size:
        recommended_mb = recommended_size // (1024 * 1024)
        return (
            True,
            f"⚠️ Видео большое ({file_size // (1024*1024)}MB).\nРекомендованный размер: {recommended_mb}MB.\nОтправка может занять время...",
        )

    if file_size > 100 * 1024 * 1024:  # Warning for files > 100MB
        return (
            True,
            f"⚠️ Видео большое ({file_size // (1024*1024)}MB).\nОтправка может занять время...",
        )

    return True, ""


@dataclass
class UserVideoMemory:
    """Memory storage for user's last processed video."""

    video_url: str
    video_path: Optional[str] = None
    file_id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def is_expired(self) -> bool:
        """Check if memory is expired (older than 1 hour)."""
        return datetime.now() - self.timestamp > timedelta(hours=1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LLM context."""
        return {
            "video_url": self.video_url,
            "title": self.title,
            "duration": self.duration,
            "file_id": self.file_id,
            "timestamp": self.timestamp.isoformat(),
        }


class VideoMemoryManager:
    """Manager for user video memory."""

    def __init__(self):
        self.user_memories: Dict[int, UserVideoMemory] = {}

    def save_video_info(
        self,
        user_id: int,
        video_url: str,
        video_info: Dict[str, Any] = None,
        video_path: str = None,
        file_id: str = None,
    ) -> None:
        """Save video information for user."""
        memory = UserVideoMemory(
            video_url=video_url,
            video_path=video_path,
            file_id=file_id,
            title=video_info.get("title") if video_info else None,
            duration=video_info.get("duration") if video_info else None,
        )
        self.user_memories[user_id] = memory
        logger.info(f"Saved video memory for user {user_id}: {video_url}")

    def get_video_memory(self, user_id: int) -> Optional[UserVideoMemory]:
        """Get user's last video memory if not expired."""
        memory = self.user_memories.get(user_id)
        if memory and not memory.is_expired():
            return memory
        elif memory and memory.is_expired():
            # Clean up expired memory
            del self.user_memories[user_id]
        return None

    def clear_memory(self, user_id: int) -> None:
        """Clear user's video memory."""
        if user_id in self.user_memories:
            del self.user_memories[user_id]
            logger.info(f"Cleared video memory for user {user_id}")


# Global video memory manager
video_memory = VideoMemoryManager()


def is_video_url(text: str) -> bool:
    """Check if text contains any valid URL."""
    import re
    from urllib.parse import urlparse

    url_pattern = r"https?://[^\s]+"
    urls = re.findall(url_pattern, text)

    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return True
        except:
            continue
    return False


def extract_video_url(text: str) -> Optional[str]:
    """Extract first valid URL from text."""
    import re
    from urllib.parse import urlparse

    url_pattern = r"https?://[^\s]+"
    urls = re.findall(url_pattern, text)

    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return url
        except:
            continue
    return None


def contains_trim_request(text: str) -> bool:
    """Check if text contains trim request."""
    text_lower = text.lower()
    trim_keywords = [
        "обрежь",
        "обрезать",
        "trim",
        "cut",
        "с ",
        "от ",
        "по ",
        "до ",
        "секунд",
        "минут",
        "сек",
        "мин",
    ]
    return any(keyword in text_lower for keyword in trim_keywords)


async def start_command(message: types.Message) -> None:
    """Handle /start command."""
    user = message.from_user
    await message.reply(
        f"Привет, {user.first_name}! 🤖\n\n"
        "Я бот для обработки видео с помощью ИИ.\n"
        "Отправь мне ссылку на видео и я помогу его обработать!\n\n"
        "Используй /help для подробной информации."
    )
    logger.info(f"User {user.id} started bot")


async def help_command(message: types.Message) -> None:
    """Handle /help command."""
    user = message.from_user
    help_text = (
        "🤖 Я умный бот для обработки видео!\n\n"
        "📋 Что я умею:\n"
        "• 📥 Скачивать видео с любых платформ\n"
        "• ✂️ Обрезать видео по времени\n"
        "• 🧠 Понимать естественный язык (с помощью ИИ)\n"
        "• 🎯 Автоматически распознавать команды\n"
        "• 🧠 Помнить ваше последнее видео\n"
        "• 🚫 Фильтровать короткие видео (минимум 5 секунд)\n"
        "• 📦 Умное сжатие (только если >720p или >100MB)\n"
        "• 🖼️ Создавать превью для видео\n"
        "• 🎯 Скачивать лучшее доступное качество\n\n"
        "💡 Просто напишите что хотите сделать с видео!\n\n"
        "📝 Примеры команд:\n"
        "• https://youtube.com/watch?v=... - просто скачать\n"
        "• Скачай это видео - скачать с распознаванием\n"
        "• Обрежь с 10 по 20 секунду - обрезать\n"
        "• Скачай и обрежь с 1:30 до 2:45 - всё вместе\n"
        "• https://vimeo.com/123 от 5 до 15 - полный URL\n"
        "• Дай первые 5 сек этого видео - обрезать предыдущее\n"
        "• Обрежь это с 1:30 до 2:45 - использовать память\n\n"
        "⏰ Форматы времени:\n"
        "• с 10 по 20 (секунды)\n"
        "• от 1:30 до 2:45 (минуты:секунды)\n"
        "• с 5 до 15\n\n"
        "🎯 Бот понимает русский язык и сам определит что делать!"
    )
    await message.reply(help_text)
    logger.info(f"User {user.id} requested help")


async def handle_message(message: types.Message) -> None:
    """Handle incoming text messages using LLM analysis."""
    user = message.from_user
    text = message.text

    logger.info(f"Received message from {user.id}: {text}")

    # Use LLM for intelligent command analysis
    if llm_handler:
        await handle_llm_request(message, text)
    else:
        # Fallback to simple logic if no LLM available
        if is_video_url(text):
            await handle_video_request(message, text)
        elif contains_trim_request(text):
            await handle_trim_request(message, text)
        else:
            await message.reply("Привет! 🤖")
            logger.info(f"Replied with greeting to user {user.id}")


async def handle_llm_request(message: types.Message, text: str) -> None:
    """Handle request using LLM analysis."""
    user = message.from_user

    # Check if it's a simple video URL without additional commands
    if is_video_url(text) and not contains_trim_request(text):
        # Simple URL - skip LLM analysis for faster processing
        video_url = extract_video_url(text)
        if video_url:
            logger.info(f"Simple video URL detected, skipping LLM: {video_url}")
            await handle_download_action(message, video_url)
            return

    try:
        # Get user's video memory
        user_memory = video_memory.get_video_memory(user.id)
        memory_dict = user_memory.to_dict() if user_memory else None

        # Get LLM analysis with memory context
        llm_result = await llm_handler.process_request(text, memory_dict)

        logger.info(f"LLM analysis result: {llm_result}")

        action = llm_result["action"]
        confidence = llm_result["confidence"]
        use_last_video = llm_result.get("use_last_video", False)

        # Handle rate limit specially
        if action == "rate_limit":
            await message.reply(
                "⏳ Сервис временно перегружен. Пожалуйста, подождите 1-2 минуты и попробуйте снова.\n\n"
                "Или попробуйте отправить ссылку без дополнительного текста для быстрой обработки."
            )
            return

        # Check confidence level
        if confidence < 0.5:
            await message.reply(
                f"🤔 Не уверен в понимании запроса (уверенность: {confidence:.1%})\n\n"
                "Попробуйте перефразировать или используйте /help для примеров."
            )
            return

        # Process based on action
        if action == "download":
            await handle_download_action(message, llm_result["video_url"])

        elif action == "trim":
            await handle_trim_only_action(message, text, use_last_video)

        elif action == "download_and_trim":
            await handle_download_trim_action(message, llm_result)

        else:
            await message.reply("🤷‍♂️ Не понял запрос. Используйте /help для примеров.")

    except Exception as e:
        logger.error(f"Error in LLM request processing: {e}")
        # Fallback to simple logic
        await message.reply("🤖 Использую простой режим обработки...")

        if is_video_url(text):
            await handle_video_request(message, text)
        elif contains_trim_request(text):
            await handle_trim_request(message, text)
        else:
            await message.reply("Привет! 🤖")


async def progress_callback_factory(
    message: types.Message, status_message: types.Message = None
):
    """Create progress callback function for video processing."""

    async def progress_callback(text: str):
        # Simplified: don't send intermediate progress messages
        logger.debug(f"Progress: {text}")
        pass

    async def status_callback(text: str):
        # Update status message if provided
        if status_message:
            try:
                await status_message.edit_text(text)
            except Exception as e:
                logger.warning(f"Failed to update status message: {e}")

    return progress_callback, status_callback


async def handle_download_action(message: types.Message, video_url: str) -> None:
    """Handle simple download action."""
    if not video_url:
        await message.reply("❌ Не найдена ссылка на видео")
        return

    await handle_video_download(message, video_url)


async def handle_trim_only_action(
    message: types.Message, text: str, use_last_video: bool = False
) -> None:
    """Handle trim-only action (when no video URL provided)."""
    user = message.from_user

    if use_last_video:
        # Try to get user's last video from memory
        user_memory = video_memory.get_video_memory(user.id)
        if user_memory:
            logger.info(
                f"Using last video from memory for user {user.id}: {user_memory.video_url}"
            )
            await handle_trim_from_memory(message, user_memory, text)
            return

    # No memory available or not requested
    await message.reply(
        "✂️ Для обрезки видео нужна ссылка.\n\n"
        "Пришлите сообщение в формате:\n"
        "• Скачай https://video-url.com и обрежь с 10 по 20\n"
        "• Обрежь https://vimeo.com/123 с 1:30 до 2:45\n"
        "• Или сначала скачайте видео, а потом скажите 'обрежь это видео с 10 по 20'"
    )


async def handle_trim_from_memory(
    message: types.Message, user_memory: UserVideoMemory, text: str
) -> None:
    """Handle trimming video from user's memory."""
    user = message.from_user

    # Extract time range from text
    time_result = await llm_handler.extract_time_range(text)
    if not time_result:
        await message.reply("❌ Не удалось распознать временной интервал для обрезки")
        return

    start_time = time_result["start_time"]
    end_time = time_result["end_time"]

    logger.info(
        f"Trimming memory video for user {user.id}: {start_time}s - {end_time}s"
    )

    try:
        # Create progress callback and download video
        progress_callback = await progress_callback_factory(message)
        video_path = await video_processor.download_video(
            user_memory.video_url, progress_callback
        )

        if video_path and Path(video_path).exists():
            # Trim video
            await message.reply("✂️ Обрезаю видео...")
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                is_acceptable, size_message = check_file_size_for_telegram(file_size)

                if not is_acceptable:
                    await message.reply(size_message)
                elif size_message:  # Warning message for large files
                    await message.reply(size_message)

                if is_acceptable:
                    # Send trimmed video
                    await message.reply("📤 Отправляю видео в Telegram...")
                    # Check for thumbnail
                    thumbnail_path = (
                        Path(trimmed_path).parent
                        / f"{Path(trimmed_path).stem}_thumb.jpg"
                    )
                    thumbnail = None
                    if thumbnail_path.exists():
                        thumbnail = types.input_file.FSInputFile(thumbnail_path)

                    # Get video dimensions for proper aspect ratio
                    dimensions = await video_processor.get_video_dimensions(
                        trimmed_path
                    )
                    width, height = dimensions if dimensions else (None, None)

                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!\n\n(Из вашего предыдущего видео: {user_memory.title or 'Без названия'})",
                        supports_streaming=True,  # Enable streaming support
                        thumbnail=thumbnail,  # Add thumbnail if available
                        width=width,  # Set video width for proper aspect ratio
                        height=height,  # Set video height for proper aspect ratio
                    )

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await message.reply("❌ Не удалось обрезать видео.")
        else:
            await message.reply("❌ Не удалось скачать видео.")

    except Exception as e:
        logger.error(f"Error in trim from memory: {e}")
        await message.reply("❌ Произошла ошибка при обработке видео.")


async def handle_download_trim_action(
    message: types.Message, llm_result: Dict[str, Any]
) -> None:
    """Handle combined download and trim action."""
    video_url = llm_result["video_url"]
    start_time = llm_result["start_time"]
    end_time = llm_result["end_time"]

    if not video_url:
        await message.reply("❌ Не найдена ссылка на видео")
        return

    if start_time is None or end_time is None:
        await message.reply("❌ Не удалось распознать временной интервал")
        return

    await handle_video_download_trim(message, video_url, start_time, end_time)


async def handle_video_download(message: types.Message, video_url: str) -> None:
    """Simplified video download handler for LLM integration."""
    user = message.from_user

    logger.info(f"LLM-triggered download from {user.id}: {video_url}")

    # Send initial status message
    status_message = await message.reply("⏳ Скачиваю видео...")

    # Create progress and status callbacks
    progress_callback, status_callback = await progress_callback_factory(
        message, status_message
    )

    video_info = None
    try:
        # Download video with progress updates
        video_path = await video_processor.download_video(
            video_url, progress_callback, status_callback
        )

        if video_path and Path(video_path).exists():
            # Update status message
            await status_message.edit_text("📦 Проверяю размер файла...")

            # Check file size
            file_size = Path(video_path).stat().st_size
            is_acceptable, size_message = check_file_size_for_telegram(file_size)

            if not is_acceptable:
                await status_message.edit_text(size_message)
                return
            elif size_message:  # Warning message for large files
                await status_message.edit_text(size_message)

            # Update status message
            await status_message.edit_text("📤 Отправляю видео в Telegram...")

            # Check for thumbnail
            thumbnail_path = (
                Path(video_path).parent / f"{Path(video_path).stem}_thumb.jpg"
            )
            thumbnail = None
            if thumbnail_path.exists():
                thumbnail = types.input_file.FSInputFile(thumbnail_path)

            # Get video dimensions for proper aspect ratio
            dimensions = await video_processor.get_video_dimensions(video_path)
            width, height = dimensions if dimensions else (None, None)

            if width and height:
                logger.info(f"Video dimensions: {width}x{height}")
            else:
                logger.warning(
                    "Could not get video dimensions, using default aspect ratio"
                )

            # Send video and save file_id for future use
            logger.info(
                f"Sending video file: {video_path} ({Path(video_path).stat().st_size} bytes)"
            )
            sent_message = await message.reply_video(
                video=types.input_file.FSInputFile(video_path),
                caption="✅ Видео скачано и отправлено!",
                supports_streaming=True,  # Enable streaming support
                thumbnail=thumbnail,  # Add thumbnail if available
                width=width,  # Set video width for proper aspect ratio
                height=height,  # Set video height for proper aspect ratio
            )
            logger.info("Video sent successfully")

            # Delete status message after successful send
            await status_message.delete()

            # Save video info to memory (including file_id for future trims)
            if sent_message.video:
                # Get video info for memory if we don't have it
                if not video_info:
                    video_info = await video_processor.get_video_info(video_url)
                video_memory.save_video_info(
                    user_id=user.id,
                    video_url=video_url,
                    video_info=video_info,
                    video_path=video_path,
                    file_id=sent_message.video.file_id,
                )
                logger.info(f"Saved video to memory for user {user.id}")

            # Clean up file
            if Path(video_path).exists():
                try:
                    Path(video_path).unlink()
                    logger.info(f"Cleaned up video file: {video_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {video_path}: {e}")

        else:
            # Try to get video info to understand what went wrong
            video_info = await video_processor.get_video_info(video_url)
            if video_info:
                await message.reply(
                    f"❌ Видео найдено, но скачать не удалось.\n\n"
                    f"Возможные причины:\n"
                    f"• Видео доступно только авторизованным пользователям\n"
                    f"• Региональные ограничения\n"
                    f"• Временные технические проблемы\n\n"
                    f"Попробуйте другую ссылку или позже."
                )
            else:
                await message.reply(
                    "❌ Не удалось найти или скачать видео.\n\n"
                    "Возможные причины:\n"
                    "• Видео слишком короткое (менее 5 секунд)\n"
                    "• Неправильная ссылка\n"
                    "• Видео недоступно для скачивания\n\n"
                    "Попробуйте другую ссылку."
                )

    except Exception as e:
        logger.error(f"Error in video download: {e}")
        await message.reply("❌ Произошла ошибка при скачивании видео.")


async def handle_video_download_trim(
    message: types.Message, video_url: str, start_time: int, end_time: int
) -> None:
    """Simplified video download and trim handler for LLM integration."""
    user = message.from_user

    logger.info(
        f"LLM-triggered download+trim from {user.id}: {video_url} ({start_time}s - {end_time}s)"
    )

    # Send initial status message
    status_message = await message.reply("⏳ Скачиваю видео...")

    # Create progress and status callbacks
    progress_callback, status_callback = await progress_callback_factory(
        message, status_message
    )

    try:
        # Download video
        video_path = await video_processor.download_video(
            video_url, progress_callback, status_callback
        )

        if video_path and Path(video_path).exists():
            # Update status message
            await status_message.edit_text("✂️ Обрезаю видео...")
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Update status message
                await status_message.edit_text("📦 Проверяю размер файла...")

                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                is_acceptable, size_message = check_file_size_for_telegram(file_size)

                if not is_acceptable:
                    await status_message.edit_text(size_message)
                elif size_message:  # Warning message for large files
                    await status_message.edit_text(size_message)

                if is_acceptable:
                    # Update status message
                    await status_message.edit_text("📤 Отправляю видео в Telegram...")
                    # Check for thumbnail
                    thumbnail_path = (
                        Path(trimmed_path).parent
                        / f"{Path(trimmed_path).stem}_thumb.jpg"
                    )
                    thumbnail = None
                    if thumbnail_path.exists():
                        thumbnail = types.input_file.FSInputFile(thumbnail_path)

                    # Get video dimensions for proper aspect ratio
                    dimensions = await video_processor.get_video_dimensions(
                        trimmed_path
                    )
                    width, height = dimensions if dimensions else (None, None)

                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!",
                        supports_streaming=True,  # Enable streaming support
                        thumbnail=thumbnail,  # Add thumbnail if available
                        width=width,  # Set video width for proper aspect ratio
                        height=height,  # Set video height for proper aspect ratio
                    )

                    # Delete status message after successful send
                    await status_message.delete()

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await message.reply(
                    "❌ Не удалось обрезать видео. Проверьте временной интервал."
                )
        else:
            await message.reply("❌ Не удалось скачать видео. Проверьте ссылку.")

    except Exception as e:
        logger.error(f"Error in video download+trim: {e}")
        await message.reply("❌ Произошла ошибка при обработке видео.")


async def handle_video_request(message: types.Message, text: str) -> None:
    """Handle video download request (legacy function)."""
    user = message.from_user
    video_url = extract_video_url(text)

    if not video_url:
        await message.reply("❌ Не удалось найти ссылку на видео")
        return

    logger.info(f"Processing video request from {user.id}: {video_url}")

    # Save video to memory after successful download
    user_id = user.id

    # Create progress callback
    progress_callback = await progress_callback_factory(message)

    try:
        # Download video
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            # Check file size
            file_size = Path(video_path).stat().st_size
            is_acceptable, size_message = check_file_size_for_telegram(file_size)

            if not is_acceptable:
                await message.reply(size_message)
                return
            elif size_message:  # Warning message for large files
                await message.reply(size_message)

            if is_acceptable:
                # Send video
                await message.reply("📤 Отправляю видео в Telegram...")
                # Check for thumbnail
                thumbnail_path = (
                    Path(video_path).parent / f"{Path(video_path).stem}_thumb.jpg"
                )
                thumbnail = None
                if thumbnail_path.exists():
                    thumbnail = types.input_file.FSInputFile(thumbnail_path)

                # Get video dimensions for proper aspect ratio
                dimensions = await video_processor.get_video_dimensions(video_path)
                width, height = dimensions if dimensions else (None, None)

                sent_message = await message.reply_video(
                    video=types.input_file.FSInputFile(video_path),
                    caption="✅ Видео скачано и отправлено!",
                    supports_streaming=True,  # Enable streaming support
                    thumbnail=thumbnail,  # Add thumbnail if available
                    width=width,  # Set video width for proper aspect ratio
                    height=height,  # Set video height for proper aspect ratio
                )

                # Save video to memory for future use
                if sent_message.video:
                    video_memory.save_video_info(
                        user_id=user_id,
                        video_url=video_url,
                        video_info=None,
                        video_path=video_path,
                        file_id=sent_message.video.file_id,
                    )
                    logger.info(f"Saved video to memory for user {user_id}")

            # Clean up file
            if Path(video_path).exists():
                try:
                    Path(video_path).unlink()
                    logger.info(f"Cleaned up video file: {video_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {video_path}: {e}")

        else:
            await message.reply("❌ Не удалось скачать видео. Проверьте ссылку.")

    except Exception as e:
        logger.error(f"Error processing video request: {e}")
        await message.reply("❌ Произошла ошибка при обработке видео.")


async def handle_trim_request(message: types.Message, text: str) -> None:
    """Handle video trim request (legacy function)."""
    user = message.from_user

    logger.info(f"Processing trim request from {user.id}: {text}")

    # Check if there's a video URL in the message
    video_url = extract_video_url(text)

    if video_url:
        # Combined request: download and trim
        await handle_combined_request(message, text, video_url)
    else:
        # Trim request without URL - ask for video
        await message.reply(
            "❌ Не найдена ссылка на видео для обрезки.\n\n"
            "Отправьте сообщение в формате:\n"
            "• Скачай https://video-url.com и обрежь с 10 по 20\n"
            "• Обрежь https://vimeo.com/123 с 1:30 до 2:45"
        )


async def handle_combined_request(
    message: types.Message, text: str, video_url: str
) -> None:
    """Handle combined download and trim request (legacy function)."""
    user = message.from_user
    _ = user  # Mark user as used to avoid linter warning

    # Parse time range from text
    time_range = video_processor.parse_time_request(text)
    if not time_range:
        await message.reply(
            "❌ Не удалось распознать временной интервал.\n\n"
            "Используйте форматы:\n"
            "• с 10 по 20 секунду\n"
            "• от 1:30 до 2:45\n"
            "• с 10 до 20"
        )
        return

    start_time, end_time = time_range
    logger.info(f"Parsed time range for trimming: {start_time}s - {end_time}s")

    # Create progress callback
    progress_callback = await progress_callback_factory(message)

    try:
        # Download video
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            # Trim video
            await message.reply("✂️ Обрезаю видео...")
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                is_acceptable, size_message = check_file_size_for_telegram(file_size)

                if not is_acceptable:
                    await message.reply(size_message)
                elif size_message:  # Warning message for large files
                    await message.reply(size_message)

                if is_acceptable:
                    # Send trimmed video
                    await message.reply("📤 Отправляю видео в Telegram...")
                    # Check for thumbnail
                    thumbnail_path = (
                        Path(trimmed_path).parent
                        / f"{Path(trimmed_path).stem}_thumb.jpg"
                    )
                    thumbnail = None
                    if thumbnail_path.exists():
                        thumbnail = types.input_file.FSInputFile(thumbnail_path)

                    # Get video dimensions for proper aspect ratio
                    dimensions = await video_processor.get_video_dimensions(
                        trimmed_path
                    )
                    width, height = dimensions if dimensions else (None, None)

                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!",
                        supports_streaming=True,  # Enable streaming support
                        thumbnail=thumbnail,  # Add thumbnail if available
                        width=width,  # Set video width for proper aspect ratio
                        height=height,  # Set video height for proper aspect ratio
                    )

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await message.reply(
                    "❌ Не удалось обрезать видео. Проверьте временной интервал."
                )
        else:
            await message.reply("❌ Не удалось скачать видео. Проверьте ссылку.")

    except Exception as e:
        logger.error(f"Error processing combined request: {e}")
        await message.reply(
            "❌ Произошла ошибка при обработке запроса. Попробуйте еще раз."
        )


async def run_bot() -> None:
    """Run the Telegram bot using aiogram."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    # Get proxy settings
    proxy_url = get_telegram_proxy_url()
    if proxy_url:
        logger.info(
            f"Using proxy: {proxy_url[:20]}..."
        )  # Log only first 20 chars for security
    else:
        logger.info("No proxy configured")

    # Create bot and dispatcher
    # Use local Bot API server if configured (allows files up to 2GB)
    if TELEGRAM_BOT_API_URL:
        logger.info(f"Using local Telegram Bot API server: {TELEGRAM_BOT_API_URL}")
        # Create custom session with local API server and proxy
        if proxy_url:
            # Parse proxy URL for aiohttp
            try:
                from urllib.parse import urlparse

                parsed = urlparse(proxy_url)
                if parsed.username and parsed.password:
                    # For authenticated proxy, we need to use aiohttp_socks.ProxyConnector
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(proxy_url)
                    aiohttp_session = aiohttp.ClientSession(connector=connector)
                    # Use aiohttp session directly in Bot constructor
                    bot = Bot(
                        token=TELEGRAM_BOT_TOKEN,
                        session=aiohttp_session,
                        api=TelegramAPIServer.from_base(TELEGRAM_BOT_API_URL),
                        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                    )
                    logger.info("✅ Local Bot API enabled - file size limit increased to 2GB!")
                    return bot
                else:
                    session = AiohttpSession(
                        api=TelegramAPIServer.from_base(TELEGRAM_BOT_API_URL),
                        proxy=proxy_url,
                    )
            except Exception as e:
                logger.warning(f"Error setting up proxy for local API: {e}")
                session = AiohttpSession(
                    api=TelegramAPIServer.from_base(TELEGRAM_BOT_API_URL),
                    proxy=proxy_url,
                )
        else:
            session = AiohttpSession(
                api=TelegramAPIServer.from_base(TELEGRAM_BOT_API_URL)
            )
        
        bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        logger.info("✅ Local Bot API enabled - file size limit increased to 2GB!")
    else:
        # Create session with proxy for standard API
        if proxy_url:
            # Parse proxy URL for aiohttp
            try:
                from urllib.parse import urlparse

                parsed = urlparse(proxy_url)
                if parsed.username and parsed.password:
                    # For authenticated proxy, we need to use aiohttp_socks.ProxyConnector
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(proxy_url)
                    aiohttp_session = aiohttp.ClientSession(connector=connector)
                    # Use aiohttp session directly in Bot constructor
                    bot = Bot(
                        token=TELEGRAM_BOT_TOKEN,
                        session=aiohttp_session,
                        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                    )
                    return bot
                else:
                    session = AiohttpSession(proxy=proxy_url)
            except Exception as e:
                logger.warning(f"Error setting up proxy for aiogram: {e}")
                session = AiohttpSession(proxy=proxy_url)
        else:
            session = None

        bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    dp = Dispatcher()

    # Register handlers
    dp.message.register(start_command, F.text.startswith("/start"))
    dp.message.register(help_command, F.text.startswith("/help"))
    dp.message.register(handle_message, F.text)

    logger.info("🤖 Bot is running with aiogram...")

    # Start polling
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        raise
