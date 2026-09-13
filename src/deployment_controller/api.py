"""
Project Aquila
=============

Deployment Controller API Server

Implements REQ-CTRL-021 ("The Deployment Controller shall expose a
documented API for Aquila components") and REQ-SEC-001 ("All
communication between Aquila nodes and the Deployment Controller
shall occur over encrypted channels").

This is a standard-library HTTP(S) server
(``http.server.ThreadingHTTPServer`` + ``ssl``), not a third-party web
framework -- every dependency this project has added so far
(``requests``, ``pyyaml``, ``wmi``/``pywin32``) was added because the
standard library genuinely cannot do the job (HTTP client sessions,
YAML, Windows WMI); a small, fixed set of JSON routes is well within
what ``http.server`` handles directly, so no new dependency
(``flask``/``fastapi``/etc.) is introduced for it.

Routes (relative to ``ControllerServerConfig.api_base_path``, matching
``bootstrap.controller_client.DeploymentControllerClient``'s contract
exactly):

    GET  /health
    POST /nodes/authenticate
    GET  /nodes/configuration?node_identifier=...
    POST /nodes/completion
    POST /inventory/nodes
    GET  /inventory/nodes?node_identifier=&hostname=&manufacturer=&model=&serial_number=&status=&limit=&offset=
    POST /inventory/benchmarks
    GET  /inventory/benchmarks?node_identifier=...

The two ``GET /inventory/...`` routes are not part of
``DeploymentControllerClient``'s node-facing contract -- they back
``services.inventory_service``/``services.benchmark_service`` for the
Technician Console (REQ-INV-010, REQ-BENCH-010) and are gated by
``NodeAuthenticator.authenticate_operator`` rather than a specific
node's identity. See ``controller.py``'s handler docstrings.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, cast
from urllib.parse import parse_qs, urlsplit

from common.constants.controller_api import (
    AUTHENTICATE_ENDPOINT,
    BENCHMARK_ENDPOINT,
    COMPLETION_ENDPOINT,
    CONFIGURATION_ENDPOINT,
    HEALTH_ENDPOINT,
    INVENTORY_ENDPOINT,
)
from common.constants.logging import INVENTORY_LOGGER
from common.events.types.controller import (
    ControllerStartedEvent,
    ControllerStoppedEvent,
)
from config.schemas.controller_server_schema import ControllerServerConfig
from deployment_controller.controller import DeploymentController

logger = logging.getLogger(INVENTORY_LOGGER)


def _build_ssl_context(config: ControllerServerConfig) -> Optional[ssl.SSLContext]:
    """
    Build the server-side TLS context (REQ-SEC-001, REQ-CTRL-020:
    "support secure communication channels").

    Returns ``None`` when TLS is disabled -- a deliberate, non-default
    configuration only intended for local development against
    ``bind_host="127.0.0.1"``, never Aquila's shipped default (see
    ``ControllerServerConfig.use_tls``'s docstring).
    """

    if not config.use_tls:
        return None

    if not config.tls_certificate_path or not config.tls_private_key_path:
        raise ValueError(
            "ControllerServerConfig.use_tls is True but "
            "tls_certificate_path/tls_private_key_path were not both "
            "supplied. Provide a certificate and private key, or set "
            "use_tls=False for local development only."
        )

    cert_path = Path(config.tls_certificate_path)
    key_path = Path(config.tls_private_key_path)

    if not cert_path.is_file() or not key_path.is_file():
        raise ValueError(
            f"TLS certificate ('{cert_path}') or private key "
            f"('{key_path}') does not exist."
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class _AquilaHTTPServer(ThreadingHTTPServer):
    """A ``ThreadingHTTPServer`` carrying the Controller it serves."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        controller: DeploymentController,
        api_base_path: str,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.controller = controller
        self.api_base_path = api_base_path.rstrip("/") or ""


