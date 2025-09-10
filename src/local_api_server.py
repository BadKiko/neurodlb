"""
Local Telegram Bot API Server Manager.
Handles starting and stopping the local Telegram Bot API server.
"""

import asyncio
import logging
import subprocess
import sys
import platform
from pathlib import Path
from typing import Optional
import urllib.request
import tarfile
import zipfile

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
            return "telegram-bot-api.exe"

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
                if "x86_64" in machine or "amd64" in machine:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-linux-x86_64.tar.gz"
                else:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-linux-arm64.tar.gz"
            elif system == "darwin":
                if "arm64" in machine:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-darwin-arm64.tar.gz"
                else:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-darwin-x86_64.tar.gz"
            elif system == "windows":
                if "amd64" in machine or "x86_64" in machine:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-win64.zip"
                else:
                    url = "https://github.com/tdlib/telegram-bot-api/releases/download/v7.0/telegram-bot-api-7.0-win32.zip"
            else:
                logger.error(
                    f"Unsupported platform for auto-download: {system} {machine}"
                )
                return False

            logger.info(f"Downloading Telegram Bot API binary from {url}")

            # Download and extract
            with urllib.request.urlopen(url) as response:
                if url.endswith(".tar.gz"):
                    with tarfile.open(fileobj=response, mode="r|gz") as tar:
                        # Extract only the binary
                        for member in tar:
                            if member.name.endswith(
                                "telegram-bot-api"
                            ) or member.name.endswith("telegram-bot-api.exe"):
                                member.name = self.bin_path.name
                                tar.extract(member, self.bin_dir)
                                break
                elif url.endswith(".zip"):
                    with zipfile.ZipFile(response) as zf:
                        for file_info in zf.filelist:
                            if file_info.filename.endswith(
                                "telegram-bot-api"
                            ) or file_info.filename.endswith("telegram-bot-api.exe"):
                                zf.extract(file_info, self.bin_dir)
                                extracted_path = self.bin_dir / file_info.filename
                                extracted_path.rename(self.bin_path)
                                break

            # Make binary executable on Unix systems
            if system != "windows":
                self.bin_path.chmod(0o755)

            # Verify the binary was extracted successfully
            if not self.bin_path.exists():
                logger.error("Failed to extract binary from archive")
                return False

            logger.info(f"Binary downloaded and extracted to {self.bin_path}")
            return True

        except Exception as e:
            logger.error(f"Error downloading binary: {e}")
            return False

    async def start(self) -> bool:
        """
        Start the local Telegram Bot API server.

        Returns:
            True if server started successfully, False otherwise
        """
        try:
            # Download binary if needed
            if not self.bin_path.exists():
                if not self._download_binary():
                    logger.error("Failed to download Telegram Bot API binary")
                    return False

            # Create data directory if it doesn't exist
            self.data_dir.mkdir(exist_ok=True)

            # Prepare command
            cmd = [
                str(self.bin_path),
                "--api-id",
                self.api_id,
                "--api-hash",
                self.api_hash,
                "--http-port",
                str(self.port),
                "--dir",
                str(self.data_dir),
                "--max-file-size",
                str(self.max_file_size),
                "--max-connections",
                str(self.max_connections),
                "--verbosity",
                "2",  # Info level logging
            ]

            logger.info(f"Starting local Telegram Bot API server on port {self.port}")

            # Start server in background
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            # Wait a moment for server to start
            await asyncio.sleep(3)

            # Check if process is still running
            if self.process.poll() is None:
                logger.info("✅ Local Telegram Bot API server started successfully")
                return True
            else:
                stdout, stderr = self.process.communicate()
                logger.error(
                    f"Failed to start server. stdout: {stdout}, stderr: {stderr}"
                )
                return False

        except Exception as e:
            logger.error(f"Error starting local API server: {e}")
            return False

    async def stop(self) -> None:
        """Stop the local Telegram Bot API server."""
        if self.process:
            logger.info("Stopping local Telegram Bot API server...")
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

        try:
            # Read available output without blocking
            if self.process.stdout:
                stdout = await asyncio.to_thread(self.process.stdout.read)
            else:
                stdout = ""

            if self.process.stderr:
                stderr = await asyncio.to_thread(self.process.stderr.read)
            else:
                stderr = ""

            return stdout, stderr
        except Exception as e:
            logger.error(f"Error reading server logs: {e}")
            return "", ""
