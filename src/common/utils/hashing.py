"""
Project Orion
=============

Hashing Utilities

Provides standardized hashing functions used throughout
Project Orion.

Supported Uses
--------------
- File integrity verification
- Deployment verification
- Recovery validation
- USB verification
- Duplicate file detection

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB


# ----------------------------------------------------------------------
# Internal Helpers
# ----------------------------------------------------------------------

def _hash_stream(
    algorithm: hashlib._Hash,
    path: Path,
    chunk_size: int,
) -> str:
    """
    Compute a hash for a file.

    Parameters
    ----------
    algorithm:
        Hashlib hashing object.

    path:
        File to hash.

    chunk_size:
        Number of bytes read per iteration.
    """

    with path.open("rb") as file:

        while chunk := file.read(chunk_size):
            algorithm.update(chunk)

    return algorithm.hexdigest()


# ----------------------------------------------------------------------
# Text Hashes
# ----------------------------------------------------------------------

def md5(
    text: str,
) -> str:
    """
    Compute the MD5 hash of a string.
    """

    return hashlib.md5(
        text.encode("utf-8")
    ).hexdigest()


def sha1(
    text: str,
) -> str:
    """
    Compute the SHA-1 hash of a string.
    """

    return hashlib.sha1(
        text.encode("utf-8")
    ).hexdigest()


def sha256(
    text: str,
) -> str:
    """
    Compute the SHA-256 hash of a string.
    """

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def sha512(
    text: str,
) -> str:
    """
    Compute the SHA-512 hash of a string.
    """

    return hashlib.sha512(
        text.encode("utf-8")
    ).hexdigest()


# ----------------------------------------------------------------------
# File Hashes
# ----------------------------------------------------------------------

def md5_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Compute the MD5 hash of a file.
    """

    return _hash_stream(
        hashlib.md5(),
        path,
        chunk_size,
    )


def sha1_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Compute the SHA-1 hash of a file.
    """

    return _hash_stream(
        hashlib.sha1(),
        path,
        chunk_size,
    )


def sha256_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Compute the SHA-256 hash of a file.
    """

    return _hash_stream(
        hashlib.sha256(),
        path,
        chunk_size,
    )


def sha512_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Compute the SHA-512 hash of a file.
    """

    return _hash_stream(
        hashlib.sha512(),
        path,
        chunk_size,
    )


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------

def verify_hash(
    value: str,
    expected: str,
) -> bool:
    """
    Compare two hashes.

    Comparison is case-insensitive.
    """

    return value.lower() == expected.lower()


def verify_file(
    path: Path,
    expected_hash: str,
    *,
    algorithm: str = "sha256",
) -> bool:
    """
    Verify a file hash.
    """

    algorithm = algorithm.lower()

    if algorithm == "md5":
        actual = md5_file(path)

    elif algorithm == "sha1":
        actual = sha1_file(path)

    elif algorithm == "sha256":
        actual = sha256_file(path)

    elif algorithm == "sha512":
        actual = sha512_file(path)

    else:
        raise ValueError(
            f"Unsupported hashing algorithm: {algorithm}"
        )

    return verify_hash(
        actual,
        expected_hash,
    )


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "md5",
    "sha1",
    "sha256",
    "sha512",
    "md5_file",
    "sha1_file",
    "sha256_file",
    "sha512_file",
    "verify_hash",
    "verify_file",
]