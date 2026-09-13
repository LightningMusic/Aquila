"""
Project Aquila
=============

Technician Console: Main-Thread Bridge

``workflows.workflow_manager.WorkflowManager.start_retirement_workflow()``/
``start_provisioning_workflow()`` are documented as "blocking,
synchronous calls" (see that module's own docstring). Tkinter is not
thread-safe: every widget must only be created, read, or mutated from
the thread that called ``Tk()`` and is running ``mainloop()`` (this is
documented Tk/Tkinter behavior, not an assumption -- touching a widget
from another thread produces undefined behavior, up to and including a
crash). Calling ``WorkflowManager.start_*_workflow()`` directly from
the Tk main thread would freeze the entire GUI event loop for the
whole deployment session (multi-minute Provisioning runs, REQ-PROV per
NFR-PERF-003's "deployment progress shall remain responsive throughout
long-running operations" -- unsatisfiable if the UI thread is blocked
inside a synchronous call).

This module is the bridge: a deployment workflow runs on a background
``threading.Thread``, and the two directions of communication that
need to cross the thread boundary are both handled here.

1. Worker -> UI (fire-and-forget): ``WorkflowStageEvent``s and
   fine-grained progress callbacks. :meth:`MainThreadBridge.post`
   queues a callable; :meth:`MainThreadBridge.pump` (scheduled via
   ``Tk.after()``, so it always runs on the main thread) drains the
   queue and invokes each callable there.

2. UI -> Worker -> UI (round trip, blocking): every technician
   decision point (``PreparationConfirmationProvider``,
   ``RecoveryDecisionProvider``, ``TargetDeviceSelector``) is a
   callback the workflow invokes *from the worker thread* and needs a
   real return value from *before it can continue*. A Tkinter modal
   dialog, however, can only be constructed on the main thread.
   :meth:`MainThreadBridge.call_blocking` closes this loop: it posts a
   request onto the same queue :meth:`pump` already drains, then blocks
   the calling (worker) thread on a ``threading.Event`` until the main
   thread has run the dialog and recorded a result.

New file added to ``technician_console/`` beyond the pre-planned stub
set (``__init__.py``, ``dialogs.py``, ``main_window.py``, ``progress.py``,
``status_panel.py``, ``workflow_selector.py``). Justified the same way
``workflows/progress.py``/``common/constants/controller_api.py`` were
in earlier sessions: this cross-cutting thread-safety concern is used
by every one of the six planned files, and none of them is a more
natural home for it than a dedicated module.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Callable, Generic, Optional, TypeVar

_T = TypeVar("_T")

#: How often ``Tk.after()`` re-schedules :meth:`MainThreadBridge.pump`,
#: in milliseconds. Frequent enough that a technician never perceives
#: lag between a worker-thread event and its on-screen appearance
#: (NFR-USE-002's "progress indicators... during all operations
#: expected to exceed five seconds" implies sub-second responsiveness
#: for anything actually being shown), without busy-polling.
PUMP_INTERVAL_MS = 100


@dataclass(slots=True)
class _BlockingRequest(Generic[_T]):
    """
    One in-flight worker-thread request awaiting a main-thread-produced
    result -- the payload :meth:`MainThreadBridge.call_blocking` queues
    and :meth:`MainThreadBridge.pump` fulfills.
    """

    run_on_main_thread: Callable[[], _T]
    done: threading.Event = field(default_factory=threading.Event)
    result: Optional[_T] = None
    error: Optional[BaseException] = None


class MainThreadBridge:
    """
    Marshals calls from a background workflow thread onto the Tk main
    thread -- see the module docstring for the two communication
    patterns this supports.
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

    # ------------------------------------------------------------------
    # Worker -> UI (fire-and-forget)
    # ------------------------------------------------------------------

    def post(self, callback: Callable[[], None]) -> None:
        """
        Queue ``callback`` to run on the main thread at the next
        :meth:`pump`. Safe to call from any thread, including the main
        thread itself.
        """

        self._queue.put(callback)

    # ------------------------------------------------------------------
    # Worker -> UI -> Worker (blocking round trip)
    # ------------------------------------------------------------------

    def call_blocking(self, run_on_main_thread: Callable[[], _T]) -> _T:
        """
        Run ``run_on_main_thread`` on the main thread (typically: show
        a modal dialog and return the technician's answer) and block
        the calling thread until it completes.

        Must be called from a thread other than the main thread --
        calling it from the main thread would deadlock, since nothing
        would ever drain the queue while this call is blocked waiting
        for it. Every ``workflows/`` callback Protocol
        (``PreparationConfirmationProvider``, ``RecoveryDecisionProvider``,
        ``TargetDeviceSelector``) is documented as being invoked from
        inside a workflow's own synchronous call -- which
        ``technician_console/`` always runs on the background workflow
        thread (see :mod:`technician_console.main_window`) -- so this
        precondition always holds for their real call sites.

        Raises:
            RuntimeError: If called from the main thread.
            BaseException: Whatever ``run_on_main_thread`` itself
                raised, re-raised here on the calling thread so normal
                exception handling (a workflow stage's own try/except,
                or the outer thread's uncaught-exception reporting)
                sees it exactly as if the call had been made directly.
        """

        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "MainThreadBridge.call_blocking() must not be called "
                "from the main thread -- it would deadlock waiting for "
                "a queue nothing is left running to drain."
            )

        request: _BlockingRequest[_T] = _BlockingRequest(
            run_on_main_thread=run_on_main_thread
        )

        def _fulfill() -> None:
            try:
                request.result = request.run_on_main_thread()
            except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
                request.error = exc
            finally:
                request.done.set()

        self._queue.put(_fulfill)
        request.done.wait()

        if request.error is not None:
            raise request.error
        return request.result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Main-thread pump
    # ------------------------------------------------------------------

    def pump(self) -> None:
        """
        Drain and run every callable currently queued. Must only be
        called from the main thread -- intended to be scheduled
        repeatedly via ``Tk.after(PUMP_INTERVAL_MS, bridge.pump)``,
        which itself guarantees main-thread execution.
        """

        while True:
            try:
                callback = self._queue.get_nowait()
            except queue.Empty:
                return
            callback()


__all__ = ["PUMP_INTERVAL_MS", "MainThreadBridge"]
