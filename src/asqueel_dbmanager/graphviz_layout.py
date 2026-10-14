"""Optional native layout for Cytoscape cards, without rendering their content."""

import math
import subprocess
from functools import lru_cache

MAX_CARD_ROWS = 15


def card_sizes(graph):
    """Stable card footprint in pixels, with room for at most fifteen visible rows.

    Always measure all columns: filtering keys must not resize the layout.
    """
    sizes = {}
    for node in graph['nodes']:
        data = node['data']
        columns = data['columns']
        name_width = max([100] + [len(c['name']) * 7.5 + 20 for c in columns])
        type_width = max([65] + [len(c['dtype']) * 7.5 + 20 for c in columns])
        flags_width = max([75] + [len(' '.join(c['flags'])) * 7.5 + 20 for c in columns])
        sizes[data['id']] = {
            'nameWidth': name_width, 'typeWidth': type_width,
            'width': max(name_width + type_width + flags_width + 16, len(data['name']) * 8 + 28),
            'height': 56 + min(MAX_CARD_ROWS, max(1, len(columns))) * 24,
        }
    return sizes


@lru_cache(maxsize=16)
def _positions(source):
    # Cache successful geometry only; a missing/broken executable is retried next time.
    result = subprocess.run(['dot', '-Tplain'], input=source, capture_output=True,
                            text=True, encoding='utf-8', timeout=10, check=False)
    if result.returncode:
        raise ValueError('Graphviz layout failed')
    positions = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == 'node':
            x, y = float(fields[2]) * 72, -float(fields[3]) * 72
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('Invalid Graphviz coordinates')
            positions[fields[1]] = {'x': x, 'y': y}
    return positions


def graphviz_positions(graph, sizes, direction):
    """Return positions, or None when native layout is unavailable or fails."""
    if not graph['nodes']:
        return None
    # Generated identifiers and numeric dimensions only: schema labels never enter DOT.
    ids = {node['data']['id']: f'n{i}' for i, node in enumerate(graph['nodes'])}
    lines = ['digraph layout {',
             f'graph [rankdir={"TB" if direction == "TB" else "LR"}, '
             'nodesep=0.5, ranksep=1.2, pack=true, packmode="array"];',
             'node [shape=box, fixedsize=true, label="", margin=0];']
    for node_id, dot_id in ids.items():
        size = sizes[node_id]
        lines.append(f'{dot_id} [width={size["width"] / 72}, height={size["height"] / 72}];')
    for edge in graph['edges']:
        data = edge['data']
        lines.append(f'{ids[data["source"]]} -> {ids[data["target"]]};')
    lines.append('}')
    try:
        positions = _positions('\n'.join(lines))
        return {node_id: positions[dot_id] for node_id, dot_id in ids.items()}
    except (OSError, UnicodeError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
        return None
