"""
Video processing module.
Handles video downloading, trimming and processing.
"""

import asyncio
import glob
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yt_dlp

from config import TEMP_DIR, MAX_VIDEO_DURATION, MAX_FILE_SIZE_MB
from video_source_handler import VideoSourceHandler

logger = logging.getLogger(__name__)


class VideoProcessor:
    """
    Main class for video processing operations.
    """

    def __init__(self, llm_handler=None):
        """Initialize video processor."""
        self.temp_dir = Path(TEMP_DIR)
        self.temp_dir.mkdir(exist_ok=True)
        self.source_handler = VideoSourceHandler(llm_handler) if llm_handler else None
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
            "restrictfilenames": True,  # Sanitize filenames
            "format": "best/bestvideo+bestaudio/best",  # Best quality with fallbacks
            "noplaylist": True,  # Download single video, not playlist
            "quiet": False,  # Show output for debugging
            "no_warnings": False,  # Show warnings
            "extract_flat": False,
            # Additional options to bypass restrictions
            "ignoreerrors": True,  # Ignore errors and try to continue
            "no_check_certificates": False,  # Check SSL certificates
            "prefer_ffmpeg": True,  # Use ffmpeg for better compatibility
            "retries": 5,  # Number of retries
            "fragment_retries": 5,  # Number of fragment retries
            "concurrent_fragment_downloads": 4,  # Allow concurrent downloads for better speed
            "http_chunk_size": 1048576,  # 1MB chunks for better performance
            "buffersize": 1024,  # Buffer size in KB
            # Speed optimization
            "throttled_rate": None,  # No speed throttling
            "no_sleep": False,  # Allow sleeping but with longer intervals
            "sleep_interval": 0,  # No sleep between requests for better speed
            "sleep_interval_requests": 0,  # No sleep between requests to same domain
            "max_sleep_interval": 0,  # No max sleep interval
            # Additional performance options
            "external_downloader": "aria2c",  # Try aria2c first for better speed
            "external_downloader_args": {
                "aria2c": [
                    "--min-split-size=1M",
                    "--max-connection-per-server=16",
                    "--max-concurrent-downloads=4",
                    "--split=16",
                    "--optimize-concurrent-downloads",
                    "--allow-overwrite=true",
                    "--auto-file-renaming=false",
                ],
                "ffmpeg": ["-hide_banner", "-loglevel", "warning"],
            },
            # Universal options for all platforms
            "continue": True,  # Resume interrupted downloads
            "keepvideo": False,  # Don't keep intermediate files
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
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "video",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Priority": "u=1",
                "Range": "bytes=0-",
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
                try:
                    with yt_dlp.YoutubeDL(options) as ydl:
                        # Get info first without downloading to prepare filename correctly
                        info = ydl.extract_info(url, download=False)
                        expected_filename = ydl.prepare_filename(info)
                        logger.info(f"Expected filename: {expected_filename}")

                        # Now download with the same ydl instance
                        ydl.download([url])

                        # After download, check for the actual file
                        # First try the expected filename
                        if expected_filename and Path(expected_filename).exists():
                            file_size = Path(expected_filename).stat().st_size
                            if file_size > 0:
                                logger.info(
                                    f"File found at expected location: {expected_filename}"
                                )
                                return expected_filename, info
                            else:
                                logger.warning(
                                    f"Downloaded file is empty: {expected_filename}"
                                )

                        # If expected file not found or empty, scan the directory

                        video_extensions = [
                            "*.mp4",
                            "*.webm",
                            "*.avi",
                            "*.mov",
                            "*.wmv",
                            "*.flv",
                            "*.m3u8",
                            "*.m3u",
                        ]

                        # Get the directory where file should be
                        download_dir = (
                            Path(expected_filename).parent
                            if expected_filename
                            else output_path
                        )

                        logger.info(
                            f"Scanning directory {download_dir} for video files"
                        )

                        # Scan for any video files in the download directory
                        for ext in video_extensions:
                            pattern = str(download_dir / ext)
                            found_files = glob.glob(pattern)
                            if found_files:
                                for found_file in found_files:
                                    file_size = Path(found_file).stat().st_size
                                    if file_size > 0:
                                        logger.info(
                                            f"Found video file: {found_file} ({file_size} bytes)"
                                        )
                                        return found_file, info

                        # If still no file found, check the entire temp directory
                        logger.warning(
                            "No video files found in download directory, scanning temp directory"
                        )
                        temp_dir = output_path.parent
                        for ext in video_extensions:
                            pattern = str(temp_dir / "**" / ext)
                            found_files = glob.glob(pattern, recursive=True)
                            if found_files:
                                for found_file in found_files:
                                    # Check if file was created recently (within last 5 minutes)
                                    mtime = Path(found_file).stat().st_mtime
                                    if time.time() - mtime < 300:  # 5 minutes
                                        file_size = Path(found_file).stat().st_size
                                        if file_size > 0:
                                            logger.info(
                                                f"Found recent video file: {found_file} ({file_size} bytes)"
                                            )
                                            return found_file, info

                        logger.error("No video files found after download")
                        return None, info

                except Exception as e:
                    logger.error(f"yt-dlp download failed: {e}")
                    return None, None

            result, info = await asyncio.to_thread(download)

            if result and Path(result).exists():
                file_size = Path(result).stat().st_size
                logger.info(
                    f"Video downloaded successfully: {result} ({file_size} bytes)"
                )
                return result
            else:
                # Try fallback formats if the first attempt failed
                logger.warning("Primary format failed, trying fallback formats...")
                fallback_result = await self._download_with_fallback_formats(
                    url, output_path
                )
                if fallback_result:
                    return fallback_result

                # Check if we have info but no file - this indicates yt-dlp couldn't download
                if info:
                    logger.warning("yt-dlp extracted info but failed to download file")
                else:
                    logger.error("yt-dlp completely failed to process URL")
                return None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            return None

    async def _download_with_fallback_formats(
        self, url: str, output_path: Path
    ) -> Optional[str]:
        """
        Try downloading with different fallback formats when the primary format fails.

        Args:
            url: Video URL
            output_path: Directory to save video

        Returns:
            Path to downloaded file or None if failed
        """
        fallback_formats = [
            "best[height<=1080]",  # 1080p
            "best[height<=720]",  # 720p
            "best[height<=480]",  # 480p
            "worst",  # Any format
            "bestaudio",  # Audio only as fallback
        ]

        for format_spec in fallback_formats:
            try:
                logger.info(f"Trying fallback format: {format_spec}")

                def fallback_download():
                    try:
                        options = self._get_yt_dlp_options(output_path)
                        options["format"] = format_spec  # Override format

                        with yt_dlp.YoutubeDL(options) as ydl:
                            info = ydl.extract_info(url, download=False)
                            expected_filename = ydl.prepare_filename(info)
                            ydl.download([url])

                            # Check if file was created
                            if expected_filename and Path(expected_filename).exists():
                                file_size = Path(expected_filename).stat().st_size
                                if file_size > 0:
                                    logger.info(
                                        f"Fallback format {format_spec} successful: {expected_filename}"
                                    )
                                    return expected_filename

                            # Scan for any video files
                            import glob

                            video_extensions = [
                                "*.mp4",
                                "*.webm",
                                "*.avi",
                                "*.mov",
                                "*.wmv",
                                "*.flv",
                            ]
                            download_dir = (
                                Path(expected_filename).parent
                                if expected_filename
                                else output_path
                            )

                            for ext in video_extensions:
                                pattern = str(download_dir / ext)
                                found_files = glob.glob(pattern)
                                if found_files:
                                    for found_file in found_files:
                                        file_size = Path(found_file).stat().st_size
                                        if file_size > 0:
                                            logger.info(
                                                f"Found file with fallback format {format_spec}: {found_file}"
                                            )
                                            return found_file

                            return None

                    except Exception as e:
                        logger.debug(f"Fallback format {format_spec} failed: {e}")
                        return None

                result = await asyncio.to_thread(fallback_download)
                if result:
                    return result

            except Exception as e:
                logger.debug(f"Error with fallback format {format_spec}: {e}")
                continue

        logger.error("All fallback formats failed")
        return None

    async def download_video(self, url: str, progress_callback=None) -> Optional[str]:
        """
        Download video from URL using four-stage approach.

        Args:
            url: Video URL to download
            progress_callback: Optional callback function for progress updates

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

            # Use four-stage approach if source handler is available
            if self.source_handler:
                video_url, method = await self.source_handler.extract_video_url(
                    url, progress_callback
                )
                if video_url:
                    logger.info(
                        "Using extracted video URL via %s: %s", method, video_url
                    )
                    url = video_url
                else:
                    logger.warning("Four-stage extraction failed: %s", method)
                    return None

            # Download video
            result = await self._download_with_yt_dlp(url, download_dir)

            if result:
                logger.info(f"Video successfully downloaded: {result}")

                # Generate thumbnail for the downloaded video
                try:
                    thumbnail_path = await self.generate_thumbnail(result)
                    if thumbnail_path:
                        logger.info(f"Thumbnail generated: {thumbnail_path}")
                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail: {e}")

                return result
            else:
                logger.error("Video download failed")
                return None

        except Exception as e:
            logger.error(f"Error during video download: {e}")
            return None

    async def get_video_dimensions(self, video_path: str) -> Optional[tuple[int, int]]:
        """
        Get video dimensions (width, height) using ffprobe.

        Args:
            video_path: Path to video file

        Returns:
            Tuple of (width, height) or None if failed
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"Video file not found: {video_path}")
                return None

            # Use ffprobe to get video dimensions
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                str(video_path),
            ]

            logger.info(f"Getting video dimensions for {video_path.name}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                import json

                data = json.loads(stdout.decode())

                # Find video stream
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        width = stream.get("width")
                        height = stream.get("height")
                        if width and height:
                            logger.info(f"Video dimensions: {width}x{height}")
                            return (width, height)

                logger.error("No video stream found in file")
                return None
            else:
                logger.error(f"Failed to get video dimensions: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Error getting video dimensions: {e}")
            return None

    async def generate_thumbnail(
        self, video_path: str, output_path: Optional[str] = None, time_offset: int = 5
    ) -> Optional[str]:
        """
        Generate thumbnail from video at specified time offset.

        Args:
            video_path: Path to video file
            output_path: Path for thumbnail output (optional)
            time_offset: Time offset in seconds for thumbnail

        Returns:
            Path to generated thumbnail or None if failed
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"Video file not found: {video_path}")
                return None

            if output_path:
                thumbnail_path = Path(output_path)
            else:
                thumbnail_path = video_path.parent / f"{video_path.stem}_thumb.jpg"

            # Generate thumbnail using ffmpeg
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-ss",
                str(time_offset),  # Seek to time offset
                "-vframes",
                "1",  # Extract one frame
                "-q:v",
                "2",  # Quality setting (2 = high quality)
                "-vf",
                "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2",  # Scale and pad
                "-y",  # Overwrite output file
                str(thumbnail_path),
            ]

            logger.info(f"Generating thumbnail for {video_path.name} at {time_offset}s")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Thumbnail generated successfully: {thumbnail_path}")
                return str(thumbnail_path)
            else:
                logger.error(f"Failed to generate thumbnail: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
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