class _ControllerRequestHandler(BaseHTTPRequestHandler):
    """Routes HTTP requests to ``DeploymentController`` handler methods."""

    protocol_version = "HTTP/1.1"

    @property
    def _aquila_server(self) -> _AquilaHTTPServer:
        # ``self.server`` is inherited from ``BaseRequestHandler`` typed
        # as the base ``socketserver.BaseServer`` -- a mutable attribute
        # cannot be safely re-narrowed by re-declaring it in a subclass
        # (it would be an invariant override), so this property performs
        # the narrowing cast at every use site instead.
        return cast(_AquilaHTTPServer, self.server)

    # ------------------------------------------------------------------
    # HTTP method entry points
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming convention
        split = urlsplit(self.path)
        server = self._aquila_server
        base = server.api_base_path

        if split.path == f"{base}/{HEALTH_ENDPOINT}":
            self._respond(*server.controller.handle_health())
            return

        if split.path == f"{base}/{CONFIGURATION_ENDPOINT}":
            query = parse_qs(split.query)
            node_identifier = (query.get("node_identifier") or [""])[0]
            self._respond(
                *server.controller.handle_get_configuration(
                    node_identifier, self.headers.get("Authorization")
                )
            )
            return

        if split.path == f"{base}/{INVENTORY_ENDPOINT}":
            query = parse_qs(split.query)
            single_valued = {key: values[0] for key, values in query.items() if values}
            self._respond(
                *server.controller.handle_search_inventory(
                    single_valued, self.headers.get("Authorization")
                )
            )
            return

        if split.path == f"{base}/{BENCHMARK_ENDPOINT}":
            query = parse_qs(split.query)
            node_identifier = (query.get("node_identifier") or [""])[0]
            self._respond(
                *server.controller.handle_get_node_benchmarks(
                    node_identifier, self.headers.get("Authorization")
                )
            )
            return

        self._respond(404, {"error": f"No such route: GET {split.path}"})

    def do_POST(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        server = self._aquila_server
        base = server.api_base_path

        routes = {
            f"{base}/{AUTHENTICATE_ENDPOINT}": server.controller.handle_authenticate,
            f"{base}/{COMPLETION_ENDPOINT}": server.controller.handle_completion,
            f"{base}/{INVENTORY_ENDPOINT}": server.controller.handle_register_inventory,
            f"{base}/{BENCHMARK_ENDPOINT}": server.controller.handle_submit_benchmark,
        }

        handler = routes.get(split.path)
        if handler is None:
            self._respond(404, {"error": f"No such route: POST {split.path}"})
            return

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._respond(400, {"error": f"Invalid JSON request body: {exc}"})
            return

        response = handler(payload, self.headers.get("Authorization"))
        self._respond(*response)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}

        raw = self.rfile.read(length)
        if not raw:
            return {}

        parsed: Any = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Request body must be a JSON object.")

        return cast(Dict[str, Any], parsed)

    def _respond(self, status_code: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # REQ-CTRL-019: "log all communications with Aquila nodes" --
        # ``BaseHTTPRequestHandler`` calls this once per request, so
        # overriding it (into the same logger every other Controller
        # module uses, instead of stderr) makes every request/response
        # this server handles a log line, not just this handler's own
        # explicit ``logger.info``/``logger.warning`` calls.
        logger.info("%s - %s", self.address_string(), format % args)


class ControllerAPIServer:
    """
    Runs the Deployment Controller's HTTP(S) API in a background
    thread. Satisfies ``interfaces.service.Service`` via
    ``initialize``/``shutdown``.
    """

    def __init__(
        self,
        *,
        controller: DeploymentController,
        server_config: ControllerServerConfig,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._controller = controller
        self._config = server_config
        self._event_bus = event_bus
        self._server: Optional[_AquilaHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self.start()

    def shutdown(self) -> None:
        self.stop()

    @property
    def is_initialized(self) -> bool:
        return self._server is not None

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._server is not None:
            return  # already running -- initialize() is idempotent

        if not self._controller.is_initialized:
            self._controller.initialize()

        server = _AquilaHTTPServer(
            (self._config.bind_host, self._config.bind_port),
            _ControllerRequestHandler,
            controller=self._controller,
            api_base_path=self._config.api_base_path,
        )
        server.timeout = self._config.request_timeout_seconds

        ssl_context = _build_ssl_context(self._config)
        if ssl_context is not None:
            server.socket = ssl_context.wrap_socket(server.socket, server_side=True)

        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="aquila-controller-api",
            daemon=True,
        )
        self._thread.start()

        self._publish(
            lambda: ControllerStartedEvent(
                self._config.bind_host, self._config.bind_port
            )
        )
        logger.info(
            "Deployment Controller API listening on %s:%d%s (TLS: %s).",
            self._config.bind_host,
            self._config.bind_port,
            self._config.api_base_path,
            "enabled" if ssl_context is not None else "disabled",
        )

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()

        if self._thread is not None:
            self._thread.join(timeout=10.0)

        self._server = None
        self._thread = None

        self._publish(lambda: ControllerStoppedEvent())
        logger.info("Deployment Controller API stopped.")

    def _publish(self, build_event: Any) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish API server event.", exc_info=True)


__all__ = ["ControllerAPIServer"]
