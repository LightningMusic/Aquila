"""
Project Aquila
=============

Deployment Controller

Implements SRS Section 9.7/10.8, REQ-CTRL-001 through REQ-CTRL-021:
the centralized service that authenticates, authorizes, configures,
and registers Aquila nodes.

Public surface:
    * ``DeploymentController`` -- the composition root / request
      handlers (``controller.py``).
    * ``ControllerAPIServer`` -- the HTTP(S) listener (``api.py``).
    * ``NodeAuthenticator``/``TokenValidator`` -- REQ-CTRL-001/002
      (``authentication.py``).
    * ``DeploymentAuthorizer`` -- REQ-CTRL-016 (``authorization.py``).
    * ``ConfigurationDistributor`` -- REQ-CTRL-006/007
      (``configuration.py``).
    * ``InventoryIntake`` -- REQ-CTRL-009/013 (``inventory.py``).
    * ``DeploymentReportIntake`` -- REQ-CTRL-015 (``reports.py``).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from deployment_controller.api import ControllerAPIServer
from deployment_controller.authentication import (
    NodeAuthenticator,
    TokenValidator,
)
from deployment_controller.authorization import DeploymentAuthorizer
from deployment_controller.configuration import ConfigurationDistributor
from deployment_controller.controller import (
    ControllerDependencies,
    DeploymentController,
    build_dependencies,
)
from deployment_controller.inventory import InventoryIntake
from deployment_controller.reports import DeploymentReportIntake

__all__ = [
    "ConfigurationDistributor",
    "ControllerAPIServer",
    "ControllerDependencies",
    "DeploymentAuthorizer",
    "DeploymentController",
    "DeploymentReportIntake",
    "InventoryIntake",
    "NodeAuthenticator",
    "TokenValidator",
    "build_dependencies",
]
