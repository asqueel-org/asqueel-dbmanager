# Availability and installation

The default GitHub branch includes the implemented beta described in this manual.
The latest documentation is built from that branch. Publication of this source
code does not create a new PyPI release.

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

## Available in the source beta

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

## PyPI package

The existing PyPI release contains the earlier core: PostgreSQL connection checks,
introspection, reviewed migrations, logical backups and restores, REST, OpenAPI,
MCP and legacy job endpoints. It does not yet contain the source beta above.
Use the GitHub installation for the new features until a package release includes
them. The basic PyPI command in [installation](installation.md) remains valid
for that earlier core.

## Planned, not implemented

Automatic database explanations, Genropy package help import, lookup loading,
`database_stats`, privacy-aware result encoding/decoding, AI charts and WAL/PITR
orchestration remain future work. Privacy choices are stored, but result rows are
not sent to the model in the current beta. Jobs are outside the new workbench scope.
