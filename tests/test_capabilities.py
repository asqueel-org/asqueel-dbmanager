"""Optional renderer discovery works without Graphviz or a running server."""

import json
import subprocess

import pytest
from conftest import _request

from asqueel_dbmanager import diagrams
from asqueel_dbmanager.__main__ import main


@pytest.mark.parametrize('outcome', [
    'svg', 'missing', 'permission', 'timeout', 'failed', 'invalid', 'html',
])
def test_capability_checks_rendering_not_just_executable_presence(monkeypatch, outcome):
    def run(args, **kwargs):
        assert kwargs['timeout'] == 2
        if outcome == 'missing':
            raise FileNotFoundError()
        if outcome == 'permission':
            raise PermissionError('private-path')
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired('dot', 2, stderr='private-value')
        output = {
            'svg': '<svg xmlns="http://www.w3.org/2000/svg"/>',
            'failed': '', 'invalid': 'private-invalid-output', 'html': '<html/>',
        }[outcome]
        return subprocess.CompletedProcess(args, 1 if outcome == 'failed' else 0, output, 'private-value')
    monkeypatch.setattr(diagrams.subprocess, 'run', run)
    result = diagrams.diagram_capabilities()
    available = outcome == 'svg'
    assert result == {
        'capabilities': {'graphviz': available},
        'diagram_formats': ['dot', 'svg'] if available else ['dot'],
    }


def test_missing_graphviz_keeps_dot_available_and_discovery_updates(monkeypatch):
    monkeypatch.setenv('PATH', '')
    assert diagrams.diagram_capabilities()['diagram_formats'] == ['dot']
    structure = {'root': {'entity': 'db', 'entity_name': 'empty', 'schemas': {}}}
    assert diagrams.diagram(structure, 'dot')['format'] == 'dot'
    with pytest.raises(diagrams.DiagramRenderError, match='install dot'):
        diagrams.diagram(structure, 'svg')
    monkeypatch.setattr(diagrams.subprocess, 'run', lambda args, **kwargs: subprocess.CompletedProcess(
        args, 0, '<svg xmlns="http://www.w3.org/2000/svg"/>', '',
    ))
    assert diagrams.diagram_capabilities()['capabilities']['graphviz'] is True


def test_capabilities_rest_mcp_and_cli_agree_without_graphviz(server, monkeypatch, capsys):
    monkeypatch.setenv('PATH', '')
    status, body = _request(server, '/capabilities', method='POST', payload={})
    assert status == 200
    expected = json.loads(body)
    assert expected['capabilities']['graphviz'] is False
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'capabilities', 'arguments': {}},
    })
    assert status == 200
    assert json.loads(json.loads(body)['result']['content'][0]['text']) == expected
    def forbidden(*args, **kwargs):
        pytest.fail('The capabilities command must not construct a server')
    monkeypatch.setattr('asqueel_dbmanager.__main__.AsgiServer', forbidden)
    main(['capabilities'])
    assert json.loads(capsys.readouterr().out) == expected
