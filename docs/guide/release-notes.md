# Release notes

## 0.2.0

This release packages the workbench and workflows previously available from the
source checkout. Python 3.11+ is supported.

### Added

- Gramlot web workbench with English Getting started instructions, iframe
  navigation, database registration and Genropy legacy instance import.
- Interactive database diagrams with Graphviz initial layout, Cytoscape dragging,
  schema/table/relationship filters, scrollable columns, PNG export and index details.
- CLI introspection, diagrams and logical backup with `-g/--genropy` selection.
- Encrypted named database profiles backed by genro-storage, with a key supplied
  through 1Password or the server environment and per-profile identity allowlists.
- Manual AI enrollment, editable database guides and persisted privacy choices.
- Anthropic query sessions returning SQL or bounded read-only results, PostgreSQL
  error correction and session-scoped prompt-cache maintenance.
- Explicit Kajenn-hosted authentication mode alongside the default local mode.
- A detailed [code guide](code-guide.md) covering classes, architecture and flows.

### Installation and upgrade

Install `asqueel-dbmanager[ui,queries,postgresql]==0.2.0` for all Python features.
The `ui` extra pins the tested Gramlot core to 0.2.16. The migration dependency
requires the 0.2 series, starting at 0.2.1. External tools and setup are listed in
[availability](availability.md).

Back up encrypted profiles and companion metadata and retain the encryption key.
Installing the package does not apply database migrations. The existing REST/MCP
maintenance operations remain available; legacy jobs are outside the new workbench.

### Known scope limits

Gramlot and AI workflows remain beta features. Query sessions are in-process and
expire or disappear on restart. Results are not sent to the model; stored privacy
settings anticipate a future result encoder. Automatic explanations, lookup
loading, database statistics, AI charts and WAL/PITR orchestration are not included.

## 0.1.0

Initial PostgreSQL administration application: connection checks, introspection,
reviewed migrations, logical backups and restores, Kajenn REST/OpenAPI/MCP and
legacy background jobs.
