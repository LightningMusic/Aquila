"""
Project Aquila
=============

Application Lifecycle

Tracks Project Aquila's application-wide state
(``common.enums.ApplicationState``) through a validated transition
graph, and publishes the corresponding lifecycle event whenever a
transition actually happens.

``common.application.Application`` already tracks two coarse booleans
(``initialized``, ``running``); this module sits alongside it and
gives ``core.startup``/``core.shutdown`` a richer, validated state
machine to drive and to fail loudly against, rather than each having
to reimplement "is this transition even legal right now" logic
independently.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from common.enums import ApplicationState
from common.events.event import ApplicationStartedEvent, ApplicationStoppingEvent
from common.exceptions.application import AquilaStateError

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(__name__)

#: The only legal transitions out of each state. ``STOPPED`` has none
#: -- it is terminal, matching NFR-REL-003 ("Unexpected shutdowns
#: shall not leave deployment state in an undefined condition"): once
#: an ``ApplicationLifecycle`` reaches ``STOPPED``, its state is
#: final and well-defined; running again means constructing a new
#: ``Application``/``ApplicationLifecycle`` pair, not resuming this
#: one.
_VALID_TRANSITIONS: dict[ApplicationState, frozenset[ApplicationState]] = {
    ApplicationState.STARTING: frozenset(
        {ApplicationState.INITIALIZING, ApplicationState.FAILED}
    ),
    ApplicationState.INITIALIZING: frozenset(
        {ApplicationState.RUNNING, ApplicationState.FAILED}
    ),
    ApplicationState.RUNNING: frozenset(
        {ApplicationState.STOPPING, ApplicationState.FAILED}
    ),
    ApplicationState.STOPPING: frozenset(
        {ApplicationState.STOPPED, ApplicationState.FAILED}
    ),
    ApplicationState.FAILED: frozenset({ApplicationState.STOPPED}),
    ApplicationState.STOPPED: frozenset(),
}


class ApplicationLifecycle:
    """
    Validated ``ApplicationState`` state machine for one application
    run.

    A new instance always starts in ``ApplicationState.STARTING``
    (matching ``common.enums.ApplicationState``'s own ordering: it is
    the first state listed, and every other Aquila lifecycle begins
    there). Every subsequent state change must go through
    :meth:`transition_to`, which raises rather than silently
    accepting an illegal transition.
    """

    def __init__(self, event_bus: Optional["EventBus"] = None) -> None:
        self._state = ApplicationState.STARTING
        self._event_bus: Optional["EventBus"] = event_bus
        self._history: list[ApplicationState] = [ApplicationState.STARTING]

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> ApplicationState:
        """The current lifecycle state."""

        return self._state

    @property
    def history(self) -> tuple[ApplicationState, ...]:
        """Every state this lifecycle has passed through, in order."""

        return tuple(self._history)

    @property
    def is_terminal(self) -> bool:
        """Whether the current state has no legal outgoing transition."""

        return not _VALID_TRANSITIONS[self._state]

    def can_transition_to(self, new_state: ApplicationState) -> bool:
        """Whether ``new_state`` is a legal transition from the current state."""

        return new_state in _VALID_TRANSITIONS[self._state]

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition_to(self, new_state: ApplicationState) -> None:
        """
        Move to ``new_state``.

        Raises:
            AquilaStateError:
                If ``new_state`` is not a legal transition from the
                current state (for example, ``RUNNING`` ->
                ``STARTING``, or any transition out of ``STOPPED``).
        """

        allowed = _VALID_TRANSITIONS[self._state]

        if new_state not in allowed:
            allowed_names = ", ".join(
                sorted(state.name for state in allowed)
            )

            raise AquilaStateError(
                f"Cannot transition Aquila's application lifecycle "
                f"from {self._state.name} to {new_state.name}. "
                f"Valid transitions from {self._state.name}: "
                f"{allowed_names or '(none -- this is a terminal state)'}."
            )

        previous = self._state
        self._state = new_state
        self._history.append(new_state)

        logger.debug(
            "Application lifecycle: %s -> %s",
            previous.name,
            new_state.name,
        )

        self._publish(new_state)

    def _publish(self, state: ApplicationState) -> None:
        if self._event_bus is None:
            return

        event = None

        if state is ApplicationState.RUNNING:
            event = ApplicationStartedEvent()

        elif state is ApplicationState.STOPPING:
            event = ApplicationStoppingEvent()

        if event is None:
            return

        try:
            self._event_bus.publish(event)
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug(
                "Failed to publish application lifecycle event.",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(state={self._state.name})"


__all__ = ["ApplicationLifecycle"]
