"""Native HTML pages authored with Gramlot; no experimental components."""

from gramlot import Page as GramlotPage

NAVIGATION = (
    ('Start here', (('home', 'Getting started'),)),
    ('Registration', (('databases', 'Databases'), ('genropy', 'Genropy legacy instances'),
                      ('asqueel', 'Asqueel configurations'))),
    ('Operations', (('diagram', 'Database diagram'), ('migrations', 'Migrations'),
                    ('backups', 'Backup & restore'))),
    ('AI Queries', (('enrollment', 'Database enrollment'), ('guide', 'Database Guide'), ('chat', 'Chat'))),
)


def field(parent, label, name, *, type='text', required=False, value=None):
    item = parent.html_label(class_='field')
    item.span(label)
    attrs = {'name': name, 'id': name, 'type': type, 'required': required}
    if value is not None:
        attrs['value'] = value
    return item.input(**attrs)


def button(parent, label, action=None, **attrs):
    return parent.button(label, type='button', data_action=action, **attrs)


def database_choice(parent, name='database', label='Database'):
    row = parent.div(class_='toolbar')
    item = row.html_label(class_='field')
    item.span(label)
    item.select(name=name, id=name, data_databases='true').option('Select a database', value='')
    button(row, 'Refresh', 'refresh')


class PageBase(GramlotPage):
    css = ('/workbench.css',)
    kind = ''
    title = 'DB Manager'

    def main(self, root):
        pane = root.main(id='workbench', class_='page', data_page=self.kind)
        header = pane.header(class_='page-header')
        header.div('DB MANAGER', class_='eyebrow')
        header.h1(self.title)
        self.content(pane)
        pane.p('', id='status', role='status', aria_live='polite')
        pane.section(id='result', aria_label='Operation result')
        pane.dataController(func='start', _onStart=True)

    def content(self, pane):
        if self.kind in {'databases', 'genropy'}:
            pane.p('Register a connection in the encrypted local catalog. AI enrollment is a separate step.', class_='muted')
            pane.section(id='database-list', class_='card')
            form = pane.form(id='registration', class_='card')
            form.h2('Register database' if self.kind == 'databases' else 'Register Genropy legacy instance')
            field(form, 'Profile name', 'profile', required=True)
            if self.kind == 'genropy':
                field(form, 'Instance name', 'instance', required=True)
                form.p('Uses the Genropy configuration installed on this server. Imports the primary PostgreSQL connection.', class_='muted')
            else:
                fields = form.div(class_='fields')
                for name, label, value in [('host', 'Host', 'localhost'), ('port', 'Port', '5432'),
                                           ('dbname', 'Database name', None), ('user', 'User', None)]:
                    field(fields, label, name, required=name == 'dbname', value=value)
                field(form, 'Password', 'password', type='password')
            form.p('The storage key must already be configured (1Password or server environment). Existing profiles are never overwritten.', class_='muted')
            form.button('Check & register', type='submit')
        elif self.kind == 'diagram':
            row = pane.div(class_='toolbar diagram-toolbar')
            row.select(id='database', data_databases='true', aria_label='Database').option('Select a database', value='')
            button(row, '↻', 'refresh', title='Refresh database list', aria_label='Refresh database list')
            button(row, 'Draw / refresh', 'diagram')
            row.a('Full page ↗', id='diagram-link', target='_blank', rel='noopener', hidden=True)
            pane.p('', id='diagram-info', class_='metadata')
            pane.iframe(id='database-diagram', title='Database tables and relationships',
                        class_='database-diagram', hidden=True)
            details = pane.details(id='index-details', class_='card', hidden=True)
            details.summary('Keys, indexes and constraints')
            item = details.html_label(class_='field')
            item.span('Table')
            item.select(id='index-table')
            details.div(id='table-indexes')
        elif self.kind == 'migrations':
            database_choice(pane)
            pane.p('Read the current structure or review a target Migration JSON before applying changes.', class_='muted')
            actions = pane.div(class_='toolbar')
            button(actions, 'Read structure', 'introspect')
            field(pane, 'Load target JSON', 'structure-file', type='file')
            pane.textarea(id='structure', rows=12, placeholder='Paste target Migration JSON', aria_label='Target structure')
            label = pane.html_label(class_='check')
            label.input(type='checkbox', id='allow-removals')
            label.span('Allow removals in the migration plan')
            button(pane, 'Preview migration plan', 'plan')
            pane.section(id='plan-result')
            field(pane, 'Type the profile name to confirm applying the reviewed plan', 'confirm-apply')
            button(pane, 'Apply reviewed plan', 'apply', disabled=True, id='apply')
        elif self.kind == 'backups':
            database_choice(pane, label='Source database')
            actions = pane.div(class_='toolbar')
            button(actions, 'Create backup', 'backup')
            button(actions, 'List backups', 'backups')
            pane.section(id='backup-list')
            pane.h2('Restore into an existing empty database')
            pane.p('Only archives created here for the selected source profile are listed. Restore never overwrites a populated database.', class_='muted')
            field(pane, 'Backup ID', 'backup-id')
            database_choice(pane, 'destination', 'Destination database')
            field(pane, 'Type the destination profile name to confirm', 'confirm-restore')
            button(pane, 'Restore backup', 'restore')
        elif self.kind in {'enrollment', 'guide'}:
            database_choice(pane)
            pane.p('First beta: manually review structure, descriptions and privacy. Only structure and approved descriptions go to the model. Result analysis, automatic suggestions, lookup loading and database_stats are not enabled yet.', class_='notice')
            actions = pane.div(class_='toolbar')
            button(actions, 'Read / refresh structure', 'prepare')
            button(actions, 'Load guide', 'guide')
            pane.p('', id='guide-status', class_='muted')
            pane.html_label('Database explanations for the model', for_='guide-notes')
            pane.textarea(id='guide-notes', rows=4, placeholder='Describe business rules and ambiguities. Do not include confidential values.')
            pane.div(id='guide-tables')
            actions = pane.div(class_='toolbar')
            button(actions, 'Save draft', 'save-draft')
            button(actions, 'Confirm enrollment', 'approve')
            pane.p('Privacy settings are stored for future result encoding. This beta never sends query result rows to the model.', class_='muted')
        elif self.kind == 'chat':
            database_choice(pane)
            actions = pane.div(class_='toolbar')
            button(actions, 'Open session', 'open-session')
            button(actions, 'Close session', 'close-session', disabled=True, id='close-session')
            pane.p('', id='session-status', class_='muted')
            pane.section(id='conversation', aria_live='polite')
            form = pane.form(id='ask', class_='card')
            form.html_label('Your question', for_='question')
            form.textarea(id='question', rows=3, required=True, placeholder='Which states have customers?')
            mode = form.html_label(class_='field')
            mode.span('Output')
            select = mode.select(id='output')
            select.option('Results (read only)', value='results')
            select.option('SQL only', value='sql')
            form.button('Ask', type='submit', id='ask-button', disabled=True)
            pane.p('Up to 100 rows per answer. Rows remain local; subsequent model calls receive questions and SQL, not results.', class_='muted')


class ShellPage(GramlotPage):
    title = 'DB Manager'
    css = ('/workbench.css',)

    def main(self, root):
        shell = root.div(id='workbench', class_='shell', data_page='shell')
        sidebar = shell.aside(class_='sidebar')
        button(sidebar, '☰', id='navigation-toggle', aria_label='Toggle navigation',
               aria_expanded='true', title='Show / hide navigation')
        sidebar.div('ASQUEEL', class_='eyebrow')
        sidebar.h1('DB Manager')
        sidebar.p('Gramlot beta', class_='badge')
        nav = sidebar.nav(aria_label='Main navigation')
        for title, entries in NAVIGATION:
            group = nav.details(open=True)
            group.summary(title)
            links = group.ul()
            for key, label in entries:
                links.li().a(label, href=key, target='workspace', data_page_link=key,
                             aria_current='page' if key == 'home' else None)
        sidebar.footer('HTML first · REST / MCP services')
        area = shell.main(id='frames', class_='frames')
        area.iframe(src='home', name='workspace', id='frame-home', title='Getting started')
        shell.dataController(func='start', _onStart=True)
