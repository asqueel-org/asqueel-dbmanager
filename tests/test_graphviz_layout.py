"""Native coordinates respect browser card sizes and remain optional."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from asqueel_dbmanager import graphviz_layout as layout
from asqueel_dbmanager.cytoscape_view import interactive_viewer


@pytest.fixture
def graph():
    return {'nodes': [
        {'data': {'id': 'child', 'name': 'public.child', 'columns': [
            {'name': 'parent_id', 'dtype': 'integer', 'flags': ['FK']},
            {'name': 'description', 'dtype': 'text', 'flags': []}]}},
        {'data': {'id': 'parent', 'name': 'public.parent', 'columns': [
            {'name': 'id', 'dtype': 'integer', 'flags': []}]}},
        {'data': {'id': 'isolated', 'name': 'public.isolated', 'columns': []}},
    ], 'edges': [{'data': {'source': 'child', 'target': 'parent',
                          'columns': ['parent_id'], 'related_columns': ['id']}}]}


@pytest.fixture(autouse=True)
def clear_cache():
    layout._positions.cache_clear()
    yield
    layout._positions.cache_clear()


@pytest.mark.parametrize('direction', ['LR', 'TB'])
def test_native_positions_respect_direction_and_do_not_overlap(graph, direction):
    sizes = layout.card_sizes(graph)
    positions = layout.graphviz_positions(graph, sizes, direction)
    assert positions is not None
    assert set(positions) == set(sizes)
    axis = 'x' if direction == 'LR' else 'y'
    assert positions['child'][axis] < positions['parent'][axis]
    ids = list(positions)
    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            dx = abs(positions[left]['x'] - positions[right]['x'])
            dy = abs(positions[left]['y'] - positions[right]['y'])
            assert (dx >= (sizes[left]['width'] + sizes[right]['width']) / 2
                    or dy >= (sizes[left]['height'] + sizes[right]['height']) / 2)


def test_geometry_measures_all_columns_and_caps_height(graph):
    sizes = layout.card_sizes(graph)
    assert sizes['parent']['height'] == 80
    assert sizes['child']['height'] == 104
    assert sizes['isolated']['height'] == 80
    graph['nodes'][0]['data']['columns'].extend([
        {'name': 'long_unkeyed_column_name_' + str(i), 'dtype': 'text', 'flags': []}
        for i in range(40)
    ])
    capped = layout.card_sizes(graph)
    assert capped['child']['height'] == 416
    assert capped['child']['width'] > sizes['child']['width']
    assert capped['child']['nameWidth'] >= len('long_unkeyed_column_name_39') * 7.5 + 20


@pytest.mark.parametrize('failure', [FileNotFoundError(), OSError(),
                                   subprocess.TimeoutExpired('dot', 10)])
def test_unavailable_native_layout_keeps_viewer_usable(graph, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(layout.subprocess, 'run', fail)
    content, _ = interactive_viewer({'graph': graph, 'direction': 'LR', 'title': 'test'}, 'page')
    config = json.loads(content.split('type="application/json">')[1].split('</script>')[0])
    assert config['graphvizPositions'] is None
    assert config['cardSizes']['child']['height'] == 104


@pytest.mark.parametrize('output,code', [('private diagnostic', 1), ('node n0 nan 1', 0),
                                       ('node n0', 0), ('', 0)])
def test_bad_native_output_falls_back(graph, monkeypatch, output, code):
    monkeypatch.setattr(layout.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(stdout=output, returncode=code))
    assert layout.graphviz_positions(graph, layout.card_sizes(graph), 'LR') is None


def test_dot_contains_only_generated_identifiers_and_dimensions(graph, monkeypatch):
    graph['nodes'][0]['data']['name'] = '"; evil [image="/private/file"];'
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs['input'])
        return SimpleNamespace(returncode=0, stdout='node n0 1 1\nnode n1 3 1\nnode n2 5 1\n')
    monkeypatch.setattr(layout.subprocess, 'run', run)
    sizes = layout.card_sizes(graph)
    assert layout.graphviz_positions(graph, sizes, 'LR')
    assert layout.graphviz_positions(graph, sizes, 'LR')
    assert len(calls) == 1
    assert 'evil' not in calls[0] and '/private/file' not in calls[0]
