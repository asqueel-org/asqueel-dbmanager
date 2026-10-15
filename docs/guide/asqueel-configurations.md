# Asqueel configurations

This workspace is available in the source checkout after the 0.2.1 release.
Install its optional integration and UI from the repository:

```bash
python -m pip install -e '.[ui,asqueel]'
asqueel-dbmanager --ui
```

Open **Registration → Asqueel configurations**. Gramlot authors the page;
standard HTML tabs, expandable trees and JavaScript provide the first viewer.
No additional Gramlot component library is required.

## Use the existing Asqueel registry

The server reads `~/.asqueel/databases`, or the directory selected by
`ASQUEEL_HOME`, through Asqueel's `DatabaseRegistry`. Each registration points
to a configuration folder containing `configure.py`. For example, if that
folder already exists:

```bash
asqueel register gestionale /absolute/path/to/configuration
asqueel list
asqueel check gestionale
```

Select its registered name and click **Load configuration**. The page accepts
registered names only, not arbitrary paths or uploaded Python. Registry cards,
recipes and credentials are not copied into DB Manager's encrypted catalog.
This workspace does not require the catalog encryption key or AI enrollment.

The server must have the recipe's Python dependencies and environment variables.
Registration is local to the server process's user and `ASQUEEL_HOME`; a registry
on another computer is not automatically visible. An empty list explains how
to register a configuration. The public Asqueel 0.5.2 API and the local 0.6
checkout have both been exercised; package objects appear when the loaded model
supports them. Development recipes may require the matching Asqueel checkout.

All operations in this workspace require DB Manager administrator access. In
standalone localhost mode this is the existing local administrator context; on
Kajenn, the identity must have `dbmanager_admin`. Loading a registered recipe
executes trusted Python and its normal model-building resolvers. Register only
code trusted by the server administrator.

## Configuration & Objects

Two trees appear side by side:

- **Configuration Bag:** the assembled Bag used by the configuration handler,
  including node attributes and static values. Resolver nodes and attributes
  show their type without running them for display.
- **Constructed objects:** the actual database, table, column and relation
  handles, their class names and completed model attributes. Package and schema
  descriptors appear when supplied by Asqueel. Tables are nested as
  `db → packages → package → tables → table → columns / relations`.
  Recipes declaring tables directly under schemas instead use
  `db → schemas → schema → tables → table`. Package membership comes from
  Asqueel's resolved descriptors, not from physical SQL schema names: multiple
  packages can share a SQL schema. Collection nodes are viewer groupings over
  the actual handles in Asqueel's flat table registry, not runtime objects.
  Older versions without schema descriptors use a labeled collection instead.
  The viewer does not traverse
  connections, query results, owner cycles or arbitrary object internals.

Expand a branch with its disclosure arrow; click a node label for its path,
attributes and value in the details pane below. Search matches names, paths
and displayed details. **Reset trees** restores the initial expansion level.
Credentials and connection strings are hidden before data reaches the browser;
arbitrary object representations are not serialized. These are read-only views.

## Migration

Click **Read / refresh comparison** to display:

- **Desired:** `SqlMigrationRenderer(to_physical_builder(db.model)).render()`.
  Physical names are resolved by Asqueel; virtual/application-only attributes
  are not projected into DDL. The root database name is aligned with the actual
  configured connection.
- **Current:** Asqueel Migration introspection of the physical database, limited
  to the schemas managed by that desired model.

The two JSON trees use aligned paths, synchronized expansion and node selection.
**Only differences** hides equal branches. Labels distinguish **Desired only**,
**Database only** and **Changed**; missing values are distinct from JSON `null`.
The JSON comparison is an inspection aid. Migration's SQL plan determines which
changes are supported and permitted, so visible differences do not necessarily
produce SQL, especially with removals disabled.

Database comparison and migration currently support PostgreSQL. The first tab
can inspect other configurations supported by Asqueel without introspection.
Comparison requires access to the configured PostgreSQL server. The migration
reader can represent a missing database as an empty structure; its plan then
includes database creation. Reading or previewing that plan does not create it.

## Review and apply

1. Click **Preview migration plan** and review SQL, warnings, skipped operations,
   managed schemas and the physical target database.
2. Leave removals disabled unless intentionally needed. Changing that option or
   the selected configuration invalidates the displayed approval.
3. Type the **registered Asqueel configuration name** and click **Apply reviewed
   plan**. The button stays disabled for an empty or unsupported plan.
4. DB Manager reloads the configuration, derives the desired structure again,
   and calls its existing migration service with the reviewed `expected_plan`.
   The service acquires the database lock and replans before applying. Changed
   targets, models or database structures reject a stale plan.
5. Inspect the execution result and refreshed comparison. `verified: false`
   reports remaining differences, not rollback. A failed application clears the
   UI approval; review a new plan before another attempt.

No application data is read for the tree views. No migration is run by loading,
searching, expanding, comparing or previewing. See [migration safeguards](migrations.md)
for locking, transaction boundaries and failure recovery.

## REST and MCP

The same services are actions on `console_action`, protected by the same
administrator gate:

| Action | Data |
| --- | --- |
| `asqueel_list` | `{}` |
| `asqueel_inspect` | `configuration` |
| `asqueel_compare` | `configuration` |
| `asqueel_plan` | `configuration`, optional boolean `allow_removals` |
| `asqueel_apply` | `configuration`, `expected_plan`, `confirm_configuration`, optional boolean `allow_removals` |

For example:

```json
{"action": "asqueel_compare", "data": {"configuration": "gestionale"}}
```

`asqueel_apply` derives connection and structure from the registered recipe;
client-supplied connections or desired structures are not used by this action.
