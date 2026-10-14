"""Experimental Cytoscape graph adapter; the Graphviz renderer stays independent."""

import html
import json
from importlib.resources import files

from .diagrams import _select
from .graphviz_layout import card_sizes, graphviz_positions
from .operations import normalize

ASSETS = {
    'cytoscape-3.34.3.min.js': 'text/javascript',
    'cytoscape-LICENSE.txt': 'text/plain',
    'cytoscape-view.js': 'text/javascript',
    'cytoscape-view.css': 'text/css',
}


def asset(name):
    return files('asqueel_dbmanager').joinpath('static', name).read_text(encoding='utf-8')


def graph_data(structure, **filters):
    root = _select(normalize(structure)['root'], **filters)
    tables = {(s, t): table for s, schema in sorted(root['schemas'].items())
              for t, table in sorted(schema['tables'].items())}
    ids = {key: f'table_{index}' for index, key in enumerate(tables)}
    nodes, edges = [], []
    for key, table in tables.items():
        pk = set((table['attributes'].get('pkeys') or '').split(','))
        fk = {c for rel in table['relations'].values() for c in rel['attributes']['columns']}
        columns = []
        for name, column in table['columns'].items():
            attrs = column['attributes']
            dtype = attrs.get('sql_type') or attrs.get('dtype') or '?'
            if not attrs.get('sql_type') and attrs.get('size'):
                dtype = f'{dtype}({attrs["size"]})'
            flags = [flag for flag, enabled in [('PK', name in pk), ('FK', name in fk),
                     ('UQ', attrs.get('unique')), ('NOT NULL', name in pk or attrs.get('notnull'))]
                     if enabled]
            columns.append({'name': name, 'dtype': dtype, 'flags': flags})
        nodes.append({'data': {'id': ids[key], 'name': f'{key[0]}.{key[1]}',
                               'schema': key[0], 'columns': columns}})
        for _, relation in sorted(table['relations'].items()):
            attrs = relation['attributes']
            target = (attrs['related_schema'], attrs['related_table'])
            if target in ids:
                edges.append({'data': {'id': f'fk_{len(edges)}', 'source': ids[key],
                                      'target': ids[target], 'columns': list(attrs['columns']),
                                      'related_columns': list(attrs['related_columns'])}})
    return {'nodes': nodes, 'edges': edges}


def interactive_viewer(snapshot, page_id):
    graph, direction = snapshot['graph'], snapshot['direction']
    sizes = card_sizes(graph)
    positions = graphviz_positions(graph, sizes, direction)
    config = json.dumps({'graph': snapshot['graph'], 'pageId': page_id,
                         'direction': direction, 'cardSizes': sizes,
                         'graphvizPositions': positions},
                        ensure_ascii=True)
    config = config.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    template = files('asqueel_dbmanager').joinpath('static', 'cytoscape-view.html').read_text()
    content = template.replace('__CONFIG__', config, 1).replace('__TITLE__', html.escape(snapshot['title']), 1)
    policy = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
              "img-src data: blob:; base-uri 'none'; frame-ancestors 'none'")
    return content, policy
