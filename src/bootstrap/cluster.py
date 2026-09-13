"""
Project Aquila
=============

Proxmox Cluster Enrollment

Implements REQ-BOOT-012 ("automatically enroll the node into the
designated Proxmox cluster") and REQ-BOOT-013 ("verify successful
cluster enrollment").

Research basis (this session, primary sources: Proxmox's own
``pvecm`` documentation, and a Proxmox staff reply on the Proxmox
support forum): a genuine capability gap, not an Aquila oversight --

* ``pvecm create CLUSTERNAME`` bootstraps a brand-new cluster.
* ``pvecm add IP-ADDRESS-CLUSTER [--fingerprint FP]`` joins an
  existing one, but **requires the target node's root@pam password**,
  and Proxmox's own documentation and staff confirm there is no
  supported unattended/API-token/stdin-documented alternative: a
  Proxmox staff member stated cluster joining "requires the root
  password since it does quite far-reaching modification on both
  ends," and the Proxmox VE API marks the join operation itself
  "Root only."

This module supplies the password the same well-established way any
script answers an interactive CLI prompt it doesn't control --
piping it to the subprocess's stdin -- rather than inventing an
undocumented flag. This is meaningfully different from, and safer
than, ``preparation.sanitizer``'s ATA/NVMe Secure Erase decision:
there the risk was a wrong low-level IOCTL on a *destructive* disk
command with no way to verify beforehand. Here, a malformed or
rejected ``pvecm add`` attempt is a safe, independently-verifiable,
retryable no-op -- it does not touch storage or destroy data -- so
REQ-BOOT-013's independent post-join verification (via ``pvecm
nodes``, never trusting the join command's exit code alone) is what
actually confirms success, exactly mirroring
``preparation.verifier``'s "never trust the mutating call's own
success signal" discipline.

**Known limitation**: without ``ClusterConfig.join_fingerprint`` set,
``pvecm add`` may also prompt to accept the target's certificate
fingerprint interactively; this module pipes only the password, not a
fingerprint acceptance, and instead bounds the whole attempt with a
timeout so an unanswered fingerprint prompt fails fast (as a timeout,
reported honestly) rather than hanging the deployment indefinitely.
Supplying ``join_fingerprint`` avoids this entirely.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from common.constants.logging import BOOTSTRAP_LOGGER
from common.exceptions.deployment import (
    DeploymentClusterError,
    DeploymentVerificationError,
)
from config.schemas.cluster_schema import ClusterConfig

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: How long a `pvecm add`/`pvecm create` attempt may run before this
#: module gives up and reports a timeout rather than hanging forever
#: on an unanswered interactive prompt (see this module's docstring).
_JOIN_TIMEOUT_SECONDS = 120

#: REQ-BOOT-013's post-join verification: how many times to re-check
#: `pvecm nodes` for this node's own hostname, and how long to wait
#: between attempts -- corosync membership can take a few seconds to
#: propagate after `pvecm add` returns.
_VERIFY_RETRY_COUNT = 6
_VERIFY_RETRY_DELAY_SECONDS = 5.0


class CommandRunner(Protocol):
    """Runs a command (optionally with piped stdin) and returns its
    completed process, or raises ``subprocess.TimeoutExpired``."""

    def __call__(
        self,
        args: list[str],
        *,
        input_text: str | None,
        timeout: float | None,
    ) -> subprocess.CompletedProcess[str]: ...


def _default_command_runner(
    args: list[str],
    *,
    input_text: str | None,
    timeout: float | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
        timeout=timeout,
    )


@dataclass(slots=True, frozen=True)
class ClusterJoinResult:
    """Outcome of REQ-BOOT-012's cluster enrollment attempt."""

    created_new_cluster: bool
    command_succeeded: bool
    detail: str


@dataclass(slots=True, frozen=True)
class ClusterVerificationResult:
    """Outcome of REQ-BOOT-013's post-join verification."""

    verified: bool
    node_hostname: str
    detail: str


