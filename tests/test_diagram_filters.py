"""Diagram selections follow directed foreign keys and retain boundary FK flags."""

import copy
import io
import json
import re

import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request

from asqueel_dbmanager import __main__ as cli
from asqueel_dbmanager.cytoscape_view import graph_data
from asqueel_dbmanager.diagrams import diagram


@pytest.fixture
def graph():
    links = {
        'geo.country': [], 'crm.customer': ['geo.country'], 'crm.peer': ['geo.country'],
        'billing.invoice': ['crm.customer', 'billing.invoice'],
        'billing.line': ['billing.invoice', 'billing.product'],
        'billing.payment': ['billing.invoice'], 'audit.entry': ['billing.line'],
        'billing.product': [], 'billing.country': [],
    }
    schemas = {}
    for qualified, targets in links.items():
        schema, name = qualified.split('.')
        table = {'name': name, 'pkey': 'id', 'columns': [{'name': 'id', 'dtype': 'I'}], 'relations': []}
        for index, target in enumerate(targets):
            target_schema, target_table = target.split('.')
            column = f'ref{index}'
            table['columns'].append({'name': column, 'dtype': 'I'})
            table['relations'].append({'columns': [column], 'related_schema': target_schema,
                                       'related_table': target_table, 'related_columns': ['id']})
        schemas.setdefault(schema, {'name': schema, 'tables': []})['tables'].append(table)
    return JsonStructureProducer({'db': 'example', 'schemas': list(schemas.values())}).get_json_struct()


def visible(result):
    return set(re.findall(r'<B>(.*?)</B>', result['content']))


def test_schema_and_table_filters_hide_edges_but_keep_fk_metadata(graph):
    before = copy.deepcopy(graph)
    result = diagram(graph, 'dot', schemas=['billing'])
    assert result['tables'] == 5 and result['relations'] == 4
    assert visible(result) == {'billing.invoice', 'billing.line', 'billing.payment',
                               'billing.product', 'billing.country'}
    result = diagram(graph, 'dot', tables=['crm.customer'])
    assert visible(result) == {'crm.customer'} and result['relations'] == 0
    assert '>FK<' in result['content']
    result = diagram(graph, 'dot', schemas=['billing'], tables=['invoice', 'crm.customer'])
    assert visible(result) == {'billing.invoice'}
    assert graph == before


@pytest.mark.parametrize(('options', 'expected'), [
    ({}, {'billing.invoice', 'crm.customer', 'geo.country', 'billing.line', 'billing.payment', 'audit.entry'}),
    ({'depth': 0}, {'billing.invoice'}),
    ({'depth': 1}, {'billing.invoice', 'crm.customer', 'billing.line', 'billing.payment'}),
    ({'depth': 2}, {'billing.invoice', 'crm.customer', 'geo.country', 'billing.line', 'billing.payment', 'audit.entry'}),
    ({'relatives': 'ancestors'}, {'billing.invoice', 'crm.customer', 'geo.country'}),
    ({'relatives': 'descendants'}, {'billing.invoice', 'billing.line', 'billing.payment', 'audit.entry'}),
    ({'schemas': ['billing']}, {'billing.invoice', 'billing.line', 'billing.payment'}),
])
def test_cluster_follows_each_direction_without_sibling_expansion(graph, options, expected):
    result = diagram(graph, 'dot', cluster='billing.invoice', **options)
    assert visible(result) == expected
    assert result['tables'] == len(expected)


def test_cluster_cycles_terminate():
    structure = JsonStructureProducer({'db': 'cycle', 'schemas': [{'name': 'public', 'tables': [
        {'name': name, 'pkey': 'id', 'columns': [{'name': 'id', 'dtype': 'I'}, {'name': 'other', 'dtype': 'I'}],
         'relations': [{'columns': ['other'], 'related_schema': 'public', 'related_table': target,
                        'related_columns': ['id']}]}
        for name, target in [('a', 'b'), ('b', 'a')]
    ]}]}).get_json_struct()
    result = diagram(structure, 'dot', cluster='public.a')
    assert result['tables'] == result['relations'] == 2
    assert visible(result) == {'public.a', 'public.b'}


def test_cytoscape_uses_same_filtered_graph_and_retains_column_metadata(graph):
    data = graph_data(graph, cluster='invoice', depth=1)
    expected = diagram(graph, 'dot', cluster='invoice', depth=1)
    assert {n['data']['name'] for n in data['nodes']} == visible(expected)
    assert len(data['edges']) == expected['relations']
    ids = {n['data']['id'] for n in data['nodes']}
    for edge in data['edges']:
        assert edge['data']['source'] in ids and edge['data']['target'] in ids
        assert len(edge['data']['columns']) == len(edge['data']['related_columns'])
    customer = next(n['data'] for n in data['nodes'] if n['data']['name'] == 'crm.customer')
    assert customer['columns'][0]['flags'] == ['PK', 'NOT NULL']
    assert customer['columns'][1]['flags'] == ['FK']


@pytest.mark.parametrize('options', [
    {'schemas': ['missing']}, {'schemas': 'billing'}, {'tables': ['country']},
    {'tables': ['missing']}, {'cluster': 'missing'}, {'cluster': ''},
    {'cluster': 'invoice', 'depth': -1}, {'cluster': 'invoice', 'depth': True},
    {'cluster': 'invoice', 'relatives': 'unknown'}, {'depth': 1}, {'relatives': 'ancestors'},
])
def test_invalid_filters_fail_explicitly(graph, options):
    with pytest.raises(ValueError):
        diagram(graph, 'dot', **options)


def test_cli_filters_file_and_published_diagrams(graph, tmp_path, monkeypatch, capsys):
    path = tmp_path / 'structure.json'
    path.write_text(json.dumps(graph))
    cli.main(['diagram', str(path), '--cluster', 'invoice', '--depth', '1', '--format', 'dot'])
    assert 'audit.entry' not in capsys.readouterr().out
    calls = []

    def publish(request, timeout):
        calls.append(json.loads(request.data))
        return io.BytesIO(b'{"url":"/diagrams/example"}')

    monkeypatch.setattr(cli, 'urlopen', publish)
    cli.main(['diagram', str(path), '--cluster', 'invoice', '--relatives', 'ancestors',
              '--depth', '2', '--schema', 'crm', '--table', 'customer',
              '--server-url', 'http://localhost:8000'])
    assert calls[0]['schemas'] == ['crm'] and calls[0]['tables'] == ['customer']
    assert calls[0]['cluster'] == 'invoice' and calls[0]['relatives'] == 'ancestors'
    assert calls[0]['depth'] == 2
    assert capsys.readouterr().out == 'http://localhost:8000/diagrams/example\n'


def test_rest_mcp_and_published_page_share_filters(server, graph):
    args = {'structure': graph, 'cluster': 'invoice', 'depth': 1}
    status, body = _request(server, '/diagram', method='POST', payload={**args, 'format': 'dot'})
    assert status == 200
    expected = json.loads(body)
    assert expected['tables'] == 4
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'diagram', 'arguments': {**args, 'format': 'dot'}},
    })
    assert status == 200
    assert json.loads(json.loads(body)['result']['content'][0]['text']) == expected
    status, body = _request(server, '/publish_diagram', method='POST', payload=args)
    assert status == 200
    published = json.loads(body)
    assert published['tables'] == 4 and published['relations'] == expected['relations']
    status, body = _request(server, published['url'])
    assert status == 200 and b'4 tables' in body
    assert _request(server, '/diagram', method='POST', payload={
        'structure': graph, 'cluster': 'private-missing',
    })[0] == 400
