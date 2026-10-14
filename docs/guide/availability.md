# Availability and installation

Version **0.2.0** includes the workbench, diagrams, Genropy integration and AI
query sessions described in this manual. The UI and AI workflows remain beta
features. Read the [release notes](release-notes.md) and [code guide](code-guide.md)
for changes and implementation details.

## Install from PyPI

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'asqueel-dbmanager[ui,queries,postgresql]==0.2.0'
asqueel-dbmanager --ui --port 8000
```

To upgrade an existing installation, run `python -m pip install --upgrade
'asqueel-dbmanager[ui,queries,postgresql]>=0.2.0'`. Back up the encrypted profile
catalog together with its metadata and preserve access to its encryption key.
No automatic database schema migration is performed by package installation.

## Install all current features from GitHub

Requires Python 3.11+ and access to PostgreSQL:

```bash
git clone https://github.com/asqueel-org/asqueel-dbmanager.git
cd asqueel-dbmanager
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ui,queries,postgresql]'
asqueel-dbmanager --ui --port 8000
```

Open `http://127.0.0.1:8000/ui/`. The Getting started page explains registration,
diagrams, maintenance and AI enrollment. When mounted at `dbmanager`, the URL
is `/dbmanager/ui/`. Configure the encrypted catalog key before registration
and provider credentials before AI queries; see [query sessions](queries.md).

## Included in 0.2.0

- Gramlot web workbench and English Getting started instructions.
- Encrypted PostgreSQL profiles and Genropy legacy instance registration.
- Graphviz layout and interactive Cytoscape diagrams, filters and index details.
- CLI introspection, diagrams and backup with Genropy instance selection.
- Reviewed migrations, logical backup and restore through registered profiles.
- AI query sessions, manual enrollment and database guide editing.
- Local access or explicit Kajenn-hosted authentication and profile allowlists.

The UI uses Gramlot core with native HTML controls while the framework evolves.
These features are beta functionality; the guides describe their operational
limits. See [workbench](workbench.md), [CLI](cli.md), [diagrams](diagrams.md) and
[query sessions](queries.md).

## External tools and optional dependencies

The `ui` extra installs Gramlot core; `postgresql` and `queries` include the
PostgreSQL driver integration. Graphviz `dot` is optional for the interactive
layout and required for SVG generation. Backups need compatible `pg_dump` and
`pg_restore`. Genropy instance resolution needs a Genropy installation on the
server. 1Password-backed profiles need the `op` CLI; a server environment key is
also supported. AI queries require provider configuration.

## Planned, not implemented

Automatic database explanations, Genropy package help import, lookup loading,
`database_stats`, privacy-aware result encoding/decoding, AI charts and WAL/PITR
orchestration remain future work. Privacy choices are stored, but result rows are
not sent to the model in the current beta. Jobs are outside the new workbench scope.
