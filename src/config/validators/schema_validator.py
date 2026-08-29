"""
Project Aquila
=============

Schema Validator

Shared, reusable validation primitives used by every configuration
schema module under ``config.schemas``.

Each ``config.schemas.*`` module defines the typed shape of one
configuration file (``deployment.yaml``, ``network.yaml``, and so on)
and is responsible for turning a loosely-typed mapping -- as produced
by ``config.loaders.yaml_loader`` or ``config.loaders.json_loader``
from an on-disk file a technician or the Deployment Controller may
have edited by hand -- into a fully validated, strongly typed
dataclass. This module centralizes the primitive checks every schema
needs (required keys, coerced scalar types, bounded ranges, allowed
choices) so that validation failures are reported consistently and so
schema modules stay focused on their own field layout rather than
re-implementing type coercion.

Every failure raised here is a subclass of
``common.exceptions.configuration.ConfigurationError``, matching the
project-wide exception hierarchy already used by the rest of Aquila.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, TypeVar, cast

from common.exceptions.configuration import (
    ConfigurationKeyError,
    ConfigurationTypeError,
    ConfigurationValueError,
)

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Mapping shape
# ---------------------------------------------------------------------------


def require_mapping(
    data: Any,
    *,
    section: str,
) -> Mapping[str, Any]:
    """
    Confirm ``data`` is a mapping and return it typed as such.

    Raises:
        ConfigurationTypeError:
            If ``data`` is not a mapping.
    """

    if not isinstance(data, Mapping):
        raise ConfigurationTypeError(
            f"'{section}' must be a mapping, got "
            f"{type(data).__name__}."
        )

    return cast(Mapping[str, Any], data)


def require_keys(
    data: Mapping[str, Any],
    keys: Iterable[str],
    *,
    section: str,
) -> None:
    """
    Confirm every key in ``keys`` is present in ``data``.

    Raises:
        ConfigurationKeyError:
            If any required key is missing.
    """

    missing = sorted(key for key in keys if key not in data)

    if missing:
        raise ConfigurationKeyError(
            f"'{section}' is missing required key(s): "
            f"{', '.join(missing)}."
        )


def optional(
    data: Mapping[str, Any],
    key: str,
    default: object,
) -> Any:
    """
    Return ``data[key]`` when present and not ``None``, else ``default``.

    The return type is deliberately ``Any``, not the type of
    ``default``: the value found in ``data`` (when present) comes
    from a loosely-typed configuration mapping and is not known to
    match ``default``'s type, so a generic parameter here would only
    assert a guarantee this function cannot actually make. Callers
    that need a specific type should follow this with one of the
    ``coerce_*`` functions below.
    """

    value = data.get(key)

    return default if value is None else value


# ---------------------------------------------------------------------------
# Scalar coercion
# ---------------------------------------------------------------------------


def coerce_bool(
    value: Any,
    *,
    field_name: str,
    default: bool = False,
) -> bool:
    """
    Coerce a configuration value to ``bool``.

    Accepts native booleans, and the common YAML/JSON textual and
    numeric spellings of true/false, since configuration files are
    frequently hand-edited by technicians.

    Raises:
        ConfigurationTypeError:
            If the value cannot be interpreted as a boolean.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and not isinstance(value, bool):
        if value in (0, 1):
            return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "yes", "on", "1", "enabled"):
            return True
        if normalized in ("false", "no", "off", "0", "disabled", ""):
            return False

    raise ConfigurationTypeError(
        f"'{field_name}' must be a boolean, got {value!r}."
    )


def coerce_int(
    value: Any,
    *,
    field_name: str,
    default: int | None = None,
) -> int:
    """
    Coerce a configuration value to ``int``.

    Raises:
        ConfigurationTypeError:
            If the value cannot be interpreted as an integer.
        ConfigurationKeyError:
            If the value is missing and no default was supplied.
    """

    if value is None:
        if default is None:
            raise ConfigurationKeyError(
                f"'{field_name}' is required and has no default."
            )
        return default

    if isinstance(value, bool):
        raise ConfigurationTypeError(
            f"'{field_name}' must be an integer, got a boolean."
        )

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ConfigurationTypeError(
                f"'{field_name}' must be an integer, got {value!r}."
            ) from exc

    raise ConfigurationTypeError(
        f"'{field_name}' must be an integer, got {value!r}."
    )


