"""Offline rendering, schema semantics and CLI/REST/MCP contracts."""

import copy
import json
import shutil
import subprocess
from xml.etree import ElementTree as ET

import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request

from asqueel_dbmanager import diagrams
from asqueel_dbmanager.__main__ import main


@pytest.fixture
def structure():
    return JsonStructureProducer({'db': 'Shop', 'schemas': [
        {'name': 'public', 'tables': [
            {'name': 'customers', 'pkey': 'region,id', 'columns': [
                {'name': 'region', 'dtype': 'T'}, {'name': 'id', 'dtype': 'I'},
                {'name': 'name', 'dtype': 'T'},
            ]},
            {'name': 'standalone', 'columns': [{'name': 'value', 'dtype': 'T'}]},
        ]},
        {'name': 'sales', 'tables': [
            {'name': 'orders', 'pkey': 'id', 'columns': [
                {'name': 'id', 'dtype': 'I'}, {'name': 'region', 'dtype': 'T'},
                {'name': 'customer_id', 'dtype': 'I'}, {'name': 'parent_id', 'dtype': 'I'},
            ], 'relations': [
                {'columns': ['region', 'customer_id'], 'related_schema': 'public',
                 'related_table': 'customers', 'related_columns': ['region', 'id']},
                {'columns': ['parent_id'], 'related_schema': 'sales',
                 'related_table': 'orders', 'related_columns': ['id']},
            ]},
        ]},
    ]}).get_json_struct()


def test_dot_preserves_composite_keys_cross_schema_and_self_relation(structure, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('DOT export must not run a subprocess')
    monkeypatch.setattr(diagrams.subprocess, 'run', forbidden)
    before = copy.deepcopy(structure)
    result = diagrams.diagram(structure, 'dot')
    assert structure == before
    assert result['tables'] == 3 and result['relations'] == 2
    assert 'public.standalone' in result['content']
    assert '(region, customer_id) → (region, id)' in result['content']
    assert '(parent_id) → (id)' in result['content']
    assert result['content'].count('PK NOT NULL') == 3
    assert diagrams.diagram(json.dumps(structure), 'dot') == result


@pytest.mark.parametrize('change', ['target', 'arity', 'version', 'shape'])
def test_invalid_schema_is_rejected_before_render(structure, monkeypatch, change):
    from asqueel_migration.exceptions import SqlValidationError
    rel = next(iter(structure['root']['schemas']['sales']['tables']['orders']['relations'].values()))
    if change == 'target':
        rel['attributes']['related_table'] = 'absent'
    elif change == 'arity':
        rel['attributes']['related_columns'] = ['id']
    elif change == 'version':
        structure['format_version'] = '99.0'
    else:
        structure['root']['schemas'] = []
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid input must not reach Graphviz')
    monkeypatch.setattr(diagrams.subprocess, 'run', forbidden)
    with pytest.raises((ValueError, SqlValidationError)):
        diagrams.diagram(structure)


@pytest.mark.parametrize('format,direction', [('png', 'LR'), ('dot', 'arbitrary')])
def test_invalid_options(structure, format, direction):
    with pytest.raises(ValueError):
        diagrams.diagram(structure, format, direction)


@pytest.mark.skipif(shutil.which('dot') is None, reason='SVG integration requires Graphviz')
def test_real_svg_includes_tables_columns_and_relations(structure):
    assert diagrams.diagram_capabilities() == {
        'capabilities': {'graphviz': True}, 'diagram_formats': ['dot', 'svg'],
    }
    result = diagrams.diagram(structure)
    svg = ET.fromstring(result['content'])
    assert svg.tag == '{http://www.w3.org/2000/svg}svg'
    text = ' '.join(svg.itertext())
    for label in ('public.customers', 'sales.orders', 'public.standalone', 'customer_id',
                  '(region, customer_id) → (region, id)', 'PK NOT NULL'):
        assert label in text
    ns = {'s': 'http://www.w3.org/2000/svg'}
    assert len(svg.findall('.//s:g[@class="edge"]', ns)) == 2


@pytest.mark.skipif(shutil.which('dot') is None, reason='SVG integration requires Graphviz')
def test_labels_are_text_not_markup_or_graphviz_commands():
    name = '日本語 <script>alert("x")</script> & \\N'
    value = JsonStructureProducer({'db': name, 'schemas': [{'name': name, 'tables': [
        {'name': name, 'columns': [{'name': name, 'dtype': 'T'}]},
    ]}]}).get_json_struct()
    svg = ET.fromstring(diagrams.diagram(value)['content'])
    assert name in ' '.join(svg.itertext())
    assert not any(node.tag.rsplit('}', 1)[-1] in {'script', 'image', 'a'} for node in svg.iter())


def test_empty_schema_is_a_valid_diagram():
    structure = JsonStructureProducer({'db': 'empty', 'schemas': []}).get_json_struct()
    result = diagrams.diagram(structure, 'dot', 'TB')
    assert result['tables'] == result['relations'] == 0
    assert 'No tables' in result['content'] and 'rankdir=TB' in result['content']


@pytest.mark.parametrize('failure,message', [
    ('missing', 'install dot'), ('timeout', '30-second'), ('error', 'could not render'),
])
def test_renderer_failures_are_actionable_without_reflecting_input(structure, monkeypatch, failure, message):
    def run(*args, **kwargs):
        if failure == 'missing':
            raise FileNotFoundError()
        if failure == 'timeout':
            raise subprocess.TimeoutExpired('dot', 30, stderr='private-value')
        return subprocess.CompletedProcess(args[0], 1, '', 'private-value')
    monkeypatch.setattr(diagrams.subprocess, 'run', run)
    with pytest.raises(diagrams.DiagramRenderError, match=message) as error:
        diagrams.diagram(structure)
    assert 'private-value' not in str(error.value)


def test_rest_and_mcp_generate_same_diagram(server, structure):
    args = {'structure': structure, 'format': 'dot'}
    status, body = _request(server, '/diagram', method='POST', payload=args)
    expected = json.loads(body)
    assert status == 200 and expected['tables'] == 3
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'diagram', 'arguments': args},
    })
    response = json.loads(body)
    assert status == 200 and 'error' not in response
    content = response['result']['content']
    assert json.loads(content[0]['text']) == expected


