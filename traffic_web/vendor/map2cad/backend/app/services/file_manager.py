"""Manage temporary files and downloadable output files."""

import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)

STALE_THRESHOLD_S = 3600  # 1 hour


class FileManager:
    """Manages temp directories and output files for exports."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.downloads_dir = os.path.join(base_dir, "downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)

    def create_temp_dir(self, request_id: str) -> str:
        """Create an isolated temp directory for an export request."""
        temp_dir = os.path.join(self.base_dir, "tmp", request_id)
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def cleanup_temp_dir(self, temp_dir: str) -> None:
        """Remove a temp directory and all its contents."""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temp dir: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up {temp_dir}: {e}")

    def move_to_downloads(self, filepath: str) -> str:
        """Move a file to the downloads directory.

        Returns the filename (not full path) for URL construction.
        """
        filename = os.path.basename(filepath)
        dest = os.path.join(self.downloads_dir, filename)
        shutil.move(filepath, dest)
        logger.debug(f"Moved to downloads: {dest}")
        return filename

    def get_download_path(self, filename: str) -> str | None:
        """Get the full path for a download file, or None if not found."""
        path = os.path.join(self.downloads_dir, filename)
        if os.path.exists(path):
            return path
        return None

    def cleanup_stale_files(self) -> int:
        """Remove files older than STALE_THRESHOLD_S from downloads.

        Returns count of removed files.
        """
        removed = 0
        now = time.time()

        if not os.path.exists(self.downloads_dir):
            return 0

        for filename in os.listdir(self.downloads_dir):
            filepath = os.path.join(self.downloads_dir, filename)
            if not os.path.isfile(filepath):
                continue
            age = now - os.path.getmtime(filepath)
            if age > STALE_THRESHOLD_S:
                try:
                    os.remove(filepath)
                    removed += 1
                except Exception as e:
                    logger.warning(f"Failed to remove stale file {filepath}: {e}")

        if removed > 0:
            logger.info(f"Cleaned up {removed} stale file(s)")

        return removed
