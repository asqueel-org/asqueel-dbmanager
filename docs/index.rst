Asqueel DB Manager
==================

.. image:: ../assets/branding/asqueel-dbmanager-primary.svg
   :alt: Asqueel DB Manager
   :width: 360px

A PostgreSQL administration service for reviewed schema migrations,
backups and restores, with REST and MCP access through Kajenn. Version 0.2.0
also includes a Gramlot workbench, interactive database
diagrams and natural-language query sessions. Install the optional
extras from PyPI to enable the Gramlot UI and AI query workflows.

Start with the installation guide and the workbench's English **Getting started**
page. Register a database, explore its structure, then choose maintenance or AI
enrollment. The workbench guide documents beta functionality and its limits.
Legacy job endpoints remain documented separately; jobs are outside the current
workbench scope.

.. toctree::
   :maxdepth: 2
   :caption: Get started

   guide/overview
   guide/availability
   guide/release-notes
   guide/installation

.. toctree::
   :maxdepth: 2
   :caption: Use DB Manager

   guide/workbench
   guide/migrations
   guide/cli
   guide/diagrams
   guide/queries
   guide/backups
   guide/jobs

.. toctree::
   :maxdepth: 2
   :caption: Reference and maintenance

   guide/code-guide
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
