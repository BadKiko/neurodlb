"""
Local Telegram Bot API Server Manager.
Handles starting and stopping the local Telegram Bot API server.
"""

import asyncio
import logging
import subprocess
import sys
import platform
import os
from pathlib import Path
from typing import Optional
import urllib.request
import tarfile
import zipfile
import py7zr

from config import get_proxy_settings

logger = logging.getLogger(__name__)


class LocalAPIServer:
    """Manager for local Telegram Bot API server."""

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        port: int = 8081,
        max_file_size: int = 2 * 1024 * 1024 * 1024,  # 2GB
        max_connections: int = 100,
    ):
        """
        Initialize local API server manager.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            port: Port to run server on
            max_file_size: Maximum file size in bytes
            max_connections: Maximum number of connections
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.port = port
        self.max_file_size = max_file_size
        self.max_connections = max_connections
        self.process: Optional[subprocess.Popen] = None
        self.data_dir = Path(__file__).parent.parent / "telegram-bot-api-data"
        self.bin_dir = Path(__file__).parent.parent / "bin"
        self.bin_path = self.bin_dir / self._get_binary_name()

    def _get_binary_name(self) -> str:
        """Get the appropriate binary name for current platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "linux":
            if "x86_64" in machine or "amd64" in machine:
                return "telegram-bot-api"
            elif "aarch64" in machine or "arm64" in machine:
                return "telegram-bot-api"
        elif system == "darwin":  # macOS
            if "arm64" in machine:
                return "telegram-bot-api"
            else:
                return "telegram-bot-api"
        elif system == "windows":
            return "build/telegram-bot-api.exe"

        raise RuntimeError(f"Unsupported platform: {system} {machine}")

    def _download_binary(self) -> bool:
        """Download telegram-bot-api binary for current platform."""
        try:
            # Create bin directory
            self.bin_dir.mkdir(exist_ok=True)

            if self.bin_path.exists():
                logger.info("Telegram Bot API binary already exists")
                return True

            # Download URL based on platform
            system = platform.system().lower()
            machine = platform.machine().lower()

            if system == "linux":
                url = "https://github.com/jakbin/telegram-bot-api-binary/releases/download/2025-08-21glibc236/telegram-bot-api.zip"
            elif system == "windows":
                url = "https://github.com/Bezdarnost01/telegram-bot-api-windows/releases/download/windows-build/build.7z"
            else:
                logger.error(
                    f"Unsupported platform for auto-download: {system} {machine}"
                )
                return False

            logger.info(f"Downloading Telegram Bot API binary from {url}")

            # Download and extract
            logger.info("Downloading file...")
            temp_file_path = self.bin_dir / "temp_download"

            # Get proxy settings
            proxy_settings = get_proxy_settings()

            # Create proxy handler if proxy is configured
            proxy_handler = None
            if proxy_settings:
                proxy_url = proxy_settings.get("https") or proxy_settings.get("http")
                if proxy_url:
                    logger.info(f"Using proxy for download: {proxy_url[:20]}...")
                    proxy_handler = urllib.request.ProxyHandler(
                        {"http": proxy_url, "https": proxy_url}
                    )

            # Create opener with proxy if needed
            if proxy_handler:
                opener = urllib.request.build_opener(proxy_handler)
                urllib.request.install_opener(opener)

            # Download file with redirect handling
            with urllib.request.urlopen(url) as response:
                with open(temp_file_path, "wb") as f:
                    f.write(response.read())

            logger.info("Extracting archive...")

            if url.endswith(".tar.gz"):
                with tarfile.open(temp_file_path, mode="r:gz") as tar:
                    # Extract only the binary
                    for member in tar:
                        if member.name.endswith(
                            "telegram-bot-api"
                        ) or member.name.endswith("telegram-bot-api.exe"):
                            tar.extract(member, self.bin_dir)
                            extracted_path = self.bin_dir / member.name
                            extracted_path.rename(self.bin_path)
                            break
            elif url.endswith(".zip"):
                with zipfile.ZipFile(temp_file_path) as zf:
                    for file_info in zf.filelist:
                        if file_info.filename.endswith(
                            "telegram-bot-api"
                        ) or file_info.filename.endswith("telegram-bot-api.exe"):
                            zf.extract(file_info, self.bin_dir)
                            extracted_path = self.bin_dir / file_info.filename
                            extracted_path.rename(self.bin_path)
                            break
            elif url.endswith(".7z"):
                # Extract .7z file (contains full directory structure for Windows)
                with py7zr.SevenZipFile(temp_file_path, mode="r") as zf:
                    zf.extractall(self.bin_dir)

                # For Windows .7z, the binary is in build/telegram-bot-api.exe
                # All dependencies (DLLs) should remain in the build folder

            # Clean up temp file
            temp_file_path.unlink()

            # Make binary executable on Unix systems
            if system != "windows":
                self.bin_path.chmod(0o755)

            # Verify the binary was extracted successfully
            if not self.bin_path.exists():
                logger.error(f"Binary not found at {self.bin_path}")
                logger.error("Archive may not contain the expected binary")
                return False

            logger.info(f"Binary downloaded and extracted to {self.bin_path}")
            return True

        except Exception as e:
            logger.error(f"Error downloading binary: {e}")
            logger.warning("Binary download failed. Alternatives:")
            if system == "windows":
                logger.warning("Windows options:")
                logger.warning(
                    "1. Download from: https://github.com/tdlib/telegram-bot-api (build from source)"
                )
                logger.warning(
                    "2. Use Docker: docker run -p 8081:8081 aiogram/telegram-bot-api"
                )
                logger.warning(
                    "3. Use standard Telegram API (50MB limit) - comment out TELEGRAM_BOT_API_URL in .env"
                )
                logger.warning("Place telegram-bot-api.exe in the bin/ folder")
            else:
                logger.warning(
                    "Check: https://github.com/tdlib/telegram-bot-api/releases"
                )
                logger.warning(
                    "Or build from source: https://github.com/tdlib/telegram-bot-api"
                )
            return False

    async def start(self) -> bool:
        """
        Start the local Telegram Bot API server.

        Returns:
            True if server started successfully, False otherwise
        """
        try:
            # Check API credentials
            if not self.api_id or not self.api_hash:
                logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
                logger.error("Get them from: https://my.telegram.org/auth")
                return False

            logger.info(f"API ID: {self.api_id[:10]}...")
            logger.info(f"API Hash: {self.api_hash[:10]}...")

            # Download binary if needed
            if not self.bin_path.exists():
                logger.info(
                    f"Binary not found at {self.bin_path}, attempting to download..."
                )
                if not self._download_binary():
                    logger.error("Failed to download Telegram Bot API binary")
                    logger.error(
                        "Please download the binary manually and place it in the bin/ folder"
                    )
                    return False
            else:
                logger.info(f"Using existing binary: {self.bin_path}")

            # Create data directory if it doesn't exist
            self.data_dir.mkdir(exist_ok=True)

            # Prepare command
            cmd = [
                str(self.bin_path),
                "--api-id",
                self.api_id,
                "--api-hash",
                self.api_hash,
                "--local",  # Use local mode
                "--http-port",
                str(self.port),
                "--dir",
                str(self.data_dir),
                "--verbosity",
                "2",  # Info level logging
            ]

            # Add proxy settings if configured
            proxy_settings = get_proxy_settings()
            if proxy_settings:
                proxy_url = proxy_settings.get("https") or proxy_settings.get("http")
                if proxy_url:
                    logger.info(
                        f"Adding proxy to telegram-bot-api: {proxy_url[:20]}..."
                    )
                    # telegram-bot-api supports proxy in format http://host:port
                    # Authentication is handled via environment variables
                    try:
                        from urllib.parse import urlparse

                        parsed = urlparse(proxy_url)
                        if parsed.hostname and parsed.port:
                            # telegram-bot-api expects proxy in format http://host:port
                            proxy_for_api = f"http://{parsed.hostname}:{parsed.port}"
                            cmd.extend(["--proxy", proxy_for_api])
                            
                            logger.info(f"Using proxy: {parsed.hostname}:{parsed.port}")
                            
                            # Store auth info for environment variables
                            if parsed.username and parsed.password:
                                logger.info("Proxy authentication will be set via environment variables")
                        else:
                            logger.warning(f"Could not parse proxy URL: {proxy_url}")
                    except Exception as e:
                        logger.error(f"Error parsing proxy URL: {e}")
                        # Fallback: try to use the URL as-is
                        cmd.extend(["--proxy", proxy_url])

            logger.info(f"Starting local Telegram Bot API server on port {self.port}")
            logger.info("Server logs will be displayed in the console below:")

            # Start server in background
            logger.info(f"Running command: {' '.join(cmd)}")
            logger.info(f"Working directory: {self.bin_dir}")

            # Prepare environment with proxy settings
            env = os.environ.copy()
            if proxy_settings:
                proxy_url = proxy_settings.get("https") or proxy_settings.get("http")
                if proxy_url:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(proxy_url)
                        
                        # Set proxy environment variables for telegram-bot-api
                        env["HTTP_PROXY"] = proxy_url
                        env["HTTPS_PROXY"] = proxy_url
                        env["http_proxy"] = proxy_url
                        env["https_proxy"] = proxy_url
                        
                        # Set proxy authentication if provided
                        if parsed.username and parsed.password:
                            env["PROXY_USER"] = parsed.username
                            env["PROXY_PASSWORD"] = parsed.password
                            logger.info("Set proxy authentication environment variables")
                        
                        logger.info("Set proxy environment variables for telegram-bot-api")
                    except Exception as e:
                        logger.error(f"Error setting proxy environment variables: {e}")

            # For Windows, run from bin directory to find DLL dependencies
            # Don't capture stdout/stderr to allow server logs to show in console
            self.process = subprocess.Popen(
                cmd,
                stdout=None,  # Allow logs to go to console
                stderr=None,  # Allow logs to go to console
                text=True,
                cwd=self.bin_dir,  # Set working directory for DLL dependencies
                env=env,  # Pass environment with proxy settings
            )

            # Wait a moment for server to start
            await asyncio.sleep(3)

            # Check if process is still running
            if self.process.poll() is None:
                logger.info("✅ Local Telegram Bot API server started successfully")
                return True
            else:
                logger.error(
                    f"Failed to start server (exit code: {self.process.returncode})"
                )
                logger.error(f"Command: {' '.join(cmd)}")
                logger.error("Server logs should be visible above in the console")
                return False

        except Exception as e:
            logger.error(f"Error starting local API server: {e}")
            return False

    async def stop(self) -> None:
        """Stop the local Telegram Bot API server."""
        if self.process:
            logger.info("Stopping local Telegram Bot API server...")
            logger.info("You should see server shutdown logs in the console")
            self.process.terminate()

            try:
                # Wait up to 5 seconds for graceful shutdown
                await asyncio.wait_for(
                    asyncio.to_thread(self.process.wait), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Server didn't stop gracefully, force killing...")
                self.process.kill()

            self.process = None
            logger.info("✅ Local Telegram Bot API server stopped")

    async def is_running(self) -> bool:
        """Check if the server is running."""
        if not self.process:
            return False

        return self.process.poll() is None

    async def get_logs(self) -> tuple[str, str]:
        """Get stdout and stderr from the server process."""
        if not self.process:
            return "", ""

        # Since we're not capturing stdout/stderr, logs go directly to console
        logger.info("Server logs are displayed directly in the console")
        return "", ""
