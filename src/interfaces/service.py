"""
Project Aquila
=============

Service Interface

Defines the structural contract every long-lived Aquila subsystem
manager satisfies: ``config.manager.ConfigurationManager``,
``logging_engine.log_manager.LogManager``, and every future engine
(Preparation, Provisioning, Bootstrap, Deployment Controller, ...)
that ``core.startup``/``core.shutdown`` bring up and tear down
uniformly through the ``ServiceContainer`` (SRS Section 10.14,
NFR-MAIN-002: "Subsystems shall expose documented interfaces").

Defined as a ``typing.Protocol`` rather than an abstract base class:
every concrete manager already exists as an ordinary class with no
common ancestor -- and one of them, ``common.events.bus.EventBus``,
lives in an already-complete package this project isn't modifying --
so structural typing lets each one satisfy this contract simply by
already having the right methods, with no inheritance change required
anywhere, and no risk of a future diamond-inheritance conflict.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Service(Protocol):
    """
    A subsystem manager with an explicit initialize/shutdown lifecycle.

    Satisfied today by ``ConfigurationManager`` and ``LogManager``.
    ``@runtime_checkable`` lets ``core.startup`` verify a registered
    object actually conforms before relying on it (``isinstance(obj,
    Service)``), without requiring that object to inherit from
    anything.
    """

    @property
    def is_initialized(self) -> bool:
        """Whether ``initialize()`` has completed."""
        ...

    def initialize(self) -> None:
        """
        Bring the service up.

        Must be idempotent -- calling it again after a successful
        initialization reconfigures rather than raising or leaking
        resources. This is exactly what ``LogManager.initialize()``
        and ``ConfigurationManager.initialize()`` already guarantee:
        a later call tears down what the first one set up before
        reattaching/reloading, so callers never need to check
        ``is_initialized`` before calling it.
        """
        ...

    def shutdown(self) -> None:
        """
        Tear the service down.

        Must be safe to call on a service that was never initialized
        (a no-op in that case), and safe to call more than once.
        """
        ...


__all__ = ["Service"]
