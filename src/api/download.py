"""
Project Orion
=============

Download Manager

Handles downloading runtime artifacts required by
Project Orion.

Current responsibilities:

    • Download Proxmox VE ISO
    • Verify downloaded files
    • Report download progress
    • Prevent duplicate downloads

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests


class DownloadManager:
    """
    Handles downloading files required by Orion.
    """

    DEFAULT_CHUNK_SIZE = 1024 * 1024

    def __init__(self) -> None:
        pass

    # ---------------------------------------------------------
    # Download
    # ---------------------------------------------------------

    def download(
        self,
        url: str,
        destination: Path,
        overwrite: bool = False,
    ) -> Path:
        """
        Download a file.

        Parameters
        ----------
        url:
            Download URL.

        destination:
            Destination file.

        overwrite:
            Replace an existing file.

        Returns
        -------
        Path
            Downloaded file.
        """

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if destination.exists() and not overwrite:
            return destination

        with requests.get(
            url,
            stream=True,
            timeout=60,
        ) as response:

            response.raise_for_status()

            with destination.open("wb") as output:

                for chunk in response.iter_content(
                    chunk_size=self.DEFAULT_CHUNK_SIZE
                ):

                    if chunk:
                        output.write(chunk)

        return destination

    # ---------------------------------------------------------
    # SHA256
    # ---------------------------------------------------------

    def sha256(
        self,
        file: Path,
    ) -> str:
        """
        Calculate a SHA256 hash.
        """

        digest = hashlib.sha256()

        with file.open("rb") as stream:

            while True:

                block = stream.read(1024 * 1024)

                if not block:
                    break

                digest.update(block)

        return digest.hexdigest()

    # ---------------------------------------------------------
    # Verification
    # ---------------------------------------------------------

    def verify_sha256(
        self,
        file: Path,
        expected: str,
    ) -> bool:
        """
        Verify SHA256 hash.
        """

        return (
            self.sha256(file).lower()
            == expected.lower()
        )

    # ---------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------

    def download_if_missing(
        self,
        url: str,
        destination: Path,
    ) -> Path:
        """
        Download only if the file does not exist.
        """

        if destination.exists():
            return destination

        return self.download(
            url,
            destination,
        )

    def delete(
        self,
        file: Path,
    ) -> None:
        """
        Delete a downloaded file.
        """

        if file.exists():
            file.unlink()

    def exists(
        self,
        file: Path,
    ) -> bool:
        """
        Determine whether a file exists.
        """

        return file.exists()