def test_rest_renderer_missing_is_503(server, structure, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(diagrams.subprocess, 'run', missing)
    status, body = _request(server, '/diagram', method='POST', payload={'structure': structure})
    assert status == 503 and b'install dot' in body


def test_cli_files_stdin_stdout_and_existing_output(structure, tmp_path, capsys, monkeypatch):
    import io
    source = tmp_path / 'schema.json'
    source.write_text(json.dumps(structure))
    output = tmp_path / 'schema.dot'
    main(['diagram', str(source), '--format', 'dot', '-o', str(output)])
    expected = output.read_text()
    assert expected.startswith('digraph schema')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(structure)))
    main(['diagram', '-', '--format', 'dot'])
    assert capsys.readouterr().out == expected
    with pytest.raises(SystemExit) as error:
        main(['diagram', str(source), '--format', 'dot', '-o', str(output)])
    assert error.value.code == 2 and output.read_text() == expected


def test_cli_invalid_input_does_not_create_output(tmp_path, capsys):
    source = tmp_path / 'invalid.json'
    source.write_text('private-invalid-input')
    target = tmp_path / 'diagram.svg'
    with pytest.raises(SystemExit) as error:
        main(['diagram', str(source), '-o', str(target)])
    assert error.value.code == 2 and not target.exists()
    assert 'private-invalid-input' not in capsys.readouterr().err


def test_legacy_server_cli(monkeypatch):
    from asqueel_dbmanager import __main__ as cli
    calls = []
    class Server:
        def __init__(self, **kwargs):
            pass

        def serve(self, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(cli, 'AsgiServer', Server)
    main(['--port', '8123'])
    assert calls == [{'host': '127.0.0.1', 'port': 8123}]
