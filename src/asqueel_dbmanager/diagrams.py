"""Offline schema diagrams: Migration validates the input, Graphviz lays it out."""

import html
import subprocess
from xml.etree import ElementTree

from .operations import normalize


class DiagramRenderError(RuntimeError):
    """The optional Graphviz renderer is unavailable or failed."""


def _render_svg(source, timeout=30):
    try:
        result = subprocess.run(
            ['dot', '-Tsvg'], input=source, capture_output=True,
            text=True, encoding='utf-8', timeout=timeout, check=False,
        )
    except FileNotFoundError:
        raise DiagramRenderError('SVG requires Graphviz: install dot or request format=dot') from None
    except subprocess.TimeoutExpired:
        raise DiagramRenderError(f'Graphviz exceeded the {timeout}-second rendering limit') from None
    except (OSError, UnicodeError):
        raise DiagramRenderError('Graphviz is not usable; check the local installation') from None
    if result.returncode:
        # Renderer diagnostics may quote input; keep them out of public errors.
        raise DiagramRenderError('Graphviz could not render the diagram')
    try:
        root = ElementTree.fromstring(result.stdout)
    except ElementTree.ParseError:
        raise DiagramRenderError('Graphviz did not produce a valid SVG document') from None
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise DiagramRenderError('Graphviz did not produce a valid SVG document')
    return result.stdout


def diagram_capabilities() -> dict:
    """Probe SVG support locally; availability is a snapshot, not a guarantee.

    No schema or database access is needed. Do not cache across calls: PATH or
    the native installation may change while the application is running.
    """
    try:
        _render_svg('digraph capability_probe { probe; }', timeout=2)
    except DiagramRenderError:
        available = False
    else:
        available = True
    return {
        'capabilities': {'graphviz': available},
        'diagram_formats': ['dot', 'svg'] if available else ['dot'],
    }


def _label(value):
    """Escape input as Graphviz HTML text, never as DOT or HTML instructions."""
    text = str(value)
    if any(ord(char) < 32 and char not in '\n\r\t' for char in text):
        raise ValueError('Diagram labels cannot contain control characters')
    return (html.escape(text, quote=True).replace('\\', '&#92;')
            .replace('\n', '&#10;').replace('\r', '&#13;').replace('\t', '&#9;'))


def _select(root, schemas=None, tables=None, cluster=None, relatives='both', depth=None):
    """Select a view of a validated structure; never mutate its table metadata."""
    for values in (schemas, tables):
        if values is not None and (not isinstance(values, list)
                                   or any(not isinstance(item, str) or not item for item in values)):
            raise ValueError('Diagram filters must be lists of names')
    if relatives not in {'both', 'ancestors', 'descendants'}:
        raise ValueError('Invalid relatives direction')
    if depth is not None and (type(depth) is not int or depth < 0):
        raise ValueError('Depth must be a non-negative integer')
    if cluster is None and (depth is not None or relatives != 'both'):
        raise ValueError('Depth and relatives require a cluster table')
    all_tables = {(s, t): table for s, schema in root['schemas'].items()
                  for t, table in schema['tables'].items()}

    def resolve(name):
        if not isinstance(name, str) or not name:
            raise ValueError('A table name is required')
        matches = {key for key in all_tables if f'{key[0]}.{key[1]}' == name}
        if not matches:
            matches = {key for key in all_tables if key[1] == name}
        if len(matches) != 1:
            raise ValueError('Unknown or ambiguous table; use schema.table')
        return next(iter(matches))

    selected = set(all_tables)
    if schemas is not None:
        if set(schemas) - root['schemas'].keys():
            raise ValueError('Unknown schema in diagram filter')
        selected &= {key for key in all_tables if key[0] in schemas}
    if tables is not None:
        selected &= {resolve(name) for name in tables}
    if cluster is not None:
        seed = resolve(cluster)
        parents = {key: set() for key in all_tables}
        children = {key: set() for key in all_tables}
        for key, table in all_tables.items():
            for relation in table['relations'].values():
                attrs = relation['attributes']
                target = (attrs['related_schema'], attrs['related_table'])
                parents[key].add(target)
                children[target].add(key)

        def walk(edges):
            seen, frontier, level = {seed}, {seed}, 0
            while frontier and (depth is None or level < depth):
                frontier = {target for key in frontier for target in edges[key]} - seen
                seen |= frontier
                level += 1
            return seen

        related = {seed}
        if relatives in {'both', 'ancestors'}:
            related |= walk(parents)
        if relatives in {'both', 'descendants'}:
            related |= walk(children)
        selected &= related
    return {**root, 'schemas': {
        name: {**schema, 'tables': {table: value for table, value in schema['tables'].items()
                                  if (name, table) in selected}}
        for name, schema in root['schemas'].items()
    }}


