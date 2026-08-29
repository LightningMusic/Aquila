"""
Project Aquila
=============

YAML Configuration Loader

Reads and writes Aquila configuration files, which are authored as
YAML (see ``configs/*.yaml`` and Appendix D of the SRS). This is the
primary configuration format: every shipped configuration file
(``deployment.yaml``, ``network.yaml``, ``cluster.yaml``,
``logging.yaml``, ``benchmark.yaml``, ``controller.yaml``) is YAML,
chosen for being both technician-editable and comment-friendly.

Depends on PyYAML (``pip install pyyaml``); see requirements.txt.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, cast

from common.exceptions.configuration import (
    ConfigurationFileNotFoundError,
    ConfigurationParseError,
    ConfigurationPermissionError,
    ConfigurationSaveError,
)

try:
    import yaml

    _YamlParseError: type[Exception] = yaml.YAMLError
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None  # type: ignore[assignment]
    _YamlParseError = Exception


class YAMLConfigLoader:
    """
    Loads and saves YAML-formatted Aquila configuration files.
    """

    @staticmethod
    def _require_yaml() -> None:
        if yaml is None:
            raise ConfigurationParseError(
                "PyYAML is not installed. Install it with "
                "'pip install pyyaml' (see requirements.txt)."
            )

    def load(self, path: Path) -> dict[str, Any]:
        """
        Load and parse a YAML configuration file.

        An empty file is treated as an empty configuration (``{}``)
        rather than an error, since Aquila ships its configuration
        files empty by default until a technician or the Deployment
        Controller populates them.

        Raises:
            ConfigurationFileNotFoundError:
                If ``path`` does not exist.
            ConfigurationPermissionError:
                If ``path`` cannot be read due to file permissions.
            ConfigurationParseError:
                If ``path`` contains invalid YAML, or PyYAML is not
                installed.
        """

        self._require_yaml()

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
            assert yaml is not None
            parsed = yaml.safe_load(text)
        except _YamlParseError as exc:
            raise ConfigurationParseError(
                f"Invalid YAML in configuration file {path}: {exc}"
            ) from exc

        if parsed is None:
            return {}

        if not isinstance(parsed, dict):
            raise ConfigurationParseError(
                f"Configuration file {path} must contain a YAML "
                f"mapping at the top level, got "
                f"{type(parsed).__name__}."
            )

        return cast(Dict[str, Any], parsed)

    def save(
        self,
        path: Path,
        data: Mapping[str, Any],
    ) -> None:
        """
        Serialize ``data`` to ``path`` as YAML.

        The parent directory is created automatically if it does not
        already exist. Writes go through a temporary file in the same
        directory and are atomically renamed into place, so a failed
        or interrupted write never leaves a truncated configuration
        file behind.

        Raises:
            ConfigurationSaveError:
                If the file cannot be written.
        """

        self._require_yaml()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            assert yaml is not None
            text = yaml.safe_dump(
                dict(data),
                sort_keys=True,
                default_flow_style=False,
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


__all__ = ["YAMLConfigLoader"]
