"""Side-by-side configuration, live objects and migration JSON trees."""

from asqueel_dbmanager.ui_pages import PageBase, button, field


class Page(PageBase):
    kind = 'asqueel'
    title = 'Asqueel configurations'
    css = ('/workbench.css', '/asqueel.css')

    def content(self, pane):
        pane.p('Inspect registered server-side configurations. Loading runs the trusted Python recipe; credentials are hidden.', class_='muted')
        toolbar = pane.div(class_='toolbar')
        toolbar.select(id='configuration', aria_label='Registered Asqueel configuration').option('Select a configuration', value='')
        button(toolbar, 'Refresh list', 'refresh')
        button(toolbar, 'Load configuration', 'load')
        pane.p('', id='configuration-info', class_='metadata')
        tabs = pane.div(class_='config-tabs', role='tablist', aria_label='Configuration views')
        for key, label in [('objects', 'Configuration & Objects'), ('migration', 'Migration')]:
            button(tabs, label, id=f'tab-{key}', role='tab', aria_selected=str(key == 'objects').lower(),
                   aria_controls=f'panel-{key}', data_tab=key, tabindex=0 if key == 'objects' else -1)
        filters = pane.div(class_='toolbar')
        field(filters, 'Search nodes', 'tree-search', type='search')
        button(filters, 'Reset trees', 'reset-trees')
        objects = pane.section(id='panel-objects', role='tabpanel', aria_labelledby='tab-objects')
        objects.p('Configuration shows static Bag nodes. Objects groups constructed tables under their packages or declared schemas, with columns and relations. Expanding a tree does not run resolvers.', class_='muted')
        self.pair(objects, [('config', 'Configuration Bag'), ('objects', 'Constructed objects')])
        migration = pane.section(id='panel-migration', role='tabpanel', aria_labelledby='tab-migration', hidden=True)
        actions = migration.div(class_='toolbar')
        button(actions, 'Read / refresh comparison', 'compare')
        label = actions.html_label(class_='check')
        label.input(id='only-differences', type='checkbox')
        label.span('Only differences')
        migration.p('Desired only · Database only · Changed. JSON differences are informational; review the migration plan for executable changes.', class_='muted')
        self.pair(migration, [('desired', 'Desired · Asqueel migration JSON'), ('current', 'Current · database JSON')])
        actions = migration.div(class_='toolbar')
        label = actions.html_label(class_='check')
        label.input(id='allow-removals', type='checkbox')
        label.span('Allow supported removals')
        button(actions, 'Preview migration plan', 'plan')
        migration.section(id='migration-plan', aria_label='Migration plan')
        field(migration, 'Type the configuration name to confirm applying the reviewed plan', 'confirm-configuration')
        button(migration, 'Apply reviewed plan', 'apply', disabled=True)

    @staticmethod
    def pair(parent, entries):
        pair = parent.div(class_='tree-pair')
        for key, title in entries:
            panel = pair.section(class_='tree-panel')
            panel.h2(title)
            panel.div(id=f'tree-{key}', class_='tree-view', aria_label=title)
            panel.pre('Select a node to inspect its details.', id=f'detail-{key}', class_='node-detail',
                      tabindex=0, aria_label=f'{title} node details')