def _dot(root, direction):
    tables = {
        (schema_name, table_name): table
        for schema_name, schema in sorted(root['schemas'].items())
        for table_name, table in sorted(schema['tables'].items())
    }
    identifiers = {key: f'table_{index}' for index, key in enumerate(tables)}
    ports = {key: {name: f'column_{index}' for index, name in enumerate(table['columns'])}
             for key, table in tables.items()}
    lines = [
        'digraph schema {',
        f'  graph [rankdir={direction}, bgcolor="white", pad="0.4", nodesep="0.5",',
        f'         fontname="Helvetica", labelloc="t", label=<{_label(root.get("entity_name", "Schema"))}>];',
        '  node [shape=plain, fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10, color="#64748b", arrowsize=0.7];',
    ]
    for key, table in tables.items():
        pk = set((table['attributes'].get('pkeys') or '').split(','))
        fk = {column for rel in table['relations'].values()
              for column in rel['attributes']['columns']}
        rows = [
            '<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="7" COLOR="#cbd5e1">',
            '<TR><TD COLSPAN="3" PORT="header" BGCOLOR="#17324d">'
            f'<FONT COLOR="white"><B>{_label(key[0])}.{_label(key[1])}</B></FONT></TD></TR>',
        ]
        for name, column in table['columns'].items():
            attrs = column['attributes']
            flags = [flag for flag, enabled in (
                ('PK', name in pk), ('FK', name in fk), ('UQ', attrs.get('unique')),
                ('NOT NULL', name in pk or attrs.get('notnull')),
            ) if enabled]
            dtype = attrs.get('sql_type') or attrs.get('dtype') or '?'
            if not attrs.get('sql_type') and attrs.get('size'):
                dtype = f'{dtype}({attrs["size"]})'
            rows.append(
                f'<TR><TD PORT="{ports[key][name]}" ALIGN="LEFT">{_label(name)}</TD>'
                f'<TD ALIGN="LEFT">{_label(dtype)}</TD>'
                f'<TD PORT="{ports[key][name]}_out" ALIGN="LEFT">{_label(" ".join(flags))}</TD></TR>'
            )
        if not table['columns']:
            rows.append('<TR><TD COLSPAN="3">(no columns)</TD></TR>')
        rows.append('</TABLE>')
        lines.append(f'  {identifiers[key]} [label=<{"".join(rows)}>];')
    relation_count = 0
    for key, table in tables.items():
        for _, relation in sorted(table['relations'].items()):
            attrs = relation['attributes']
            target = (attrs['related_schema'], attrs['related_table'])
            if target not in tables:
                continue  # Boundary foreign keys retain their column flags, but no dangling edge.
            source_columns, target_columns = attrs['columns'], attrs['related_columns']
            if not source_columns or len(source_columns) != len(target_columns):
                raise ValueError('Foreign key columns must have matching lengths')
            source_port = ports[key][source_columns[0]] + '_out' if len(source_columns) == 1 else 'header'
            target_port = ports[target][target_columns[0]] if len(target_columns) == 1 else 'header'
            label = f'({", ".join(source_columns)}) → ({", ".join(target_columns)})'
            lines.append(
                f'  {identifiers[key]}:{source_port}:e -> {identifiers[target]}:{target_port}:w'
                f' [label=<{_label(label)}>];'
            )
            relation_count += 1
    if not tables:
        lines.append('  empty [shape=box, label="No tables"];')
    lines.append('}')
    return '\n'.join(lines) + '\n', len(tables), relation_count


def diagram(structure: dict | str, format: str = 'svg', direction: str = 'LR', *,
            schemas: list[str] | None = None, tables: list[str] | None = None,
            cluster: str | None = None, relatives: str = 'both', depth: int | None = None) -> dict:
    """Render normalized Migration JSON without opening a database connection.

    SVG requires Graphviz's ``dot`` on PATH; DOT source needs only Python.
    Arrows point from referencing columns to referenced columns. They do not
    infer business cardinalities. Composite keys retain their ordered mapping.
    """
    if format not in {'svg', 'dot'}:
        raise ValueError('Diagram format must be svg or dot')
    if direction not in {'LR', 'TB'}:
        raise ValueError('Diagram direction must be LR or TB')
    document = normalize(structure)
    root = _select(document['root'], schemas, tables, cluster, relatives, depth)
    source, table_count, relations = _dot(root, direction)
    content = source
    if format == 'svg':
        content = _render_svg(source)
    return {
        'format': format,
        'media_type': 'image/svg+xml' if format == 'svg' else 'text/vnd.graphviz',
        'content': content, 'tables': table_count, 'relations': relations,
    }
