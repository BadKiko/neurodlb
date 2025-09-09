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

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import TELEGRAM_BOT_TOKEN, MISTRAL_API_KEY
from video_processor import VideoProcessor
from llm_handler import LLMHandler

logger = logging.getLogger(__name__)

# Global instances
llm_handler = LLMHandler(MISTRAL_API_KEY) if MISTRAL_API_KEY else None
video_processor = VideoProcessor(llm_handler)


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
        "• 🧠 Помнить ваше последнее видео\n\n"
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


async def progress_callback_factory(message: types.Message):
    """Create progress callback function for video processing."""

    async def progress_callback(text: str):
        try:
            await message.reply(text)
        except Exception as e:
            logger.warning(f"Failed to send progress message: {e}")

    return progress_callback


async def handle_download_action(message: types.Message, video_url: str) -> None:
    """Handle simple download action."""
    if not video_url:
        await message.reply("❌ Не найдена ссылка на видео")
        return

    # Notify user about processing
    await message.reply(
        "📥 Обрабатываю ссылку...\n" "⏳ Проверяю различные методы скачивания видео."
    )

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

    # Start processing
    processing_msg = await message.reply("⏳ Обрабатываю ваше предыдущее видео...")

    try:
        # Always need to download and trim video, even if we have file_id
        # file_id is just for reference, we still need to process the video
        await processing_msg.edit_text("🔄 Загружаю видео для обрезки...")

        # Create progress callback and download video
        progress_callback = await progress_callback_factory(message)
        video_path = await video_processor.download_video(
            user_memory.video_url, progress_callback
        )

        if video_path and Path(video_path).exists():
            await processing_msg.edit_text("✂️ Обрезаю видео...")

            # Trim video
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                max_size = 50 * 1024 * 1024  # 50MB

                if file_size > max_size:
                    await processing_msg.edit_text(
                        f"❌ Обрезанное видео слишком большое ({file_size // (1024*1024)}MB).\n"
                        f"Попробуйте меньший временной интервал."
                    )
                else:
                    # Send trimmed video
                    await processing_msg.edit_text("📤 Отправляю обрезанное видео...")
                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!\n\n(Из вашего предыдущего видео: {user_memory.title or 'Без названия'})",
                    )
                    await processing_msg.delete()

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await processing_msg.edit_text("❌ Не удалось обрезать видео.")
        else:
            await processing_msg.edit_text("❌ Не удалось скачать видео.")

    except Exception as e:
        logger.error(f"Error in trim from memory: {e}")
        await processing_msg.edit_text("❌ Произошла ошибка при обработке видео.")


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

    # Create progress callback
    progress_callback = await progress_callback_factory(message)

    # Send initial processing message
    processing_msg = await message.reply("⏳ Подготавливаю скачивание...")

    try:
        # Get video info first
        video_info = await video_processor.get_video_info(video_url)
        if video_info:
            info_text = (
                f"📹 Найдено видео:\n"
                f"🎬 {video_info['title']}\n"
                f"👤 {video_info['uploader']}\n"
                f"⏱️ {video_info['duration']} сек\n\n"
                f"🔄 Начинаю скачивание..."
            )
            await processing_msg.edit_text(info_text)

        # Download video with progress updates
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            # Check file size
            file_size = Path(video_path).stat().st_size
            max_size = 50 * 1024 * 1024  # 50MB

            if file_size > max_size:
                await processing_msg.edit_text(
                    f"❌ Видео слишком большое ({file_size // (1024*1024)}MB).\n"
                    f"Telegram ограничивает размер файла до 50MB."
                )
            else:
                # Send video
                await processing_msg.edit_text("📤 Отправляю видео...")

                # Send video and save file_id for future use
                sent_message = await message.reply_video(
                    video=types.input_file.FSInputFile(video_path),
                    caption="✅ Видео успешно скачано!",
                )

                # Save video info to memory (including file_id for future trims)
                if sent_message.video:
                    video_memory.save_video_info(
                        user_id=user.id,
                        video_url=video_url,
                        video_info=video_info,
                        video_path=video_path,
                        file_id=sent_message.video.file_id,
                    )
                    logger.info(f"Saved video to memory for user {user.id}")

                await processing_msg.delete()

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
                await processing_msg.edit_text(
                    f"❌ Видео найдено ({video_info['title']}), но скачать не удалось.\n\n"
                    f"Возможные причины:\n"
                    f"• Видео доступно только авторизованным пользователям\n"
                    f"• Региональные ограничения\n"
                    f"• Временные технические проблемы\n\n"
                    f"Попробуйте другую ссылку или позже."
                )
            else:
                await processing_msg.edit_text(
                    "❌ Не удалось найти или скачать видео.\n"
                    "Проверьте правильность ссылки."
                )

    except Exception as e:
        logger.error(f"Error in video download: {e}")
        await processing_msg.edit_text("❌ Произошла ошибка при скачивании видео.")


