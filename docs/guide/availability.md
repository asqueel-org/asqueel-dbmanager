# Availability and development preview

This manual covers both the published core and a development preview. Publishing
the manual does not release the preview implementation.

## Published core

The public application provides PostgreSQL connection checks and introspection,
reviewed migration plans and application, logical backup archives, archive
verification, and restore into an existing empty database. It exposes REST,
OpenAPI and MCP over HTTP and runs as a standalone Kajenn application. Legacy
job submission and polling are also present.

The basic PyPI installation in [installation](installation.md) applies to this
core. It is intended for trusted local callers.

## Development preview documented here

At this documentation publication, the following implementation exists in a local
development checkout and has not been published to the default GitHub branch or
released on PyPI:

- Gramlot web workbench and its English Getting started page.
- Encrypted database profiles and Genropy legacy registration.
- Diagram generation, Graphviz layout and interactive Cytoscape viewers.
- CLI introspection, diagrams and backup with Genropy instance selection.
- AI query sessions, manual enrollment and database guide editing.
- Explicit Kajenn-hosted identity and profile access checks.

The [workbench](workbench.md), [CLI](cli.md), [diagrams](diagrams.md) and
[query sessions](queries.md) guides document that preview. Commands using
`--ui`, the `ui`/`queries` extras or the new subcommands require a checkout that
contains their implementation. A fresh clone of the public branch or a PyPI
installation does not yet supply them. Other guides mark sections or additions
that describe preview behavior.

These pages describe implemented beta behavior, not a promise of production
readiness. Update this availability page when the corresponding code is published
and again when a package release makes it installable from PyPI.

## Planned, not implemented in the preview

Automatic database explanations, Genropy package help import, lookup loading,
`database_stats`, privacy-aware result encoding/decoding, AI charts and WAL/PITR
orchestration remain future work. Privacy choices are stored, but result rows are
not sent to the model in the current beta. Jobs are outside the new workbench scope.
