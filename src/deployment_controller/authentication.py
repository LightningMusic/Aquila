"""
Project Aquila
=============

Deployment Controller Authentication

Implements REQ-CTRL-001 ("authenticate all deployment requests"),
REQ-CTRL-002 ("uniquely identify every node requesting deployment"),
REQ-SEC-002 ("authenticate every node prior to accepting deployment
requests"), and REQ-SEC-006 ("authentication failures shall be
logged").

Architecture: resolving the node identifier / credential gap
--------------------------------------------------------------
``bootstrap.controller_client.DeploymentControllerClient`` (already
delivered) sends a single shared bearer token on every request --
``authenticate()`` sets it once on the underlying ``requests.Session``
and every subsequent call (configuration retrieval, completion
report, inventory/benchmark submission) reuses that same session, so
the Controller never receives a second, per-node credential to
distinguish callers by. This module therefore authenticates *every*
protected request the same way a Kubernetes bootstrap token or a
join-token based cluster enrollment scheme would: possession of one
of the Controller's configured enrollment secrets
(``ControllerServerConfig.enrollment_token_env_var``) proves "this
request comes from an Aquila deployment", while the caller-supplied
``node_identifier`` -- a UUID Bootstrap generates and persists locally
on first run -- distinguishes *which* node is calling. This is
consistent with GP-009 ("Installer media shall not contain permanently
assigned deployment identities"): the shared secret is fleet-wide
policy baked into deployment media, not a per-node identity, while
each node's identifier is generated dynamically per-node, never baked
into the media itself. REQ-CTRL-003's "the Deployment Controller shall
assign a unique Aquila Node Identifier" is satisfied by the Controller
being the authoritative registry that accepts (or rejects, as a
duplicate) that identifier -- not by the Controller originating the
random value -- exactly parallel to how a DHCP server "assigns" an
address a client proposes via DHCPDISCOVER, or how Kubernetes "assigns"
identity to a node presenting a bootstrap token. This resolution is
flagged in ``claude/aquila-project-status.md`` as the answer to the
architectural gap noted when ``bootstrap/controller_client.py`` was
built, before this subsystem existed to reconcile it against.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from common.constants.logging import INVENTORY_LOGGER
from common.events.types.controller import (
    NodeAuthenticatedEvent,
    NodeAuthenticationFailedEvent,
)

logger = logging.getLogger(INVENTORY_LOGGER)

#: Deliberately permissive of both a UUID4 (Bootstrap's own default
#: choice) and any other reasonably-shaped opaque identifier, while
#: still rejecting anything that could not safely become a SQLite
#: primary key, a filesystem-adjacent hostname component, or a log
#: line -- REQ-SEC-002's "authenticate" is a request-origin check, not
#: a UUID-format mandate the SRS never actually states.
_NODE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a shared secret, for at-rest comparison."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """Parse an ``Authorization: Bearer <token>`` header value."""

    if not authorization_header:
        return None

    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    return token or None


def is_valid_node_identifier(node_identifier: str) -> bool:
    return bool(_NODE_IDENTIFIER_PATTERN.match(node_identifier))


@dataclass(slots=True, frozen=True)
class AuthenticationResult:
    """The outcome of one REQ-CTRL-001/REQ-SEC-002 authentication check."""

    authenticated: bool
    node_identifier: str
    detail: str = ""


class TokenValidator:
    """
    Validates a candidate bearer token against one or more configured
    enrollment secrets, stored only as SHA-256 hashes (REQ-SEC-009,
    "sensitive credentials shall be stored securely") and compared in
    constant time (``hmac.compare_digest``) to avoid a timing side
    channel on the comparison itself.

    REQ-SEC-016: ``NodeAuthenticator`` depends on this only through
    its narrow ``has_configured_tokens``/``validate()`` surface,
    injected at construction rather than hardcoded -- a future
    authentication provider (mTLS client certificates, an external
    identity service, ...) can be introduced as a second class behind
    that same surface and swapped in without changing
    ``NodeAuthenticator`` or anything upstream of it.
    """

    def __init__(self, valid_tokens: tuple[str, ...]) -> None:
        self._valid_hashes = tuple(hash_token(token) for token in valid_tokens if token)

    @property
    def has_configured_tokens(self) -> bool:
        return bool(self._valid_hashes)

    def validate(self, candidate: Optional[str]) -> bool:
        if not candidate or not self._valid_hashes:
            return False

        candidate_hash = hash_token(candidate)
        return any(
            hmac.compare_digest(candidate_hash, valid_hash)
            for valid_hash in self._valid_hashes
        )


#: Callable returning ``True`` when a node identifier is barred from
#: authenticating (for example, a node the Inventory System has marked
#: RETIRED or that authorization has DENIED). Injected rather than
#: imported directly so this module has no compile-time dependency on
#: ``inventory``/``deployment_controller.authorization`` -- only
#: ``deployment_controller.controller`` needs to know about all three.
RevocationCheck = Callable[[str], bool]


class NodeAuthenticator:
    """Authenticates deployment requests (REQ-CTRL-001, REQ-SEC-002)."""

    def __init__(
        self,
        *,
        token_validator: TokenValidator,
        is_revoked: Optional[RevocationCheck] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._token_validator = token_validator
        self._is_revoked = is_revoked
        self._event_bus = event_bus

    def authenticate(
        self, node_identifier: str, authorization_header: Optional[str]
    ) -> AuthenticationResult:
        node_identifier = (node_identifier or "").strip()

        if not node_identifier or not is_valid_node_identifier(node_identifier):
            return self._reject(
                node_identifier or "<empty>",
                "A valid node_identifier was not supplied.",
            )

        token = extract_bearer_token(authorization_header)
        if not self._token_validator.validate(token):
            return self._reject(
                node_identifier,
                "The supplied Authorization bearer token is missing or invalid.",
            )

        if self._is_revoked is not None and self._is_revoked(node_identifier):
            return self._reject(
                node_identifier,
                f"Node '{node_identifier}' has been denied or retired.",
            )

        self._publish(lambda: NodeAuthenticatedEvent(node_identifier))
        logger.info("Node '%s' authenticated successfully.", node_identifier)

        return AuthenticationResult(
            authenticated=True,
            node_identifier=node_identifier,
            detail="Authenticated.",
        )

    def authenticate_operator(
        self, authorization_header: Optional[str]
    ) -> bool:
        """
        Validate a bearer token for an operator-facing read request
        that is not made on behalf of any single node -- REQ-INV-010
        inventory search and benchmark-history lookups, which the
        Technician Console calls for itself rather than a deployment
        target. There is no separate operator credential system
        (SRS-silent on one, and REQ-SEC-003's "every node shall
        possess a unique identity" is about deployment nodes, not the
        Console): possession of one of the same configured enrollment
        secrets is treated as sufficient, exactly as it is for every
        node-scoped call, without the ``node_identifier``-shaped
        validation or revocation check those calls also require.
        """

        token = extract_bearer_token(authorization_header)
        return self._token_validator.validate(token)

    def _reject(self, node_identifier: str, detail: str) -> AuthenticationResult:
        logger.warning(
            "Authentication rejected for node '%s': %s", node_identifier, detail
        )
        self._publish(
            lambda: NodeAuthenticationFailedEvent(node_identifier, detail)
        )
        return AuthenticationResult(
            authenticated=False, node_identifier=node_identifier, detail=detail
        )

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish authentication event.", exc_info=True)


__all__ = [
    "AuthenticationResult",
    "NodeAuthenticator",
    "RevocationCheck",
    "TokenValidator",
    "extract_bearer_token",
    "hash_token",
    "is_valid_node_identifier",
]