async def handle_video_download_trim(
    message: types.Message, video_url: str, start_time: int, end_time: int
) -> None:
    """Simplified video download and trim handler for LLM integration."""
    user = message.from_user

    logger.info(
        f"LLM-triggered download+trim from {user.id}: {video_url} ({start_time}s - {end_time}s)"
    )

    # Start processing
    processing_msg = await message.reply("⏳ Обрабатываю видео...")

    try:
        # Get video info first
        video_info = await video_processor.get_video_info(video_url)
        if video_info:
            info_text = (
                f"📹 Найдено видео:\n"
                f"🎬 {video_info['title']}\n"
                f"⏱️ Обрезка: {start_time}сек - {end_time}сек\n\n"
                f"🔄 Начинаю скачивание..."
            )
            await processing_msg.edit_text(info_text)

        # Download video
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            await processing_msg.edit_text("✂️ Обрезаю видео...")

            # Trim video
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                max_size = 50 * 1024 * 1024  # 50MB

                if file_size > max_size:
                    await processing_msg.edit_text(
                        f"❌ Обрезанное видео слишком большое ({file_size // (1024*1024)}MB).\n"
                        f"Попробуйте меньший временной интервал."
                    )
                else:
                    # Send trimmed video
                    await processing_msg.edit_text("📤 Отправляю обрезанное видео...")
                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!",
                    )
                    await processing_msg.delete()

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await processing_msg.edit_text(
                    "❌ Не удалось обрезать видео. Проверьте временной интервал."
                )
        else:
            await processing_msg.edit_text(
                "❌ Не удалось скачать видео. Проверьте ссылку."
            )

    except Exception as e:
        logger.error(f"Error in video download+trim: {e}")
        await processing_msg.edit_text("❌ Произошла ошибка при обработке видео.")


async def handle_video_request(message: types.Message, text: str) -> None:
    """Handle video download request (legacy function)."""
    user = message.from_user
    video_url = extract_video_url(text)

    if not video_url:
        await message.reply("❌ Не удалось найти ссылку на видео")
        return

    logger.info(f"Processing video request from {user.id}: {video_url}")

    # Send processing message
    processing_msg = await message.reply("⏳ Скачиваю видео...")

    try:
        # Get video info first
        video_info = await video_processor.get_video_info(video_url)
        if video_info:
            info_text = (
                f"📹 Найдено видео:\n"
                f"🎬 {video_info['title']}\n"
                f"👤 {video_info['uploader']}\n"
                f"⏱️ {video_info['duration']} сек\n\n"
                f"🔄 Начинаю скачивание..."
            )
            await processing_msg.edit_text(info_text)

        # Download video
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            # Check file size
            file_size = Path(video_path).stat().st_size
            max_size = 50 * 1024 * 1024  # 50MB

            if file_size > max_size:
                await processing_msg.edit_text(
                    f"❌ Видео слишком большое ({file_size // (1024*1024)}MB).\n"
                    f"Telegram ограничивает размер файла до 50MB."
                )
            else:
                # Send video
                await processing_msg.edit_text("📤 Отправляю видео...")
                await message.reply_video(
                    video=types.input_file.FSInputFile(video_path),
                    caption="✅ Видео успешно скачано!",
                )
                await processing_msg.delete()

            # Clean up file
            if Path(video_path).exists():
                try:
                    Path(video_path).unlink()
                    logger.info(f"Cleaned up video file: {video_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {video_path}: {e}")

        else:
            await processing_msg.edit_text(
                "❌ Не удалось скачать видео. Проверьте ссылку."
            )

    except Exception as e:
        logger.error(f"Error processing video request: {e}")
        await processing_msg.edit_text("❌ Произошла ошибка при обработке видео.")


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

    # Start processing
    processing_msg = await message.reply("⏳ Обрабатываю запрос на обрезку видео...")

    try:
        # Get video info first
        video_info = await video_processor.get_video_info(video_url)
        if video_info:
            info_text = (
                f"📹 Найдено видео:\n"
                f"🎬 {video_info['title']}\n"
                f"⏱️ Обрезка: {start_time}сек - {end_time}сек\n\n"
                f"🔄 Начинаю скачивание и обрезку..."
            )
            await processing_msg.edit_text(info_text)

        # Download video
        video_path = await video_processor.download_video(video_url, progress_callback)

        if video_path and Path(video_path).exists():
            await processing_msg.edit_text("✂️ Обрезаю видео...")

            # Trim video
            trimmed_path = await video_processor.trim_video(
                video_path, start_time, end_time
            )

            if trimmed_path and Path(trimmed_path).exists():
                # Check file size
                file_size = Path(trimmed_path).stat().st_size
                max_size = 50 * 1024 * 1024  # 50MB

                if file_size > max_size:
                    await processing_msg.edit_text(
                        f"❌ Обрезанное видео слишком большое ({file_size // (1024*1024)}MB).\n"
                        f"Попробуйте меньший временной интервал."
                    )
                else:
                    # Send trimmed video
                    await processing_msg.edit_text("📤 Отправляю обрезанное видео...")
                    await message.reply_video(
                        video=types.input_file.FSInputFile(trimmed_path),
                        caption=f"✅ Видео обрезано с {start_time} по {end_time} секунду!",
                    )
                    await processing_msg.delete()

                # Clean up files
                for path in [video_path, trimmed_path]:
                    if path and Path(path).exists():
                        try:
                            Path(path).unlink()
                            logger.info(f"Cleaned up file: {path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up file {path}: {e}")

            else:
                await processing_msg.edit_text(
                    "❌ Не удалось обрезать видео. Проверьте временной интервал."
                )
        else:
            await processing_msg.edit_text(
                "❌ Не удалось скачать видео. Проверьте ссылку."
            )

    except Exception as e:
        logger.error(f"Error processing combined request: {e}")
        await processing_msg.edit_text(
            "❌ Произошла ошибка при обработке запроса. Попробуйте еще раз."
        )


async def run_bot() -> None:
    """Run the Telegram bot using aiogram."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    # Create bot and dispatcher
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
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
