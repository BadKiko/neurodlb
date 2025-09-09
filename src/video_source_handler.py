"""
Video Source Handler with four-stage video extraction system.
Implements multi-stage approach to find and download videos from various sources.
"""

import asyncio
import logging
import json
from typing import Optional, Tuple
from urllib.parse import urlparse, urljoin

from playwright.async_api import async_playwright

from llm_handler import LLMHandler

logger = logging.getLogger(__name__)


class VideoSourceHandler:
    """
    Handler for extracting videos from various sources using four-stage approach.
    """

    def __init__(self, llm_handler: LLMHandler):
        """
        Initialize video source handler.

        Args:
            llm_handler: LLM handler for AI-powered analysis
        """
        self.llm_handler = llm_handler

    async def extract_video_url(
        self, url: str, progress_callback=None
    ) -> Tuple[Optional[str], str]:
        """
        Extract video URL using four-stage approach.

        Args:
            url: Original URL to process
            progress_callback: Optional callback function to notify about progress

        Returns:
            Tuple of (video_url, method_used) or (None, error_message)
        """
        logger.info("Starting four-stage video extraction for: %s", url)

        # Stage 1: Try direct yt-dlp download
        logger.info("Stage 1: Attempting direct yt-dlp download")

        video_url, method = await self._stage1_direct_yt_dlp(url)
        if video_url:
            logger.info("Stage 1 successful: %s", method)
            return video_url, method
        else:
            logger.info("Stage 1 failed, moving to next stage")

        # Stage 2: Use Playwright to find video elements (moved up)
        logger.info("Stage 2: Using Playwright to search for video elements")

        video_url, method = await self._stage3_playwright_search(url)
        if video_url:
            logger.info("Stage 2 successful: %s", method)
            return video_url, method
        else:
            logger.info("Stage 2 failed, moving to next stage")

        # Stage 3: Use LLM to find video on the page (moved down)
        logger.info("Stage 3: Using LLM to find video on the page")

        video_url, method = await self._stage2_llm_find_video(url)
        if video_url:
            logger.info("Stage 3 successful: %s", method)
            return video_url, method
        else:
            logger.info("Stage 3 failed, moving to final stage")

        # Stage 4: Ask LLM to generate extraction code
        logger.info("Stage 4: Asking LLM to generate extraction code")

        video_url, method = await self._stage4_llm_generate_code(url)
        if video_url:
            logger.info("Stage 4 successful: %s", method)
            return video_url, method
        else:
            logger.info("All stages failed")

        # All stages failed
        error_msg = (
            "Не удалось найти видео на данной странице. Попробуйте другую ссылку."
        )
        logger.warning("All stages failed for URL: %s", url)
        return None, error_msg

    async def _stage1_direct_yt_dlp(self, url: str) -> Tuple[Optional[str], str]:
        """
        Stage 1: Try direct yt-dlp download with actual file download.

        Args:
            url: URL to test

        Returns:
            Tuple of (video_url, method_description) or (None, "")
        """
        import tempfile
        import os
        from pathlib import Path

        try:
            # Create temporary directory for test download
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Try actual download with yt-dlp
                def test_download():
                    try:
                        import yt_dlp

                        options = {
                            "outtmpl": str(temp_path / "%(title)s.%(ext)s"),
                            "format": "best[height<=360]",  # Low quality for test
                            "max_filesize": 50 * 1024 * 1024,  # 50MB limit
                            "quiet": True,
                            "no_warnings": True,
                            "noplaylist": True,
                        }

                        with yt_dlp.YoutubeDL(options) as ydl:
                            info = ydl.extract_info(url, download=True)
                            filename = ydl.prepare_filename(info)

                            # Check if file was actually downloaded
                            if filename and Path(filename).exists():
                                file_size = Path(filename).stat().st_size
                                if file_size > 0:
                                    return filename, info
                                else:
                                    logger.debug("Stage 1: Downloaded file is empty")
                            else:
                                logger.debug("Stage 1: Downloaded file not found")

                            return None, info

                    except Exception as e:
                        logger.debug("Stage 1 yt-dlp download failed: %s", e)
                        return None, None

                result, info = await asyncio.to_thread(test_download)

                if result and Path(result).exists():
                    # Clean up test file
                    try:
                        Path(result).unlink()
                        logger.debug("Stage 1: Cleaned up test file")
                    except Exception as e:
                        logger.debug("Stage 1: Failed to clean up test file: %s", e)

                    return url, "прямое скачивание через yt-dlp"

                # If we have info but no file, yt-dlp couldn't download
                if info:
                    logger.debug("Stage 1: yt-dlp extracted info but download failed")
                else:
                    logger.debug("Stage 1: yt-dlp completely failed")

                return None, ""

        except Exception as e:
            logger.debug("Stage 1 error: %s", e)
            return None, ""

    async def _stage2_llm_find_video(self, url: str) -> Tuple[Optional[str], str]:
        """
        Stage 2: Use LLM to find video URL on the page.

        Args:
            url: Original URL

        Returns:
            Tuple of (video_url, method_description) or (None, "")
        """
        try:
            # Get page content using simple HTTP request
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return None, ""

                    html_content = await response.text()

            # Ask LLM to find video URLs in FULL HTML
            prompt = f"""
            Проанализируй ПОЛНЫЙ HTML код страницы и найди ВСЕ ссылки на видео.
            Страница: {url}

            Ищи ТЩАТЕЛЬНО:
            1. Ссылки в тегах <a> с href содержащими "video"
            2. Ссылки в атрибутах data-video
            3. Ссылки на видео файлы (.mp4, .webm, .avi, etc.)
            4. Ссылки в тегах <video> и их source
            5. Любые URL с паттернами: /video, video-, Video, VIDEO

            ОСОБОЕ ВНИМАНИЕ на VK.COM паттерны:
            - /video-79002029_456269004
            - /video?list=
            - data-video="-79002029_456269004"

            Верни ТОЛЬКО JSON в формате:
            {{
                "video_urls": ["url1", "url2", "url3", ...],
                "confidence": 0.0-1.0
            }}

            Найди МАКСИМУМ ссылок, даже если они кажутся похожими.
            """

            # Get LLM response with full HTML
            messages = [
                {
                    "role": "system",
                    "content": "Ты - эксперт по анализу HTML VK.COM и поиску видео ссылок.",
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nПОЛНЫЙ HTML страницы:\n{html_content}",
                },
            ]

            # Note: Using the same Mistral client from llm_handler
            response = self.llm_handler.client.chat(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )

            llm_response = response.choices[0].message.content.strip()
            result = json.loads(llm_response)

            if result.get("confidence", 0) > 0.3 and result.get("video_urls"):
                # Test the first video URL
                video_url = result["video_urls"][0]

                # Validate URL format
                if self._is_valid_video_url(video_url):
                    return (
                        video_url,
                        f"найдено через ИИ анализ страницы (confidence: {result['confidence']:.1%})",
                    )

        except (aiohttp.ClientError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("Stage 2 error: %s", e)

        return None, ""

    async def _stage3_playwright_search(self, url: str) -> Tuple[Optional[str], str]:
        """
        Stage 3: Use Playwright to search for video elements on the page.

        Args:
            url: Original URL

        Returns:
            Tuple of (video_url, method_description) or (None, "")
        """
        try:
            async with async_playwright() as p:
                # Try to use system browser first
                try:
                    browser = await p.chromium.launch(
                        headless=True, executable_path="/usr/local/bin/google-chrome"
                    )
                    logger.debug("Using system Google Chrome browser")
                except Exception:
                    # Fallback to playwright browser
                    try:
                        browser = await p.chromium.launch(headless=True)
                        logger.debug("Using Playwright Chromium browser")
                    except Exception as e:
                        logger.warning("Failed to launch any Chromium browser: %s", e)
                        return None, ""

                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()

                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")

                    # Wait a bit for dynamic content
                    await page.wait_for_timeout(2000)

                    # Try to find video elements
                    video_selectors = [
                        "video[src]",
                        "video source[src]",
                        "video[data-src]",
                        ".video-player video",
                        ".player video",
                        "[class*='video'] video",
                        "[id*='video'] video",
                    ]

                    for selector in video_selectors:
                        try:
                            video_element = page.locator(selector).first
                            if await video_element.is_visible():
                                src = await video_element.get_attribute("src")
                                if src:
                                    video_url = urljoin(url, src)
                                    if self._is_valid_video_url(video_url):
                                        await browser.close()
                                        return (
                                            video_url,
                                            f"найдено через Playwright ({selector})",
                                        )
                        except Exception:
                            continue

                    # Try to find ALL video-related URLs in page content
                    video_urls = await page.evaluate(
                        """
                        () => {
                            const urls = [];
                            const videoExtensions = ['.mp4', '.webm', '.avi', '.mov', '.wmv', '.flv', '.m3u8', '.m3u'];

                            // Find all links with video in href
                            const allLinks = document.querySelectorAll('a[href]');
                            allLinks.forEach(link => {
                                const href = link.href;
                                // Check for video extensions OR video patterns
                                if (videoExtensions.some(ext => href.includes(ext)) ||
                                    href.includes('/video') ||
                                    href.includes('video-') ||
                                    href.includes('Video') ||
                                    href.includes('VIDEO')) {
                                    urls.push(href);
                                }
                            });

                            // Find links with data-video attribute (VK style)
                            const dataVideoElements = document.querySelectorAll('[data-video]');
                            dataVideoElements.forEach(el => {
                                const videoId = el.getAttribute('data-video');
                                if (videoId) {
                                    // Try to construct VK video URL
                                    const baseUrl = window.location.origin;
                                    const videoUrl = `${baseUrl}/video${videoId}`;
                                    urls.push(videoUrl);
                                }
                            });

                            // Find video sources in script tags
                            const scripts = document.querySelectorAll('script');
                            scripts.forEach(script => {
                                const content = script.textContent || '';
                                // Look for VK video patterns in scripts
                                const vkMatches = content.match(/video-[0-9_-]+/g);
                                if (vkMatches) {
                                    vkMatches.forEach(match => {
                                        const baseUrl = window.location.origin;
                                        urls.push(`${baseUrl}/${match}`);
                                    });
                                }
                                // Also look for direct video URLs
                                const urlMatches = content.match(/https?:\/\/[^\s"']+\.(mp4|webm|avi|mov|wmv|flv|m3u8|m3u)/gi);
                                if (urlMatches) {
                                    urls.push(...urlMatches);
                                }
                            });

                            return [...new Set(urls)]; // Remove duplicates
                        }
                    """
                    )

                    logger.debug(
                        f"Stage 3: Found {len(video_urls)} potential video URLs"
                    )

                    # Test each URL with yt-dlp (not just validate format)
                    for video_url in video_urls[:10]:  # Test first 10 URLs
                        if video_url and video_url.startswith(("http://", "https://")):
                            logger.debug(
                                f"Stage 3: Testing URL with yt-dlp: {video_url}"
                            )

                            # Quick test if yt-dlp can handle this URL
                            try:
                                import yt_dlp

                                with yt_dlp.YoutubeDL(
                                    {"quiet": True, "no_warnings": True}
                                ) as ydl:
                                    info = ydl.extract_info(video_url, download=False)
                                    if info:
                                        await browser.close()
                                        return (
                                            video_url,
                                            f"найдено через Playwright + yt-dlp тест ({len(video_urls)} URLs найдено)",
                                        )
                            except Exception as e:
                                logger.debug(
                                    f"Stage 3: URL {video_url} failed yt-dlp test: {e}"
                                )
                                continue

                finally:
                    await browser.close()

        except Exception as e:
            logger.debug("Stage 3 error: %s", e)

        return None, ""

    async def _stage4_llm_generate_code(self, url: str) -> Tuple[Optional[str], str]:
        """
        Stage 4: Ask LLM to generate code for video extraction.

        Args:
            url: Original URL

        Returns:
            Tuple of (video_url, method_description) or (None, "")
        """
        try:
            # Get page content
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return None, ""

                    html_content = await response.text()

            # Ask LLM to generate Python code for video extraction
            prompt = f"""
            Создай Python код для извлечения видео с этой страницы: {url}

            HTML страницы:
            {html_content[:3000]}

            Код должен:
            1. Использовать requests или aiohttp для загрузки страницы
            2. Найти ссылки на видео файлы
            3. Вернуть первую найденную ссылку на видео

            Верни ТОЛЬКО JSON в формате:
            {{
                "extraction_code": "python_code_here",
                "video_url": "extracted_url_or_null"
            }}

            Если не можешь создать код, верни video_url: null
            """

            messages = [
                {
                    "role": "system",
                    "content": "Ты - эксперт Python разработчик, специализирующийся на веб-скрапинге.",
                },
                {"role": "user", "content": prompt},
            ]

            response = self.llm_handler.client.chat(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.1,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            llm_response = response.choices[0].message.content.strip()
            result = json.loads(llm_response)

            if result.get("video_url") and self._is_valid_video_url(
                result["video_url"]
            ):
                return result["video_url"], "найдено через ИИ-генерированный код"

        except (aiohttp.ClientError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("Stage 4 error: %s", e)

        return None, ""

    def _is_valid_video_url(self, url: str) -> bool:
        """
        Check if URL is a valid video URL.

        Args:
            url: URL to validate

        Returns:
            True if URL looks like a video URL
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Check for video file extensions
            video_extensions = [
                ".mp4",
                ".webm",
                ".avi",
                ".mov",
                ".wmv",
                ".flv",
                ".m3u8",
                ".m3u",
            ]
            if any(ext in url.lower() for ext in video_extensions):
                return True

            # Check for common video hosting domains
            video_domains = [
                "youtube.com",
                "youtu.be",
                "vimeo.com",
                "dailymotion.com",
                "twitch.tv",
                "facebook.com",
                "instagram.com",
                "tiktok.com",
                "twitter.com",
                "vk.com",
                "ok.ru",
                "rutube.ru",
            ]

            if any(domain in parsed.netloc.lower() for domain in video_domains):
                return True

            return True  # Accept any valid URL, let yt-dlp handle it

        except (ValueError, TypeError):
            return False
