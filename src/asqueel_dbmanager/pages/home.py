"""English operating instructions for the current workbench beta."""

from asqueel_dbmanager.ui_pages import PageBase


def section(parent, anchor, title, introduction, steps=()):
    block = parent.section(id=anchor, class_='help-section')
    block.h2(title)
    block.p(introduction)
    if steps:
        items = block.ol()
        for step in steps:
            items.li(step)
    return block


class Page(PageBase):
    kind = 'home'
    title = 'Getting started'

    def content(self, pane):
        pane.p('Your guide to registering databases, exploring their structure, '
               'reviewing migrations, managing backups and asking questions in natural language.',
               class_='help-lead')
        pane.p('Start with registration. Diagrams and maintenance need a registered profile; '
               'AI Chat also needs a reviewed database guide and confirmed enrollment.', class_='notice')
        toc = pane.nav(aria_label='On this page', class_='help-toc')
        for anchor, label in [('access', 'Before you start'), ('registration', 'Register a database'),
                              ('genropy', 'Genropy legacy'), ('diagram', 'Database diagram'),
                              ('migrations', 'Migrations'), ('backups', 'Backup & restore'),
                              ('enrollment', 'AI enrollment'), ('chat', 'AI Chat'),
                              ('troubleshooting', 'Troubleshooting'), ('documentation', 'Documentation')]:
            toc.a(label, href=f'#{anchor}')

        section(pane, 'access', '1. Before you start',
                'Use the navigation menu to open a workspace. Open pages are retained while you switch '
                'sections. The ☰ button shows or hides navigation; Getting started brings you back here.', [
                    'Local mode is intended for a trusted personal machine. It accepts localhost access '
                    'and does not show a separate login form.',
                    'When hosted by Kajenn, sign in through the host. Your identity determines which '
                    'database profiles you can access. Registration, migration application, backup and '
                    'restore require the dbmanager_admin tag.',
                    'The operator must configure the encrypted catalog key through 1Password or the '
                    'server environment before registering profiles. PostgreSQL must be reachable from '
                    'the DB Manager server. AI Chat additionally needs the query dependencies and provider credentials.',
                ])
        section(pane, 'registration', '2. Register a PostgreSQL database',
                'Open Registration → Databases. Registration checks the connection and stores it encrypted '
                'in the local profile catalog. It does not change the database structure.', [
                    'Choose a unique Profile name: this is the logical name used throughout DB Manager.',
                    'Enter Host, Port, Database name, User and Password. The host is resolved from the '
                    'server running DB Manager, not from your browser.',
                    'Click Check & register. The profile appears in Registered profiles and in database selectors.',
                    'Select Refresh in an already open workspace to load newly registered profiles. '
                    'Existing profile names cannot be overwritten from this interface.',
                ])
        section(pane, 'genropy', '3. Register a Genropy legacy instance',
                'Open Registration → Genropy legacy instances when the server has access to your legacy '
                'Genropy installation and instance configuration.', [
                    'Enter a unique Profile name and the existing Instance name.',
                    'Click Check & register. DB Manager resolves the primary PostgreSQL connection, '
                    'checks it and saves an encrypted profile.',
                    'Use that profile in diagrams, migrations, backups and AI enrollment exactly like '
                    'a directly registered database. This beta does not import all stores or package help files.',
                ])
        section(pane, 'diagram', '4. Explore the database diagram',
                'Open Operations → Database diagram, select a database and click Draw / refresh. '
                'Migration reads the current structure; no AI enrollment is needed.', [
                    'Navigation collapses to make room for the canvas. Use ☰ to reopen it or Full page ↗ '
                    'to open the viewer separately.',
                    'Fit shows the whole graph; Readable moves to a readable scale. Use + and − to adjust '
                    'zoom, drag table headers to move tables and scroll inside tables with more than 15 columns.',
                    'Expand Filters to select a SQL schema or a Cluster root table. Choose Ancestors, '
                    'Descendants or Both and an optional Depth, then Apply filters. Clear filters restores '
                    'the full snapshot. Related tables follow foreign-key links.',
                    'Expand Layout & export to choose a layout, Reset layout, toggle Keys only, Save '
                    'positions or Download PNG. Graphviz provides the initial layout when installed; '
                    'Cytoscape handles interaction. Saved positions belong to this browser and snapshot.',
                    'Tables / details opens the table list and selection details. Keys, indexes and '
                    'constraints below the viewer shows per-table information reported by Migration.',
                    'Draw / refresh reads the database again and creates a new snapshot. Filtering or '
                    'dragging the existing diagram does not change the database.',
                ])
        section(pane, 'migrations', '5. Review and apply a migration',
                'Open Operations → Migrations. A target Migration JSON describes the desired structure.', [
                    'Choose a database and use Read structure to inspect its current structure.',
                    'Load a target JSON file or paste it into Target structure. Leave Allow removals '
                    'unchecked unless removals are intentional.',
                    'Click Preview migration plan and review its operations and SQL before proceeding.',
                    'To apply, type the selected profile name into the confirmation field and click '
                    'Apply reviewed plan. Changing the target invalidates the reviewed plan. Inspect '
                    'the returned verification result after application.',
                ])
        section(pane, 'backups', '6. Back up and restore a database',
                'Open Operations → Backup & restore. This workspace creates local logical PostgreSQL '
                'database backups. Compatible pg_dump and pg_restore must be installed on the server.', [
                    'Select Source database and click Create backup. List backups shows archives created '
                    'through this workspace for the selected profile.',
                    'For a restore, first prepare an existing empty destination database and register '
                    'it as a separate profile.',
                    'Enter the Backup ID, choose Destination database and type its profile name into '
                    'the confirmation field. Click Restore backup and inspect the result.',
                    'A populated destination is rejected. This workspace does not provide job scheduling, '
                    'WAL archiving or cluster point-in-time recovery.',
                ])
        section(pane, 'enrollment', '7. Prepare the database for AI questions',
                'Registration establishes access. AI enrollment adds a reviewed guide for the model. '
                'In this beta you write and approve the explanations yourself.', [
                    'Open AI Queries → Database enrollment, select a profile and click Read / refresh structure.',
                    'Explain business rules in Database explanations for the model, and describe '
                    'ambiguous tables in their individual sections. Keep confidential values out of these explanations.',
                    'Review table and column privacy settings. Tables default to Hide (H). Columns '
                    'can Inherit, Share or Hide. These choices are stored for future result encoding.',
                    'Save draft to continue later, or Confirm enrollment when the guide is ready for use.',
                    'Use AI Queries → Database Guide and Load guide to revise it later. A detected '
                    'structure change requires refreshing and reviewing the guide again. New sessions '
                    'use the latest approved guide; an already open session keeps its original guide.',
                ])
        section(pane, 'chat', '8. Ask questions in AI Chat',
                'Open AI Queries → Chat and choose an enrolled database.', [
                    'Click Open session. Check the selected database and the session expiry shown on the page.',
                    'Write a question, for example: “Which states have customers?” or “Show the 10 most '
                    'purchased products in Queensland in the last three months.” Specify the intended '
                    'date and business meaning when they could be ambiguous.',
                    'Choose SQL only to inspect generated SQL without running that query, or Results '
                    '(read only) to execute it. Click Ask.',
                    'Review the SQL, parameters and assumptions, not just the displayed rows. Results '
                    'are limited to 100 rows per answer. Ask a follow-up within the same session.',
                    'Click Close session before changing database or when finished. Switching workspace '
                    'pages keeps the session open; reloading the browser is not a way to close it.',
                ]).p('Data sent to the model includes the structure, approved guide explanations, your '
                     'questions and SQL history. Query result rows are not sent to the model in this beta, '
                     'even for fields marked Share. Automated lookup loading, database_stats, result '
                     'analysis and AI-generated charts are not available yet.', class_='notice')
        block = section(pane, 'troubleshooting', '9. If something does not work',
                        'Start with the message shown by the operation. These are the most common checks:')
        for title, text in [
            ('No databases listed', 'Register a profile or click Refresh. In Kajenn mode, check that '
             'the current identity is allowed to use it.'),
            ('Connection or catalog error', 'Check the server’s network access, PostgreSQL settings and '
             'the configured encryption key. If using 1Password, make sure it is available and unlocked.'),
            ('Chat cannot start', 'Confirm enrollment, check provider credentials and refresh a stale '
             'guide. Close an existing session before choosing another database.'),
            ('Diagram looks too small', 'Use Readable or +, filter to a schema or related cluster, '
             'or open Full page. Fit prioritizes seeing every table over readable text.'),
            ('Administrative action disabled', 'In Kajenn mode, ask the host administrator to check '
             'your dbmanager_admin tag and database access.'),
            ('Backup or restore fails', 'Check pg_dump / pg_restore availability and version '
             'compatibility. Confirm that the restore destination already exists and is empty.'),
        ]:
            item = block.details()
            item.summary(title)
            item.p(text)
        block = section(pane, 'documentation', '10. Documentation and this beta',
                        'This interface uses Gramlot core with native HTML controls and iframe workspaces. '
                        'The diagram uses Cytoscape for interaction and Graphviz for optional layout. '
                        'Advanced Gramlot components will be adopted as the framework develops.')
        block.p('The repository manual under docs/guide is the reference for this checkout. '
                'The published Read the Docs manual can lag behind local beta changes.')
        links = block.ul()
        for label, url in [
            ('Published manual', 'https://asqueel-dbmanager.readthedocs.io/en/latest/'),
            ('Source, local documentation and issues', 'https://github.com/asqueel-org/asqueel-dbmanager'),
        ]:
            links.li().a(label, href=url, target='_blank', rel='noopener')
