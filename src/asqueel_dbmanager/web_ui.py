"""Small Gramlot core bridge for Kajenn 0.1; no dependency on the newer adapter."""

import json
import re
from http.cookies import SimpleCookie
from pathlib import Path
from secrets import token_urlsafe

from kajenn import HTTPBadRequest, HTTPException, Response

PAGES = Path(__file__).with_name('pages')
COOKIE = 'dbmanager_ui'


class WebUI:
    def __init__(self):
        try:
            from gramlot.server import GramlotFileServer
        except ImportError:
            raise HTTPException(503, 'Install asqueel-dbmanager[ui] to enable the web interface') from None
        self.server = GramlotFileServer(PAGES, runtime_url='/runtime.js', rpc_url='/rpc',
                                        close_url='/close', page_ttl=28800, max_pages=512)

    def close(self):
        self.server.close_all()

    async def __call__(self, scope, receive, send, *, prefix, identity):
        from gramlot.server import InvalidRequest, PageNotFound, ServerCapacity, runtime_asset

        path = scope['path'].removeprefix('/ui').strip('/')
        method = scope.get('method', 'GET')
        headers = {'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
                   'referrer-policy': 'same-origin', 'x-frame-options': 'SAMEORIGIN'}
        if scope.get('query_string'):
            raise HTTPBadRequest('Unexpected URL parameters')
        cookies = SimpleCookie()
        try:
            cookies.load(dict(scope.get('headers', [])).get(b'cookie', b'').decode('latin-1'))
        except Exception:
            raise HTTPBadRequest('Invalid cookie') from None
        cookie = cookies[COOKIE].value if COOKIE in cookies else ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{32}', cookie):
            cookie = ''
        if path in {'rpc', 'close'}:
            if method != 'POST':
                raise HTTPException(405, 'Method Not Allowed')
            if not cookie:
                raise HTTPException(403, 'Open the page before sending requests')
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > 2_000_000:
                    raise HTTPException(413, 'Request too large')
                if not message.get('more_body'):
                    break
            owner = (identity, cookie)
            try:
                if path == 'rpc':
                    content = await self.server.call(body.decode(), owner=owner)
                else:
                    self.server.close_page(json.loads(body)['pageId'], owner=owner)
                    content = json.dumps({'ok': True})
            except (InvalidRequest, ValueError, KeyError, TypeError):
                raise HTTPBadRequest('Invalid Gramlot request') from None
            media = 'application/json'
        elif path in {'runtime.js', 'workbench.js', 'workbench.css', 'index.js',
                      'databases.js', 'genropy.js', 'migrations.js', 'backups.js',
                      'enrollment.js', 'guide.js', 'chat.js', 'diagram.js', 'home.js',
                      'asqueel.js', 'asqueel.css'}:
            if method not in {'GET', 'HEAD'}:
                raise HTTPException(405, 'Method Not Allowed')
            file = runtime_asset() if path == 'runtime.js' else PAGES / path
            content = b'' if method == 'HEAD' else file.read_bytes()
            media = 'text/css' if path.endswith('.css') else 'text/javascript'
        else:
            if method != 'GET':
                raise HTTPException(405, 'Method Not Allowed')
            if path not in {'', 'index', 'databases', 'genropy', 'migrations', 'backups',
                            'enrollment', 'guide', 'chat', 'diagram', 'home', 'asqueel'}:
                raise HTTPException(404, 'Unknown page')
            if scope['path'] == '/ui':
                await Response(content='', status_code=307,
                               headers={'location': prefix + '/'})(scope, receive, send)
                return
            cookie = cookie or token_urlsafe(24)
            try:
                opened = await self.server.open_page(path, owner=(identity, cookie), prefix=prefix)
            except PageNotFound:
                raise HTTPException(404, 'Unknown page') from None
            except ServerCapacity:
                raise HTTPException(503, 'Too many open pages') from None
            headers['set-cookie'] = (f'{COOKIE}={cookie}; Path={prefix}/; HttpOnly; SameSite=Strict'
                                     + ('; Secure' if scope.get('scheme') == 'https' else ''))
            headers['content-security-policy'] = (
                f"default-src 'self'; script-src 'self' 'nonce-{opened.nonce}'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; "
                "object-src 'none'; base-uri 'self'; form-action 'self'")
            content, media = opened.html, 'text/html'
        await Response(content=content, media_type=media, headers=headers)(scope, receive, send)
