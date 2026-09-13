# ADR-0002: Markdown Documentation

## Status

Accepted

## Context

Project Aquila's intended audience (SRS Section 6) explicitly includes
developers, system administrators, AI coding assistants, testers, and
future contributors working directly against the Git repository. GP-010
(Documentation First) requires that "no production feature shall be
implemented before its behavior has been documented within this Software
Requirements Specification" and that documentation stay authoritative and
current throughout the project's lifecycle (SRS Section 13.5).

## Decision

All Project Aquila documentation — the SRS itself, Architecture Decision
Records, the roadmap, and this changelog — is written in plain Markdown
and stored in the Git repository (`docs/`), not in an external wiki,
word processor document, or proprietary format.

## Consequences

- Documentation is version-controlled alongside the code it describes:
  a requirement change and the code change it justifies can land in the
  same commit or pull request, and history/blame apply to
  specification text exactly as they do to source code.
- Documentation is diffable and mergeable through ordinary Git tooling,
  with no lock-in to a specific editor or hosted service to read or edit
  it.
- Plain text is directly and reliably consumable by AI coding
  assistants (an explicitly named member of the intended audience),
  without a lossy export or conversion step.
- No rich formatting (embedded diagrams-as-images aside, used sparingly
  and only where an ASCII/text diagram genuinely cannot substitute) is
  available; where a real diagram is warranted, it is authored as text
  (ASCII art, as already used throughout the SRS's architecture
  sections) rather than as an external binary asset, preserving the
  diffability property above.
- A synced external copy of the SRS (e.g. a GitHub-hosted document
  mirrored into the Claude Project) is treated as a second view onto
  the same Markdown source of truth, not an independent document — a
  defect found in one is a defect in both, and is recorded as such
  (see, for example, the duplicate-section defect noted in
  `provisioning/__init__.py`'s module docstring).
