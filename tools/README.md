# tools/

Developer-facing tooling that supports the engineering process itself,
not part of the shipped product (see `docs/ADR/ADR-0001-Repository-Structure.md`).

## `check_requirement_traceability.py`

Implements SRS Section 13.2's own requirement that every `REQ-*`/`NFR-*`
identifier be traceable to source code and test cases. Extracts every
identifier the SRS defines as a heading, then checks whether each one is
cited by name anywhere in `src/` and anywhere in the `run_tests_*.py`
suite.

```powershell
uv run python tools/check_requirement_traceability.py
uv run python tools/check_requirement_traceability.py --strict   # also fail on missing test citations
uv run python tools/check_requirement_traceability.py --format json
```

Exit code `0` means every requirement has at least one source citation
(and, under `--strict`, at least one test citation too); `1` means at
least one does not — read the printed list, it names exactly which ones.
A missing *source* citation is worth treating as a real gap (either the
requirement was never implemented, or nobody wrote down which code
implements it). A missing *test* citation is a weaker signal — plenty of
requirements are exercised indirectly by a broader test rather than cited
by identifier — which is why it is reported separately and does not fail
the run unless `--strict` is passed.

This tool does not, and cannot, judge whether a citation reflects a
*correct* implementation — only whether one was ever written down. Use it
to find gaps to investigate, not as proof of correctness on its own.
