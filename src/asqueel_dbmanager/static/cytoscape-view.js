/* Experimental viewer. Cytoscape.js is bundled locally under its MIT license. */
'use strict';
(() => {
  const config = JSON.parse(document.getElementById('graph-data').textContent);
  const el = id => document.getElementById(id);
  const status = text => { el('status').textContent = text; };
  if (typeof cytoscape !== 'function') { status('Cannot load the local Cytoscape library.'); return; }
  const xml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[char]));
  const key = `dbmanager.cytoscape.${config.pageId}`;
  const referenced = new Map();
  config.graph.edges.forEach(({data}) => {
    if (!referenced.has(data.target)) referenced.set(data.target, new Set());
    data.related_columns.forEach(column => referenced.get(data.target).add(column));
  });
  function shownColumns(data) {
    return data.columns.filter(c => !el('keys-only').checked || c.flags.some(f => ['PK','FK','UQ'].includes(f)) || referenced.get(data.id)?.has(c.name));
  }
  function card(data) {
    const cols = shownColumns(data);
    const {nameWidth,typeWidth,width,height} = config.cardSizes[data.id];
    const bodyHeight=height-56, scrollTop=Math.max(0,Math.min(data.scrollTop||0,cols.length*24-bodyHeight));
    const rows = cols.map((c, i) => `<rect x="0" y="${i*24-scrollTop}" width="${width}" height="24" fill="${i%2?'#f3f7fb':'white'}"/><text x="10" y="${16+i*24-scrollTop}">${xml(c.name)}</text><text x="${nameWidth}" y="${16+i*24-scrollTop}">${xml(c.dtype)}</text><text x="${nameWidth+typeWidth}" y="${16+i*24-scrollTop}" fill="#256953">${xml(c.flags.join(' '))}</text>`).join('');
    const note=cols.length*24>bodyHeight?' · scroll columns':'';
    const svg = `<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="white"/><rect width="100%" height="32" fill="#183b56"/><g font-family="monospace" font-size="12" fill="#18334e"><text x="12" y="21" fill="white" font-weight="bold">${xml(data.name)}</text><svg x="0" y="32" width="${width}" height="${bodyHeight}" overflow="hidden">${rows}</svg><text x="10" y="${height-8}" fill="#62788e">${cols.length} / ${data.columns.length} columns${note}</text></g></svg>`;
    return {width, height, scrollTop, shownColumns:cols.map(c=>c.name), image:'data:image/svg+xml;utf8,'+encodeURIComponent(svg)};
  }
  config.graph.nodes.forEach(n => Object.assign(n.data, card(n.data)));
  config.graph.edges.forEach(e => {e.data.label=`${e.data.columns.join(', ')} → ${e.data.related_columns.join(', ')}`;});
  function endpoint(node, columns, side) {
    const index = columns.length === 1 ? node.data('shownColumns').indexOf(columns[0]) : -1;
    // Offscreen columns connect at the nearest body boundary, never outside the card.
    const y = index < 0 ? 16 : Math.max(34,Math.min(node.data('height')-26,44+index*24-node.data('scrollTop')));
    return `${side*50}% ${(y/node.data('height')-0.5)*100}%`;
  }
  const cy = cytoscape({container:el('cy'), elements:config.graph, layout:{name:'preset'},
    minZoom:0.02, maxZoom:3,
    style:[
      {selector:'node',style:{shape:'rectangle',width:'data(width)',height:'data(height)',
        'background-image':'data(image)','background-fit':'contain','background-opacity':1,
        'background-color':'white','border-width':1,'border-color':'#bdcbd8'}},
      {selector:'node:selected',style:{'border-width':3,'border-color':'#0e9c80'}},
      {selector:'edge',style:{width:1.8,'line-color':'#6c849a','target-arrow-color':'#6c849a',
        'target-arrow-shape':'triangle','curve-style':'bezier',
        'source-endpoint':e=>endpoint(e.source(),e.data('columns'),1),
        'target-endpoint':e=>endpoint(e.target(),e.data('related_columns'),-1),
        label:'data(label)','font-size':10,'text-background-color':'#f0f4f8',
        'text-background-opacity':0.9,'text-background-padding':'3px','text-rotation':'autorotate'}},
      {selector:'edge:selected',style:{'line-color':'#0e9c80','target-arrow-color':'#0e9c80',width:3}},
      {selector:'.hidden',style:{display:'none'}}
    ]});
  // Native scrolling bodies sit over the canvas cards; headers remain draggable in Cytoscape.
  // Keep an SVG copy in each node for the overview and PNG export.
  const scrollBodies=new Map();
  function buildScrollBodies() {
    el('card-scroll-layer').replaceChildren();scrollBodies.clear();
    cy.nodes().forEach(node=>{
      const data=node.data(), geometry=config.cardSizes[data.id];
      const shell=document.createElement('div');shell.className='table-card';
      shell.style.width=`${geometry.width}px`;shell.style.height=`${geometry.height}px`;
      const heading=document.createElement('div');heading.className='table-heading';heading.textContent=data.name;
      const footer=document.createElement('div');footer.className='table-footer';
      const columns=shownColumns(data);
      footer.textContent=`${columns.length} / ${data.columns.length} columns${columns.length*24>geometry.height-56?' · scroll columns':''}`;
      const body=document.createElement('div');body.className='table-scroll';body.tabIndex=0;
      body.setAttribute('role','region');body.setAttribute('aria-label',`Columns of ${data.name}`);
      body.style.width=`${geometry.width}px`;body.style.height=`${geometry.height-56}px`;
      columns.forEach(c=>{
        const row=document.createElement('div');row.className='column-row';
        row.style.gridTemplateColumns=`${geometry.nameWidth-10}px ${geometry.typeWidth}px minmax(0,1fr)`;
        [c.name,c.dtype,c.flags.join(' ')].forEach(value=>{const cell=document.createElement('span');cell.textContent=value;cell.title=value;row.append(cell);});
        body.append(row);
      });
      body.onclick=()=>{cy.elements().unselect();node.select();tableDetails(node);};
      body.onscroll=()=>{node.data(card({...node.data(),scrollTop:body.scrollTop}));node.connectedEdges().updateStyle();};
      shell.append(heading,body,footer);el('card-scroll-layer').append(shell);
      scrollBodies.set(node.id(),body);body.scrollTop=data.scrollTop;
    });
    syncScrollBodies();
  }
  function syncScrollBodies() {
    const zoom=cy.zoom();
    cy.nodes().forEach(node=>{
      const body=scrollBodies.get(node.id());if(!body)return;
      const shell=body.parentElement;
      const p=node.renderedPosition(),width=node.data('width'),height=node.data('height');
      const x=p.x-width*zoom/2,y=p.y-height*zoom/2;
      shell.hidden=node.hasClass('hidden')||zoom<0.35||x>cy.width()||y>cy.height()||x+width*zoom<0||y+height*zoom<0;
      shell.style.transform=`translate(${x}px,${y}px) scale(${zoom})`;
    });
  }
  let scrollFrame;
  function scheduleScrollBodies(){if(!scrollFrame)scrollFrame=requestAnimationFrame(()=>{scrollFrame=null;syncScrollBodies();});}
  cy.on('pan zoom resize position',scheduleScrollBodies);
  const fit = () => {const nodes=cy.nodes().not('.hidden'); if(nodes.length)cy.fit(nodes,40);};
  function readable() {
    const nodes=cy.nodes().not('.hidden');
    if(!nodes.length)return;
    fit();
    if(cy.zoom()<0.85){
      const selected=nodes.filter(':selected');
      const focus=selected.length?selected[0]:nodes.sort((a,b)=>b.connectedEdges().not('.hidden').length-a.connectedEdges().not('.hidden').length)[0];
      cy.zoom(0.85);cy.center(focus);
    }
  }
  function layout() {
    const elements=cy.elements().not('.hidden'), name=el('layout-type').value;
    if(!elements.nodes().length)return;
    if(name==='graphviz'){
      const positions=config.graphvizPositions;
      elements.layout({name:'preset',positions,fit:false,animate:false}).run();
      readable();status('Graphviz layout applied. Drag tables to adjust; Cytoscape draws the relations.');
      return;
    }
    if(name==='cose')elements.layout({name:'grid',fit:false,avoidOverlap:true}).run();
    elements.layout({name,directed:false,avoidOverlap:true,
      direction:config.direction==='TB'?'downward':'rightward',spacingFactor:1.1,
      fit:false,animate:false,randomize:false,componentSpacing:100,
      nodeRepulsion:()=>18000,nodeOverlap:20,idealEdgeLength:()=>100,
      edgeElasticity:()=>100,gravity:0.5,numIter:1200,
      stop:()=>{readable();status('Layout ready. Drag the background to explore; Fit shows the complete overview.');}
    }).run();
  }
  function tableDetails(node) {
    el('detail-title').textContent=node.data('name'); el('details').replaceChildren();
    const table=document.createElement('table');
    node.data('columns').forEach(c=>{const row=table.insertRow();
      [c.name,c.dtype,c.flags.join(' ')].forEach(value=>{row.insertCell().textContent=value;});});
    el('details').append(table);
  }
  function listTables() {
    el('tables').replaceChildren();
    cy.nodes().not('.hidden').forEach(node=>{const button=document.createElement('button');
      button.textContent=node.data('name'); button.onclick=()=>{cy.elements().unselect();node.select();cy.center(node);tableDetails(node);};
      el('tables').append(button);});
    const nodes=cy.nodes().not('.hidden').length, edges=cy.edges().not('.hidden').length;
    el('summary').textContent=`${nodes} ${nodes===1?'table':'tables'} · ${edges} ${edges===1?'relation':'relations'} · Drag headers · Scroll columns`;
  }
  cy.on('tap','node',event=>tableDetails(event.target));
  cy.on('tap','edge',event=>{const edge=event.target;el('detail-title').textContent='Foreign key';
    el('details').textContent=`${edge.source().data('name')} (${edge.data('columns').join(', ')}) → ${edge.target().data('name')} (${edge.data('related_columns').join(', ')})`;});
  cy.on('dragfree','node',event=>status(`Moved ${event.target.data('name')}. Use Save positions to keep this arrangement.`));
  el('fit').onclick=fit;
  el('readable').onclick=readable;
  const zoomLabel=()=>{el('zoom-level').textContent=Math.round(cy.zoom()*100)+'%';};
  cy.on('zoom',zoomLabel);zoomLabel();
  el('details-toggle').onclick=()=>{const open=document.body.classList.toggle('show-details');el('details-toggle').setAttribute('aria-expanded',String(open));};
  new ResizeObserver(()=>{cy.resize();scheduleScrollBodies();}).observe(el('diagram-stage'));
  el('zoom-in').onclick=()=>cy.zoom({level:cy.zoom()*1.25,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});
  el('zoom-out').onclick=()=>cy.zoom({level:cy.zoom()/1.25,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});
  el('layout').onclick=layout;
  el('keys-only').onchange=()=>{cy.batch(()=>cy.nodes().forEach(n=>n.data(card({...n.data(),scrollTop:0}))));cy.edges().updateStyle();buildScrollBodies();status('Column visibility changed. Table sizes, positions and zoom are unchanged.');};
  el('save').onclick=()=>{try{localStorage.setItem(key,JSON.stringify(cy.nodes().map(n=>({id:n.id(),position:n.position()}))));status('Positions saved in this browser for this snapshot.');}catch{status('Browser storage unavailable; positions were not saved.');}};
  let pngUrl;
  el('png').onclick=()=>{try{if(pngUrl)URL.revokeObjectURL(pngUrl);
    const blob=cy.png({output:'blob',full:true,scale:2,maxWidth:6000,maxHeight:6000});
    pngUrl=URL.createObjectURL(blob);el('png-download').href=pngUrl;el('png-download').hidden=false;
    status(`PNG ready (${Math.round(blob.size/1024)} KB). Use Save PNG to download.`);
  }catch{status('PNG export failed. Try a smaller filtered graph.');}};
  function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
  [...new Set(config.graph.nodes.map(n=>n.data.schema))].sort().forEach(s=>option(el('schema'),s,s));
  config.graph.nodes.forEach(n=>option(el('cluster'),n.data.id,n.data.name));
  function reachable(seed, reverse, depth) {
    const seen=new Set([seed]);let frontier=[seed],level=0;
    while(frontier.length && level<depth){const next=new Set();
      config.graph.edges.forEach(({data:e})=>{const source=reverse?e.target:e.source,target=reverse?e.source:e.target;
        if(frontier.includes(source)&&!seen.has(target))next.add(target);});
      next.forEach(id=>seen.add(id));frontier=[...next];level++;}
    return seen;
  }
  function filter() {
    const seed=el('cluster').value, schema=el('schema').value, direction=el('relatives').value;
    const depth=el('depth').value===''?Infinity:Number(el('depth').value);
    if(!Number.isInteger(depth)&&depth!==Infinity || depth<0){status('Depth must be a non-negative integer.');return;}
    let selected=new Set(config.graph.nodes.map(n=>n.data.id));
    if(seed){selected=new Set([seed]);
      if(direction!=='descendants')reachable(seed,false,depth).forEach(id=>selected.add(id));
      if(direction!=='ancestors')reachable(seed,true,depth).forEach(id=>selected.add(id));}
    cy.batch(()=>{cy.nodes().forEach(n=>n.toggleClass('hidden',!selected.has(n.id())||!!schema&&schema!==n.data('schema')));
      cy.edges().forEach(e=>e.toggleClass('hidden',e.source().hasClass('hidden')||e.target().hasClass('hidden')));});
    listTables();readable();syncScrollBodies();status('Filters applied within this saved snapshot.');
  }
  el('filter').onclick=filter;
  el('clear').onclick=()=>{el('cluster').value='';el('schema').value='';el('relatives').value='both';el('depth').value='';filter();};
  if(config.graphvizPositions){option(el('layout-type'),'graphviz','Graphviz');el('layout-type').value='graphviz';}
  let restored=false;
  try{const positions=JSON.parse(localStorage.getItem(key));
    if(Array.isArray(positions)&&positions.length===cy.nodes().length&&positions.every(p=>cy.getElementById(p.id).isNode()&&Number.isFinite(p.position?.x)&&Number.isFinite(p.position?.y))){
      positions.forEach(p=>cy.getElementById(p.id).position(p.position));readable();restored=true;status('Saved browser positions restored.');}}
  catch{status('Saved positions unavailable; using automatic layout.');}
  if(!restored)layout();listTables();buildScrollBodies();
  if(!cy.nodes().length)status('No tables in this snapshot.');
})();