def coerce_float(
    value: Any,
    *,
    field_name: str,
    default: float | None = None,
) -> float:
    """
    Coerce a configuration value to ``float``.

    Raises:
        ConfigurationTypeError:
            If the value cannot be interpreted as a number.
        ConfigurationKeyError:
            If the value is missing and no default was supplied.
    """

    if value is None:
        if default is None:
            raise ConfigurationKeyError(
                f"'{field_name}' is required and has no default."
            )
        return default

    if isinstance(value, bool):
        raise ConfigurationTypeError(
            f"'{field_name}' must be a number, got a boolean."
        )

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise ConfigurationTypeError(
                f"'{field_name}' must be a number, got {value!r}."
            ) from exc

    raise ConfigurationTypeError(
        f"'{field_name}' must be a number, got {value!r}."
    )


def coerce_str(
    value: Any,
    *,
    field_name: str,
    default: str | None = None,
    allow_empty: bool = True,
) -> str:
    """
    Coerce a configuration value to a stripped ``str``.

    Raises:
        ConfigurationTypeError:
            If the value cannot be interpreted as text.
        ConfigurationKeyError:
            If the value is missing and no default was supplied.
        ConfigurationValueError:
            If the resulting text is empty and ``allow_empty`` is False.
    """

    if value is None:
        if default is None:
            raise ConfigurationKeyError(
                f"'{field_name}' is required and has no default."
            )
        value = default

    if not isinstance(value, str):
        raise ConfigurationTypeError(
            f"'{field_name}' must be a string, got {type(value).__name__}."
        )

    text = value.strip()

    if not text and not allow_empty:
        raise ConfigurationValueError(
            f"'{field_name}' must not be empty."
        )

    return text


def coerce_str_list(
    value: Any,
    *,
    field_name: str,
) -> list[str]:
    """
    Coerce a configuration value to a list of strings.

    ``None`` is treated as an empty list, since optional list-valued
    settings are commonly omitted entirely from a hand-edited file.

    Raises:
        ConfigurationTypeError:
            If the value is present but not a list of strings.
    """

    if value is None:
        return []

    if not isinstance(value, (list, tuple)):
        raise ConfigurationTypeError(
            f"'{field_name}' must be a list, got {type(value).__name__}."
        )

    items: list[str] = []
    typed_value = cast("list[Any] | tuple[Any, ...]", value)
    for index, item in enumerate(typed_value):
        if not isinstance(item, str):
            raise ConfigurationTypeError(
                f"'{field_name}[{index}]' must be a string, "
                f"got {type(item).__name__}."
            )
        items.append(item.strip())

    return items


# ---------------------------------------------------------------------------
# Range and choice validation
# ---------------------------------------------------------------------------


def validate_range(
    value: int | float,
    *,
    field_name: str,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
) -> None:
    """
    Confirm ``value`` falls within ``[minimum, maximum]``.

    Either bound may be omitted to leave that side unconstrained.

    Raises:
        ConfigurationValueError:
            If the value falls outside the allowed range.
    """

    if minimum is not None and value < minimum:
        raise ConfigurationValueError(
            f"'{field_name}' must be >= {minimum}, got {value}."
        )

    if maximum is not None and value > maximum:
        raise ConfigurationValueError(
            f"'{field_name}' must be <= {maximum}, got {value}."
        )


def validate_choice(
    value: _T,
    choices: Sequence[_T],
    *,
    field_name: str,
) -> _T:
    """
    Confirm ``value`` is one of ``choices``.

    Raises:
        ConfigurationValueError:
            If the value is not among the allowed choices.
    """

    if value not in choices:
        allowed = ", ".join(repr(choice) for choice in choices)
        raise ConfigurationValueError(
            f"'{field_name}' must be one of [{allowed}], got {value!r}."
        )

    return value


__all__ = [
    "coerce_bool",
    "coerce_float",
    "coerce_int",
    "coerce_str",
    "coerce_str_list",
    "optional",
    "require_keys",
    "require_mapping",
    "validate_choice",
    "validate_range",
]
