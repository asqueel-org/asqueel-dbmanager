"""Persistent rendered snapshots and a self-contained HTML diagram viewer."""

import base64
import html
import json
import os
import re
from pathlib import Path
from secrets import token_hex
from uuid import uuid4

from .cytoscape_view import graph_data
from .diagrams import diagram


class DiagramPages:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def create(self, structure, direction='LR', title='Database diagram', renderer='graphviz',
               profile_access=None, **filters):
        if renderer not in {'graphviz', 'cytoscape'} or direction not in {'LR', 'TB'}:
            raise ValueError('Invalid renderer or direction')
        if renderer == 'cytoscape':
            graph = graph_data(structure, **filters)
            rendered = {'format': 'cytoscape', 'graph': graph, 'direction': direction,
                        'tables': len(graph['nodes']), 'relations': len(graph['edges'])}
        else:
            rendered = diagram(structure, format='svg', direction=direction, **filters)
        page_id = uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / f'{page_id}.json'
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                snapshot = {**rendered, 'title': title}
                if profile_access is not None:
                    snapshot['profile_access'] = profile_access
                json.dump(snapshot, stream, ensure_ascii=False)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {'diagram_id': page_id, 'tables': rendered['tables'],
                'relations': rendered['relations']}

    def read(self, page_id):
        if not re.fullmatch(r'[0-9a-f]{32}', page_id):
            raise FileNotFoundError('Unknown diagram')
        path = self.root / f'{page_id}.json'
        if path.is_symlink():
            raise FileNotFoundError('Unknown diagram')
        return json.loads(path.read_text(encoding='utf-8'))


def viewer(snapshot, svg_url):
    """Use an image context for SVG; schema labels can never become HTML code."""
    title = html.escape(snapshot['title'], quote=True)
    image = base64.b64encode(snapshot['content'].encode('utf-8')).decode('ascii')
    nonce = token_hex(16)
    content = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font:15px system-ui,sans-serif;color:#172b42;background:#edf2f7}}
header{{padding:18px 24px;background:white;border-bottom:1px solid #d5dee8}}
h1{{font-size:22px;margin:0 0 6px}}p{{margin:0;color:#516479}}
nav{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}}
button,a{{padding:8px 12px;border:1px solid #bccbd9;border-radius:6px;background:white;color:#172b42;font:inherit}}
button{{cursor:pointer}}a{{text-decoration:none}}button:hover,a:hover{{background:#edf2f7}}
#viewport{{height:calc(100vh - 158px);min-height:300px;overflow:auto;padding:20px}}
img{{display:block;max-width:none;background:white;box-shadow:0 2px 12px #172b4218}}
</style></head><body>
<header><h1>{title}</h1><p>{snapshot['tables']} tables · {snapshot['relations']} relations · Saved snapshot</p>
<nav aria-label="Diagram controls"><button id="fit">Fit width</button>
<button id="smaller" aria-label="Zoom out">−</button><button id="larger" aria-label="Zoom in">+</button>
<button id="actual">100%</button><span id="zoom" aria-live="polite"></span>
<a href="{html.escape(svg_url, quote=True)}" download="diagram.svg">Download SVG</a></nav></header>
<main id="viewport"><img id="diagram" alt="Database tables and relationships" src="data:image/svg+xml;base64,{image}"></main>
<script nonce="{nonce}">
const image=document.getElementById('diagram'), viewport=document.getElementById('viewport');
let scale=1;
function show(value){{scale=Math.max(0.01,Math.min(4,value));image.style.width=(image.naturalWidth*scale)+'px';
 document.getElementById('zoom').textContent=Math.round(scale*100)+'%';}}
function fit(){{show((viewport.clientWidth-40)/image.naturalWidth);}}
document.getElementById('fit').onclick=fit;
document.getElementById('smaller').onclick=()=>show(scale/1.25);
document.getElementById('larger').onclick=()=>show(scale*1.25);
document.getElementById('actual').onclick=()=>show(1);
image.onload=fit;if(image.complete&&image.naturalWidth)fit();
</script></body></html>'''
    return content, f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'"
