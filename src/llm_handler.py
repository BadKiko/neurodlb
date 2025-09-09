"""
LLM handler for Mistral API integration.
Processes natural language requests and extracts video processing parameters.
"""

import json
import logging
from typing import Optional, Dict, Any, List

from mistralai.client import MistralClient

logger = logging.getLogger(__name__)


class LLMHandler:
    """
    Handler for LLM operations with Mistral API.
    """

    def __init__(self, api_key: str):
        """
        Initialize LLM handler.

        Args:
            api_key: Mistral API key
        """
        self.api_key = api_key
        self.client = MistralClient(api_key=api_key)

        # System prompt for structured JSON responses
        self.system_prompt = """Ты - помощник для обработки запросов пользователей по работе с видео. Твоя задача - анализировать текстовые сообщения и извлекать из них параметры для обработки видео.

ПОЛЬЗОВАТЕЛЬ МОЖЕТ:
1. Прислать ссылку на видео для скачивания
2. Попросить обрезать видео с указанием времени
3. Сделать оба действия в одном сообщении
4. Использовать слова "это", "это видео", "последнее видео" для ссылки на предыдущее видео

ТВОЯ ЗАДАЧА:
Всегда отвечать ТОЛЬКО в формате JSON со следующей структурой:

{
  "action": "download|trim|download_and_trim",
  "video_url": "ссылка_на_видео_или_null",
  "start_time": число_в_секундах_или_null,
  "end_time": число_в_секундах_или_null,
  "use_last_video": true_или_false,
  "confidence": число_от_0_до_1
}

ПРАВИЛА:
- Если есть ссылка на видео - извлеки её в поле video_url
- Если есть запрос на обрезку - извлеки время в start_time и end_time
- Если есть слова "это", "это видео", "последнее видео" - установи use_last_video: true
- Если есть и ссылка и обрезка - используй action "download_and_trim"
- Если только ссылка - используй action "download"
- Если только обрезка - используй action "trim"
- use_last_video: true означает использовать предыдущее видео пользователя
- confidence - уверенность в правильности распознавания (0.0-1.0)
- Если не уверен в распознавании - ставь confidence ниже 0.5

ФОРМАТЫ ВРЕМЕНИ:
- "с 10 по 20" -> start_time: 10, end_time: 20
- "от 1:30 до 2:45" -> start_time: 90, end_time: 165
- "с 5 до 15 секунд" -> start_time: 5, end_time: 15
- "первые 5 сек" -> start_time: 0, end_time: 5
- "последние 10 сек" -> используй длительность видео минус 10"""

    async def process_request(
        self, text: str, user_memory: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process natural language request and extract parameters using Mistral API.

        Args:
            text: Natural language request

        Returns:
            Dictionary with extracted parameters
        """
        logger.info(f"Processing request with LLM: {text}")

        try:
            # Create enhanced prompt with user memory context
            enhanced_prompt = self.system_prompt
            if user_memory:
                memory_context = f"""

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
Последнее видео пользователя:
- URL: {user_memory.get('video_url', 'неизвестно')}
- Название: {user_memory.get('title', 'неизвестно')}
- Длительность: {user_memory.get('duration', 'неизвестно')} сек
- Время: {user_memory.get('timestamp', 'неизвестно')}

Используй эту информацию, если пользователь ссылается на "это видео" или "последнее видео"."""
                enhanced_prompt += memory_context

            # Create chat completion with structured output
            messages = [
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": f"Запрос пользователя: {text}"},
            ]

            response = self.client.chat(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.1,  # Low temperature for consistent structured output
                max_tokens=500,
                response_format={"type": "json_object"},  # Force JSON response
            )

            # Extract response content
            llm_response = response.choices[0].message.content.strip()

            # Parse JSON response
            try:
                result = json.loads(llm_response)
                logger.info(f"LLM parsed result: {result}")

                # Validate result structure
                if self._validate_result(result):
                    return result
                else:
                    logger.warning(f"Invalid LLM result structure: {result}")
                    return self._create_fallback_result(text)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM JSON response: {llm_response}")
                logger.error(f"JSON error: {e}")
                return self._create_fallback_result(text)

        except Exception as e:
            logger.error(f"Error calling Mistral API: {e}")
            return self._create_fallback_result(text)

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Validate LLM result structure.

        Args:
            result: Result from LLM

        Returns:
            True if valid
        """
        required_fields = [
            "action",
            "video_url",
            "start_time",
            "end_time",
            "use_last_video",
            "confidence",
        ]

        for field in required_fields:
            if field not in result:
                return False

        if result["action"] not in ["download", "trim", "download_and_trim"]:
            return False

        if not isinstance(result["confidence"], (int, float)):
            return False

        if not isinstance(result["use_last_video"], bool):
            return False

        return True

    def _create_fallback_result(self, text: str) -> Dict[str, Any]:
        """
        Create fallback result when LLM fails.

        Args:
            text: Original text

        Returns:
            Fallback result dictionary
        """
        logger.info("Using fallback parsing for: {text}")

        # Simple fallback logic
        import re

        # Check for video URL
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, text)

        # Check for trim keywords
        trim_keywords = ["обрежь", "обрезать", "с ", "от ", "по ", "до "]
        has_trim = any(keyword in text.lower() for keyword in trim_keywords)

        if urls and has_trim:
            action = "download_and_trim"
        elif urls:
            action = "download"
        elif has_trim:
            action = "trim"
        else:
            action = "unknown"

        # Check for references to last video
        last_video_keywords = [
            "это",
            "это видео",
            "последнее",
            "последнее видео",
            "предыдущее",
            "предыдущее видео",
        ]
        has_last_video_ref = any(
            keyword in text.lower() for keyword in last_video_keywords
        )

        return {
            "action": action,
            "video_url": urls[0] if urls else None,
            "start_time": None,
            "end_time": None,
            "use_last_video": has_last_video_ref,
            "confidence": 0.3,  # Low confidence for fallback
        }

    async def extract_time_range(self, text: str) -> Optional[Dict[str, int]]:
        """
        Extract time range from text using LLM.

        Args:
            text: Text containing time information

        Returns:
            Dictionary with start_time and end_time or None
        """
        result = await self.process_request(text)

        if result["action"] in ["trim", "download_and_trim"]:
            if result["start_time"] is not None and result["end_time"] is not None:
                return {
                    "start_time": result["start_time"],
                    "end_time": result["end_time"],
                }

        return None
