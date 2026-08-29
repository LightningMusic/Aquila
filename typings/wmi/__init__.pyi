"""
Minimal, hand-written type stub for the third-party ``wmi`` package
(https://pypi.org/project/WMI/).

The real ``wmi`` package ships no type information (no ``py.typed``
marker, no bundled ``.pyi`` files), and none is published on the
typeshed third-party stub index either. Under strict type checking
this means every attribute pulled from a live import of ``wmi``
resolves to ``Unknown``, and that "Unknown"-ness silently spreads into
any code that touches the result -- even code, elsewhere in this
project, whose own declared types are fully known (e.g. helper methods
already annotated to return ``List[Any]``).

This stub does not attempt to model the full WMI COM surface -- the
real package exposes an open-ended set of dynamically generated
classes and properties determined at runtime by whatever WMI classes
exist on the target Windows system, which is not something a static
stub can enumerate. It instead models exactly the calling convention
every Aquila BIOS provider actually uses:

    connection = wmi.WMI(namespace=r"root\\wmi")
    for row in connection.query("SELECT * FROM Win32_BIOS"):
        value = getattr(row, "SomePropertyName", None)

That is: constructing a connection with keyword arguments, calling
``.query()`` with a WQL string to get back a list of dynamically
shaped result rows, and reading arbitrary properties off each row
(always through ``getattr`` with a default, in this codebase -- never
through a statically known attribute name). ``_WMIRow`` models that
last part with ``__getattr__``, which is the intentionally correct
type-safe way to describe "an object whose attributes are only known
at runtime": callers still get ``Any`` back (so they can do whatever
they need with it) but pyright now knows *why* -- it is a deliberate,
declared dynamic surface rather than an unresolved import.

Only the keyword arguments Aquila's providers actually pass to
``wmi.WMI(...)`` are named explicitly; everything else the real
constructor accepts is covered by ``**kwargs`` so this stub never
rejects a legitimate call.
"""

from typing import Any, List

class _WMIRow:
    """A single dynamically-shaped WMI query result row."""

    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...

class _WMINamespace:
    """A connected WMI namespace handle, as returned by ``wmi.WMI(...)``."""

    def query(self, wql: str, *args: Any, **kwargs: Any) -> List[_WMIRow]: ...
    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...

def WMI(
    computer: str = ...,
    namespace: str = ...,
    moniker: str = ...,
    user: str = ...,
    password: str = ...,
    find_classes: bool = ...,
    debug: bool = ...,
    privileges: Any = ...,
    **kwargs: Any,
) -> _WMINamespace: ...

class x_wmi(Exception):
    """Base exception raised by the ``wmi`` package on query/connection failure."""

    ...

class x_wmi_timed_out(x_wmi): ...
class x_access_denied(x_wmi): ...
class x_wmi_authentication(x_wmi): ...
