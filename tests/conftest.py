import asyncio
import json

import pytest
from kajenn import AsgiServer

from asqueel_dbmanager.app import DbManagerApp, DbManagerWorker


def _request(
    server,
    path,
    *,
    method='GET',
    client='127.0.0.1',
    query=b'',
    payload=None,
    include_headers=False,
    auth=None,
    request_headers=None,
):
    """Drive one HTTP request through the real ASGI stack."""
    body = json.dumps(payload).encode() if payload is not None else b''
    headers = [(b'content-type', b'application/json')] if payload is not None else []
    headers.extend(request_headers or [])

    async def run():
        scope = {
            'type': 'http',
            'method': method,
            'path': path,
            'query_string': query,
            'headers': headers,
            'client': (client, 12345),
        }
        if auth is not None:
            scope['auth'] = auth
        sent = []

        async def receive():
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def send(message):
            sent.append(message)

        await server(scope, receive, send)
        status = next(
            message['status']
            for message in sent
            if message['type'] == 'http.response.start'
        )
        response_body = b''.join(
            message.get('body', b'')
            for message in sent
            if message['type'] == 'http.response.body'
        )
        if include_headers:
            raw_headers = next(message['headers'] for message in sent
                               if message['type'] == 'http.response.start')
            response_headers = dict(raw_headers)
            cookies = [value for name, value in raw_headers if name == b'set-cookie']
            if cookies:
                response_headers[b'set-cookie'] = b'\n'.join(cookies)
            return status, response_body, response_headers
        return status, response_body

    return asyncio.run(run())



@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASQUEEL_DBMANAGER_BACKUP_DIR", str(tmp_path / "backups"))
    return AsgiServer(applications=[DbManagerApp, DbManagerWorker])
