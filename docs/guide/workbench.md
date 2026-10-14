# Gramlot workbench (beta)

> **Development preview:** this guide describes the local beta, not the code
> currently available from PyPI or the public default branch. See
> [availability](availability.md) before using these commands.

DB Manager includes a minimal web interface authored with Gramlot and native HTML
controls. The left navigation opens pages in same-origin iframes and retains open
pages while switching sections. This is an application beta test of Gramlot;
advanced components from the Gramlot POC are not dependencies.

## Run locally

From the current source checkout:

```bash
python -m pip install -e '.[ui,queries]'
asqueel-dbmanager --ui --port 8000
```

Open [the local workbench](http://127.0.0.1:8000/ui/). When the app is mounted at
`dbmanager`, its URL is `/dbmanager/ui/`. The `ui` extra currently pins the tested
Gramlot core to **0.2.16**; installing that extra makes the UI routes available.
`--ui` checks the installation and prints the URL. The existing API and CLI remain
available without Gramlot.

Configure the encrypted profile key first using [Query sessions](queries.md).
Registering a database checks connectivity and stores the connection encrypted;
credentials are never returned by the workbench API. The Genropy legacy page
imports an instance's primary PostgreSQL connection using the Genropy installation
on the server. It does not yet import package help files or discover all stores.
Existing profiles are not overwritten from the UI.

## Navigation and working flows

- **Start here / Getting started:** the initial workspace contains detailed English
  instructions for access, registration, diagrams, migrations, backup/restore,
  enrollment, chat, privacy and troubleshooting. It opens without accessing the
  encrypted catalog or calling a model. Return here from navigation at any time.
- **Registration:** databases and Genropy legacy instances. Technical registration
  is separate from AI enrollment.
- **Operations / Database diagram:** select a registered database and click
  **Draw / refresh** to introspect its current structure with Migration.
  The embedded Cytoscape viewer uses Graphviz for its initial layout when available,
  with draggable tables, zoom and schema/relationship filters. Open
  **Keys, indexes and constraints** below the viewer for per-table details, or use
  the full-page link for more drawing space. AI enrollment is not required.
  Navigation collapses automatically when opening the diagram; use **☰** to
  reopen it. The canvas fills the remaining workspace. **Filters** and
  **Layout & export** expand on demand; **Tables / details** opens an overlay.
- **Migrations:** read a registered database's structure, load or paste a target
  Migration JSON, preview the plan and explicitly apply the reviewed plan.
  Applying requires typing the logical profile name; changing the target structure
  invalidates the UI's reviewed plan. The backend also checks the plan fingerprint.
- **Backup & restore:** create and list local logical backups for the selected
  profile, then restore a selected archive into an existing empty destination
  database. The destination must be separately registered and confirmed by name.
  This page lists only archives attributed to profiles through the workbench;
  earlier archives remain available through the existing archive API/CLI.
- **AI Queries / Database enrollment:** introspect the actual structure, edit
  explanations and review privacy settings, save a draft or confirm enrollment.
- **AI Queries / Database Guide:** load and revise the same persistent document.
- **AI Queries / Chat:** open a session for an enrolled profile, ask for SQL or
  read-only results, inspect SQL/parameters/assumptions, then close the session.
  The page limits each answer to 100 rows. Navigating to another iframe keeps the
  chat alive; sessions expire automatically and can be explicitly closed.

The first enrollment is manual: it does **not** call Sonnet to generate descriptions.
Descriptions approved as model context are included with the physical structure
when opening subsequent sessions. The guide is frozen for that session. A detected
structure change prevents using a previously approved guide until refreshed and
reviewed. Refresh keeps explanations and column choices for surviving tables and
columns, hides newly discovered tables by default and returns the guide to draft.
Concurrent edits are detected using a revision number. Guide metadata is encrypted
beside the profile in `.console_NAME.json`; do not remove these files when backing
up the profile catalog.

## Privacy in this beta

Tables default to `privacy="H"`. Table sharing is a checkbox; columns offer
**Inherit / Share / Hide**, preserving the difference between an absent attribute
and explicit `None` (`null` in JSON). The effective setting is shown for each field.

These settings are persisted for the future encoder. **This beta never forwards
query result rows to the model**, even when a field is marked Share. Query results
are shown to the authorized user. The model receives structure, approved guide
explanations, user questions and generated SQL history. Do not put confidential
values in explanations intended for model context.

Automatic analysis, package `llm_help.md`, lookup loading, `database_stats`,
encoding/decoding result datasets and model-generated charts are subsequent work.
They are not implied by confirming enrollment. Enrollment gates the web chat;
existing query-session APIs still support the earlier structure-only workflow for
profiles without an approved guide.

## Access modes

`DbManagerApp` defaults to `access_mode="local"`: loopback clients and loopback
Host only, with the trusted `local` identity unless Kajenn provides an Avatar.
Local mode is for a trusted personal machine, not isolation between its users.
Cross-site requests and mismatching browser origins are rejected; the workbench
is framed only by the same origin. All POST requests use JSON.

For a host with authentication already configured, mount with:

```python
AsgiServer(applications=[
    (DbManagerApp, {"code": "database_admin", "mount": "dbmanager",
                    "access_mode": "kajenn"}),
])
```

The host must supply an authenticated Kajenn Avatar on every request. DB Manager
has no login page and never falls back to `local` in this mode. Profile allowlists
use `Avatar.identity`. New registrations belong to that identity. The
`dbmanager_admin` tag is required to register connections, execute migrations,
create backups or restore, and to access the legacy raw-connection/archive/MCP
surfaces. Authorized profile users can use the workbench's inspection, diagram and query
operations through REST. Assigning identities/tags and HTTPS termination remain
responsibilities of the host.

Workbench diagram snapshots retain the profile name and version. Every HTML or
data download rechecks profile access; replacing the connection invalidates older
snapshots. These viewers permit same-origin embedding in the workbench.

This is a database-level allowlist, not row/column authorization. Privacy flags
control future outbound model data, not PostgreSQL privileges. Single-process
session and concurrency limits remain in effect.

## Gramlot integration and beta evidence

The current `gramlot-py-server` Kajenn adapter requires Kajenn >=0.4.1, whereas
DB Manager currently depends on Kajenn <0.2. A small ASGI bridge therefore hosts
the **Gramlot core** `GramlotFileServer` inside DB Manager's existing app. It serves
bootstrap, runtime and fixed assets, and forwards the core's Source protocol.
The browser page owner combines a private cookie with the current Kajenn identity.
There are no page-defined business endpoints; operations use the same
`console_action` REST/MCP service.

This bridge is deliberately isolated in `web_ui.py` so it can be replaced with
the standard adapter after a deliberate Kajenn upgrade. A framework upgrade must
recheck page loading, navigation, forms, identity propagation and saving. The POC
is a reference for future grids and charts, not a promise that their APIs already
exist in this core release.
