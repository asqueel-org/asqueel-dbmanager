# Development and releases

```bash
python -m pip install -e '.[dev,postgresql]'
ruff check src tests
pytest
python -m build
```

PostgreSQL tests use an ephemeral `testing.postgresql` server, or the server
configured by `GNR_TEST_PG_HOST`, `GNR_TEST_PG_PORT`, `GNR_TEST_PG_USER` and
`GNR_TEST_PG_PASSWORD`. They create uniquely named temporary databases and remove
them afterward. OpenAPI, MCP, native task execution, stale plans, migrations and
backup/restoration of row data are covered.

Next extensions: additional database backends, authenticated remote deployment,
archive retention and maintenance utilities. They belong to this manager;
schema comparison and dialect SQL remain in the migration engine.

## Build the manual

The manual uses Sphinx, MyST Markdown and the Read the Docs theme, with the
shared Asqueel branding. Install its dependencies and build with warnings as
errors:

```bash
python -m pip install -e '.[docs]'
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` in a browser. GitHub Actions runs the same
strict build and saves an HTML artifact. PostgreSQL is not needed to build the
manual. Only `index.rst` and `guide/` are published; local design notes elsewhere
in `docs/` are outside the public manual and source distribution.

## Read the Docs

The repository's `.readthedocs.yaml` selects Ubuntu 24.04, Python 3.12,
`docs/conf.py` and the `docs` installation extra. Warnings fail the build.

To connect a new project, add `asqueel-org/asqueel-dbmanager` in the
[Read the Docs dashboard](https://app.readthedocs.org/dashboard/) with project
slug `asqueel-dbmanager`, language English and default branch `main`. Connect
the repository integration so pushes trigger builds. Build the `latest` version;
its public URL is `https://asqueel-dbmanager.readthedocs.io/en/latest/`.
If using manual import, configure the webhook shown in the project's Integrations
page. See the [official project setup guide](https://docs.readthedocs.com/platform/stable/intro/add-project.html).

Release tag `v0.1.0` predates this manual. Keep documentation on `latest` until a
new release includes these files; do not select that older tag for a docs build.

## Package compatibility and publishing

The manager uses the published migration engine 0.2 series. Asqueel 0.5.2 accepts
that engine while retaining its direct migration API. Installations resolve
packages from PyPI; no source-revision dependency is required.

Release tags must match `pyproject.toml`. The publishing workflow validates
wheel and source archives, checks clean installations of both and publishes via
PyPI Trusted Publishing. The publisher uses GitHub owner `asqueel-org`, repository
`asqueel-dbmanager`, workflow `publish.yml` and environment `release`.
