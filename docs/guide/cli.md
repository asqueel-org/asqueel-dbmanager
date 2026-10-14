# Command line

> **Source beta:** these features are available on the public GitHub branch.
> Install from source for UI, diagrams, Genropy CLI and AI queries; the PyPI
> package has not been updated yet. See [availability](availability.md).

The CLI runs operations locally, without starting the HTTP/MCP server or using
background jobs. `python -m asqueel_dbmanager` accepts the same arguments as
`asqueel-dbmanager`.

## Select a Genropy database

Use `-g INSTANCE` or `--genropy INSTANCE` with `introspect`, `backup` and
`diagram`. All three commands use the same configuration resolver and connect
to the instance's primary PostgreSQL database. Genropy and its dependencies
must be available in the same Python environment as
`asqueel-dbmanager[postgresql]`.

Connection parameters are used in memory and are never written to a connection
profile, output JSON or backup metadata. Genropy's application is not started.
The resolver supports instance defaults/templates, environment references and
the `GNR_DB_DSN` override; see [Genropy configuration details](diagrams.md#from-a-genropy-instance).
Remote/store selectors and automatic SSH tunnels are not supported.

## Export the database structure

```bash
asqueel-dbmanager introspect -g test_invoice_pg -o structure.json
asqueel-dbmanager introspect -g test_invoice_pg --schema public --schema sales
```

The output is normalized Migration JSON. Without `--schema`, all accessible
non-system schemas are discovered. Repeat `--schema` to limit the result.
Output defaults to stdout; `-o FILE` writes UTF-8 and refuses to overwrite an
existing file. This reads database metadata without changing its structure.

Use the result as input for a diagram:

```bash
asqueel-dbmanager diagram structure.json -o structure.svg
asqueel-dbmanager introspect -g test_invoice_pg | asqueel-dbmanager diagram - --format dot
```

Include foreign-key target schemas when filtering if the exported structure
will be validated or rendered.

## Create a database backup

```bash
asqueel-dbmanager backup -g test_invoice_pg --backup-dir ./backups
```

The command runs the existing logical backup operation synchronously, using
`pg_dump` in custom format and `pg_restore --list` for an initial readability
check. Both executables must be available on `PATH`, with versions compatible
with the database server.

The store is selected by `--backup-dir`, then `ASQUEEL_DBMANAGER_BACKUP_DIR`,
then `.dbmanager/backups` relative to the current directory. Each backup gets
a new identifier and contains:

```text
<backup-dir>/<backup_id>/database.dump
<backup-dir>/<backup_id>/metadata.json
```

Stdout contains JSON metadata with the `backup_id`, database name, timestamp,
size, SHA-256 and `pg_dump` version. The archive contains database data; the
connection password is not included in metadata or subprocess command arguments.
No output filename is required, and existing archives are not overwritten.

Use the same store directory when listing, verifying or restoring this backup
through REST/MCP. See [backup and restore](backups.md) for the existing restore
contract. This CLI command backs up a single database, not a PostgreSQL cluster
or WAL history.

## Other commands

```bash
asqueel-dbmanager capabilities
asqueel-dbmanager diagram -g test_invoice_pg -o diagram.svg
asqueel-dbmanager diagram -g test_invoice_pg --schema invc -o invoices.svg
asqueel-dbmanager diagram -g test_invoice_pg --cluster invc.invc_invoice --depth 1 -o cluster.svg
asqueel-dbmanager diagram -g test_invoice_pg --server-url http://127.0.0.1:8000/dbmanager
asqueel-dbmanager --port 8000
```

`--server-url` publishes a saved HTML diagram on a running server and prints its
full browser URL. Include the mount prefix if applicable; omit `/dbmanager` for
the default standalone CLI server. Rendering happens on that server. See
[browser pages](diagrams.md#publish-a-browser-page) for storage and lifecycle.

Use repeatable `--schema` and `--table` to restrict the view, or `--cluster`
with optional `--relatives` and `--depth` to follow foreign keys. See
[diagram filters](diagrams.md#filter-schemas-tables-and-related-clusters).

SVG output requires Graphviz; introspection, backup and DOT output do not.
Use `COMMAND --help` for options. Invalid arguments, connection or operation
failures return exit status 2 with a diagnostic on stderr that omits driver
output and credentials. Successful commands return exit status 0.
