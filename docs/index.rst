Asqueel DB Manager
==================

.. image:: ../assets/branding/asqueel-dbmanager-primary.svg
   :alt: Asqueel DB Manager
   :width: 360px

A local PostgreSQL administration service for reviewed schema migrations,
backups and restores. Kajenn exposes the same typed operations as REST endpoints
and MCP tools, and runs background jobs through its native task executor.

Start with the installation guide, inspect your database, then review a migration
plan before applying it. Backup and restore guides cover both direct calls and
queued jobs.

.. toctree::
   :maxdepth: 2
   :caption: Get started

   guide/overview
   guide/installation

.. toctree::
   :maxdepth: 2
   :caption: Use DB Manager

   guide/migrations
   guide/backups
   guide/jobs

.. toctree::
   :maxdepth: 2
   :caption: Reference and maintenance

   guide/api
   guide/deployment
   guide/development

Related projects
----------------

* `Asqueel <https://asqueel.readthedocs.io/en/latest/>`_: application models,
  database access and queries.
* `Asqueel Migration <https://asqueel-migration.readthedocs.io/en/latest/>`_:
  schema comparison and dialect-specific migration SQL.
* `Source and issues <https://github.com/asqueel-org/asqueel-dbmanager>`_.
