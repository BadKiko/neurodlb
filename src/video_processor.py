"""
Video processing module.
Handles video downloading, trimming and processing.
"""

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yt_dlp

from config import TEMP_DIR, MAX_VIDEO_DURATION, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)


class VideoProcessor:
    """
    Main class for video processing operations.
    """

    def __init__(self):
        """Initialize video processor."""
        self.temp_dir = Path(TEMP_DIR)
        self.temp_dir.mkdir(exist_ok=True)
        logger.info(f"VideoProcessor initialized with temp dir: {self.temp_dir}")

    def _is_valid_video_url(self, url: str) -> bool:
        """
        Validate if URL is valid for video processing.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid (yt-dlp will handle the rest)
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Accept any valid URL - yt-dlp will determine if it's supported
            return True

        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False

    def _get_yt_dlp_options(self, output_path: Path) -> dict:
        """
        Get yt-dlp options for downloading.

        Args:
            output_path: Path where to save the video

        Returns:
            Dictionary with yt-dlp options
        """
        return {
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "format": "best[height<=720]",  # Limit quality to avoid large files
            "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,  # Convert MB to bytes
            "noplaylist": True,  # Download single video, not playlist
            "quiet": True,  # Reduce output
            "no_warnings": False,  # Show warnings but not too verbose
            "extract_flat": False,
            # Additional options to bypass restrictions
            "ignoreerrors": False,  # Don't ignore errors
            "no_check_certificates": False,  # Check SSL certificates
            "sleep_interval": 1,  # Sleep between requests
            "max_sleep_interval": 5,  # Max sleep interval
            "sleep_interval_requests": 1,  # Sleep between requests to same domain
            "retries": 3,  # Number of retries
            "fragment_retries": 3,  # Number of fragment retries
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0"
            },
        }

    async def _download_with_yt_dlp(self, url: str, output_path: Path) -> Optional[str]:
        """
        Download video using yt-dlp.

        Args:
            url: Video URL
            output_path: Directory to save video

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            options = self._get_yt_dlp_options(output_path)

            # Run yt-dlp in thread pool to avoid blocking
            def download():
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info)

            result = await asyncio.to_thread(download)

            if result and Path(result).exists():
                file_size = Path(result).stat().st_size
                logger.info(
                    f"Video downloaded successfully: {result} ({file_size} bytes)"
                )
                return result
            else:
                logger.error("Download completed but file not found")
                return None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            return None

    async def download_video(self, url: str) -> Optional[str]:
        """
        Download video from URL.

        Args:
            url: Video URL to download

        Returns:
            Path to downloaded video file or None if failed
        """
        logger.info(f"Starting video download from: {url}")

        # Validate URL
        if not self._is_valid_video_url(url):
            logger.warning(f"Invalid or unsupported video URL: {url}")
            return None

        try:
            # Create unique subdirectory for this download
            import uuid

            download_dir = self.temp_dir / f"download_{uuid.uuid4().hex[:8]}"
            download_dir.mkdir(exist_ok=True)

            # Download video
            result = await self._download_with_yt_dlp(url, download_dir)

            if result:
                logger.info(f"Video successfully downloaded: {result}")
                return result
            else:
                logger.error("Video download failed")
                return None

        except Exception as e:
            logger.error(f"Error during video download: {e}")
            return None

    async def get_video_info(self, url: str) -> Optional[dict]:
        """
        Get video information without downloading.

        Args:
            url: Video URL

        Returns:
            Dictionary with video info or None if failed
        """
        try:
            if not self._is_valid_video_url(url):
                return None

            def extract_info():
                with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.to_thread(extract_info)

            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "filesize": info.get("filesize", 0),
                "uploader": info.get("uploader", "Unknown"),
                "webpage_url": info.get("webpage_url", url),
            }

        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    async def trim_video(
        self, video_path: str, start_time: int, end_time: int
    ) -> Optional[str]:
        """
        Trim video to specified time range using FFmpeg.

        Args:
            video_path: Path to input video
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            Path to trimmed video file or None if failed
        """
        logger.info(f"Trimming video {video_path} from {start_time}s to {end_time}s")

        if start_time >= end_time:
            logger.error(
                f"Invalid time range: start_time ({start_time}) >= end_time ({end_time})"
            )
            return None

        if not Path(video_path).exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        # Create unique output path
        import uuid

        input_path = Path(video_path)
        output_path = (
            input_path.parent / f"trimmed_{uuid.uuid4().hex[:8]}{input_path.suffix}"
        )

        try:
            # Calculate duration
            duration = end_time - start_time

            # FFmpeg command for trimming
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),  # Input file
                "-ss",
                str(start_time),  # Start time
                "-t",
                str(duration),  # Duration
                "-c:v",
                "copy",  # Copy video codec (no re-encoding)
                "-c:a",
                "copy",  # Copy audio codec (no re-encoding)
                "-avoid_negative_ts",
                "make_zero",  # Handle negative timestamps
                "-y",  # Overwrite output file
                str(output_path),  # Output file
            ]

            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")

            # Run FFmpeg in thread pool
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )

            if result.returncode == 0:
                # Check if output file was created and has content
                if output_path.exists() and output_path.stat().st_size > 0:
                    file_size = output_path.stat().st_size
                    logger.info(
                        f"Video trimmed successfully: {output_path} ({file_size} bytes)"
                    )
                    return str(output_path)
                else:
                    logger.error("FFmpeg completed but output file is empty or missing")
                    return None
            else:
                logger.error(f"FFmpeg failed with return code {result.returncode}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error during video trimming: {e}")
            # Clean up partial output file if it exists
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up partial file: {cleanup_error}")
            return None

    def parse_time_request(
        self, text: str, video_duration: Optional[int] = None
    ) -> Optional[tuple[int, int]]:
        """
        Parse time range from natural language text.

        Args:
            text: Text containing time information
            video_duration: Total video duration in seconds (optional)

        Returns:
            Tuple of (start_time, end_time) in seconds or None if not found
        """
        text_lower = text.lower()

        # Patterns for Russian time requests
        patterns = [
            # "с 10 по 20 секунду" / "с 10 до 20 секунды"
            r"с\s+(\d+(?::\d+)?)\s+(?:по|до)\s+(\d+(?::\d+)?)",
            # "от 10 до 20"
            r"от\s+(\d+(?::\d+)?)\s+до\s+(\d+(?::\d+)?)",
            # "10-20 секунд"
            r"(\d+(?::\d+)?)-(\d+(?::\d+)?)",
            # "с 1:30 до 2:45"
            r"с\s+(\d+:\d+)\s+(?:по|до)\s+(\d+:\d+)",
            # "от 1:30 до 2:45"
            r"от\s+(\d+:\d+)\s+до\s+(\d+:\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    start_str = match.group(1)
                    end_str = match.group(2)

                    start_time = self._parse_time_string(start_str)
                    end_time = self._parse_time_string(end_str)

                    if start_time is not None and end_time is not None:
                        # Validate against video duration if provided
                        if video_duration and end_time > video_duration:
                            logger.warning(
                                f"End time {end_time}s exceeds video duration {video_duration}s"
                            )
                            # Allow it anyway, FFmpeg will handle it

                        logger.info(f"Parsed time range: {start_time}s - {end_time}s")
                        return (start_time, end_time)

                except Exception as e:
                    logger.error(
                        f"Error parsing time from '{start_str}' to '{end_str}': {e}"
                    )
                    continue

        logger.info("No time range found in text")
        return None

    def _parse_time_string(self, time_str: str) -> Optional[int]:
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