class ClusterEnrollment:
    """
    Joins (or, for the first node, creates) the designated Proxmox
    cluster, then independently verifies membership.
    """

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._run = command_runner or _default_command_runner
        self._sleep = sleep or time.sleep

    def join(
        self, cluster_config: ClusterConfig, join_secret: str
    ) -> ClusterJoinResult:
        """
        Join ``cluster_config``'s cluster (or create it, if this node
        is configured as ``cluster_master``).

        Raises:
            DeploymentClusterError: If the join/create command fails
                or times out.
        """

        if cluster_config.node_role == "cluster_master":
            return self._create(cluster_config)
        return self._join_existing(cluster_config, join_secret)

    def _create(
        self, cluster_config: ClusterConfig
    ) -> ClusterJoinResult:
        if not cluster_config.cluster_name:
            raise DeploymentClusterError(
                "'cluster_name' is required to create a new cluster "
                "(node_role='cluster_master')."
            )

        args = ["pvecm", "create", cluster_config.cluster_name]

        try:
            result = self._run(
                args, input_text=None, timeout=_JOIN_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as exc:
            raise DeploymentClusterError(
                f"'pvecm create {cluster_config.cluster_name}' timed "
                f"out after {_JOIN_TIMEOUT_SECONDS}s."
            ) from exc

        if result.returncode != 0:
            raise DeploymentClusterError(
                f"'pvecm create {cluster_config.cluster_name}' "
                f"failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        detail = f"Created new cluster '{cluster_config.cluster_name}'."
        logger.info(detail)
        return ClusterJoinResult(
            created_new_cluster=True,
            command_succeeded=True,
            detail=detail,
        )

    def _join_existing(
        self, cluster_config: ClusterConfig, join_secret: str
    ) -> ClusterJoinResult:
        if not cluster_config.primary_node_host:
            raise DeploymentClusterError(
                "'primary_node_host' is required to join an existing "
                "cluster."
            )

        if not join_secret:
            raise DeploymentClusterError(
                "No cluster join secret was resolved from "
                f"'{cluster_config.join_token_env_var}' -- refusing "
                "to attempt an unauthenticated cluster join."
            )

        args = ["pvecm", "add", cluster_config.primary_node_host]
        if cluster_config.join_fingerprint:
            args += ["--fingerprint", cluster_config.join_fingerprint]

        try:
            result = self._run(
                args,
                input_text=f"{join_secret}\n",
                timeout=_JOIN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise DeploymentClusterError(
                f"'pvecm add {cluster_config.primary_node_host}' "
                f"timed out after {_JOIN_TIMEOUT_SECONDS}s -- if "
                "'join_fingerprint' isn't configured, pvecm may be "
                "waiting on an unanswered fingerprint-acceptance "
                "prompt (see bootstrap.cluster's module docstring)."
            ) from exc

        if result.returncode != 0:
            raise DeploymentClusterError(
                f"'pvecm add {cluster_config.primary_node_host}' "
                f"failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        detail = (
            f"Joined cluster via {cluster_config.primary_node_host}."
        )
        logger.info(detail)
        return ClusterJoinResult(
            created_new_cluster=False,
            command_succeeded=True,
            detail=detail,
        )

    def verify(self, node_hostname: str) -> ClusterVerificationResult:
        """
        Independently confirm ``node_hostname`` appears in the local
        cluster's membership list (REQ-BOOT-013), retrying with delay
        since corosync membership can lag behind ``pvecm add``
        returning.

        Never trusts :meth:`join`'s exit code alone.
        """

        attempts = _VERIFY_RETRY_COUNT + 1
        last_detail = ""

        for attempt in range(1, attempts + 1):
            try:
                result = self._run(
                    ["pvecm", "nodes"],
                    input_text=None,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                last_detail = "'pvecm nodes' timed out."
                result = None

            if result is not None and result.returncode == 0:
                if node_hostname.lower() in result.stdout.lower():
                    detail = (
                        f"'{node_hostname}' confirmed present in "
                        f"'pvecm nodes' output (attempt {attempt})."
                    )
                    logger.info(detail)
                    return ClusterVerificationResult(
                        verified=True,
                        node_hostname=node_hostname,
                        detail=detail,
                    )
                last_detail = (
                    f"'{node_hostname}' not yet present in 'pvecm "
                    f"nodes' output (attempt {attempt}/{attempts})."
                )
            elif result is not None:
                last_detail = (
                    f"'pvecm nodes' failed (exit {result.returncode}): "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )

            if attempt < attempts:
                self._sleep(_VERIFY_RETRY_DELAY_SECONDS)

        detail = (
            f"Could not confirm '{node_hostname}' joined the cluster "
            f"after {attempts} attempt(s): {last_detail}"
        )
        logger.error(detail)
        raise DeploymentVerificationError(detail)


__all__ = [
    "ClusterEnrollment",
    "ClusterJoinResult",
    "ClusterVerificationResult",
    "CommandRunner",
]
