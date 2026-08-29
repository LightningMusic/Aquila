"""
Project Aquila
=============

JSON Configuration Loader

Reads and writes Aquila configuration files authored as JSON.

YAML (``config.loaders.yaml_loader``) is the primary format for the
shipped ``configs/*.yaml`` files, but JSON is accepted anywhere
configuration can be supplied externally -- a deployment profile
handed to the CLI, a payload from the Deployment Controller API, or a
configuration exported for inspection -- since JSON requires no extra
dependency and is what most external tooling produces.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, cast

from common.exceptions.configuration import (
    ConfigurationFileNotFoundError,
    ConfigurationParseError,
    ConfigurationPermissionError,
    ConfigurationSaveError,
)


class JSONConfigLoader:
    """
    Loads and saves JSON-formatted Aquila configuration files.
    """

    def load(self, path: Path) -> dict[str, Any]:
        """
        Load and parse a JSON configuration file.

        An empty file is treated as an empty configuration (``{}``),
        matching ``YAMLConfigLoader.load``'s behavior.

        Raises:
            ConfigurationFileNotFoundError:
                If ``path`` does not exist.
            ConfigurationPermissionError:
                If ``path`` cannot be read due to file permissions.
            ConfigurationParseError:
                If ``path`` contains invalid JSON.
        """

        if not path.exists():
            raise ConfigurationFileNotFoundError(
                f"Configuration file not found: {path}"
            )

        try:
            text = path.read_text(encoding="utf-8")
        except PermissionError as exc:
            raise ConfigurationPermissionError(
                f"Unable to read configuration file (permission "
                f"denied): {path}"
            ) from exc
        except OSError as exc:
            raise ConfigurationParseError(
                f"Unable to read configuration file: {path} ({exc})"
            ) from exc

        if not text.strip():
            return {}

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigurationParseError(
                f"Invalid JSON in configuration file {path}: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ConfigurationParseError(
                f"Configuration file {path} must contain a JSON "
                f"object at the top level, got "
                f"{type(parsed).__name__}."
            )

        return cast(Dict[str, Any], parsed)

    def save(
        self,
        path: Path,
        data: Mapping[str, Any],
    ) -> None:
        """
        Serialize ``data`` to ``path`` as formatted JSON.

        The parent directory is created automatically if it does not
        already exist. Writes go through a temporary file in the same
        directory and are atomically renamed into place, so a failed
        or interrupted write never leaves a truncated configuration
        file behind.

        Raises:
            ConfigurationSaveError:
                If the file cannot be written.
        """

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            text = json.dumps(
                dict(data),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )

            temporary_path = path.with_suffix(path.suffix + ".tmp")
            temporary_path.write_text(text, encoding="utf-8")
            temporary_path.replace(path)
        except PermissionError as exc:
            raise ConfigurationSaveError(
                f"Unable to write configuration file (permission "
                f"denied): {path}"
            ) from exc
        except OSError as exc:
            raise ConfigurationSaveError(
                f"Unable to write configuration file {path}: {exc}"
            ) from exc


__all__ = ["JSONConfigLoader"]
