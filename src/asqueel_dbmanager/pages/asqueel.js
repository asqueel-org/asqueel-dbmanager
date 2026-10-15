// HTML-first Gramlot workspace. All data enters the DOM through textContent.
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
};
const pretty = value => JSON.stringify(value, null, 2);
const missing = Symbol('missing');
const container = value => value !== null && typeof value === 'object' && value !== missing;

// Both sides use the same union of paths, including explicit missing nodes.
export function comparisonTrees(desired, current) {
    function walk(a, b, name, path) {
        const objectA = container(a), objectB = container(b);
        const keys = [...new Set([...(objectA ? Object.keys(a) : []), ...(objectB ? Object.keys(b) : [])])].sort();
        const children = keys.map(key => walk(objectA && Object.hasOwn(a, key) ? a[key] : missing,
            objectB && Object.hasOwn(b, key) ? b[key] : missing, key, [...path, key]));
        const status = a === missing ? 'current' : b === missing ? 'desired' :
            (objectA !== objectB || Array.isArray(a) !== Array.isArray(b) ||
             (objectA ? children.some(([left]) => left.status !== 'equal') : a !== b)) ? 'changed' : 'equal';
        const node = (value, side) => ({name, path, status, missing: value === missing,
            detail: value === missing ? {status: 'Not present on this side'} :
                {type: Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value,
                 value: container(value) ? `${Object.keys(value).length} entries` : value},
            children: children.map(pair => pair[side])});
        return [node(a, 0), node(b, 1)];
    }
    return walk(desired, current, 'Migration JSON', []);
}

function snapshot(node, path = []) {
    return {name: node.name, path, detail: {type: node.type, attributes: node.attributes, value: node.value},
        children: node.children.map(child => snapshot(child, [...path, child.name]))};
}

export class Logic {
    start() { mount(); }
}

function mount() {
    const root = $('workbench');
    if (!root || root.dataset.started) return;
    root.dataset.started = 'true';
    const base = location.pathname.slice(0, location.pathname.lastIndexOf('/ui/'));
    let busy = false, loaded = null, plan = null, active = 'objects', trees = {}, selected = {};
    let maps = {};
    const config = () => $('configuration').value;
    const status = (message, error = false) => {
        $('status').textContent = message; $('status').classList.toggle('error', error);
    };
    function controls() {
        $('configuration').disabled = busy;
        for (const button of root.querySelectorAll('[data-action]')) {
            const action = button.dataset.action;
            button.disabled = busy || (action === 'load' && !config()) ||
                (['compare', 'plan'].includes(action) && (!loaded || loaded.backend !== 'postgresql')) ||
                (action === 'apply' && (!plan || $('confirm-configuration').value !== config()));
        }
        $('allow-removals').disabled = busy;
    }
    async function api(action, data = {}) {
        const response = await fetch(`${base}/console_action`, {method: 'POST',
            headers: {'Content-Type': 'application/json'}, credentials: 'same-origin',
            body: JSON.stringify({action: `asqueel_${action}`, data})});
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || result.message || result.error?.message || `Request failed (${response.status})`);
        return result;
    }
    async function run(fn) {
        if (busy) return;
        busy = true; controls(); root.setAttribute('aria-busy', 'true'); status('Working…');
        try { await fn(); status('Done.'); }
        catch (error) { status(error.message || 'Operation failed', true); }
        finally { busy = false; controls(); root.removeAttribute('aria-busy'); }
    }
    function forgetPlan() {
        plan = null; $('migration-plan').replaceChildren(); $('confirm-configuration').value = ''; controls();
    }
    function clear() {
        loaded = null; trees = {}; selected = {}; forgetPlan();
        $('configuration-info').textContent = ''; $('result').replaceChildren(); render();
    }
    function selectTab(key) {
        active = key;
        for (const button of root.querySelectorAll('[data-tab]')) {
            const yes = button.dataset.tab === key;
            button.setAttribute('aria-selected', String(yes)); button.tabIndex = yes ? 0 : -1;
            $(`panel-${button.dataset.tab}`).hidden = !yes;
        }
        render();
    }
    function render() {
        maps = {};
        const query = $('tree-search').value.toLowerCase().trim();
        const only = $('only-differences').checked;
        const keys = active === 'objects' ? ['config', 'objects'] : ['desired', 'current'];
        function filter(node) {
            if (active === 'migration' && only && node.status === 'equal') return null;
            const matches = !query || `${node.path.join('.')} ${node.name} ${pretty(node.detail)}`.toLowerCase().includes(query);
            const children = node.children.map(filter).filter(Boolean);
            return matches || children.length ? {...node, children} : null;
        }
        function choose(key, node) {
            const targets = active === 'migration' ? keys : [key];
            for (const target of targets) {
                selected[target] = pretty(node.path);
                const entry = maps[target]?.get(selected[target]);
                $(`detail-${target}`).textContent = pretty({path: node.path, ...(entry?.node || node).detail,
                    ...(node.status ? {comparison: node.status} : {})});
                for (const [path, item] of maps[target] || []) item.button.setAttribute('aria-pressed', String(path === selected[target]));
            }
        }
        function item(key, node, depth) {
            const row = el('li', undefined, node.status && node.status !== 'equal' ? `diff-${node.status}` : '');
            const details = node.children.length ? el('details') : null;
            const label = details ? el('summary') : el('div');
            const button = el('button', node.name, `node-button${node.missing ? ' missing' : ''}`);
            button.type = 'button'; button.title = node.path.join('.') || node.name;
            button.setAttribute('aria-pressed', String(selected[key] === pretty(node.path)));
            button.onclick = event => { event.preventDefault(); choose(key, node); };
            label.append(button);
            const badge = node.status && node.status !== 'equal' ?
                ({desired: 'Desired only', current: 'Database only', changed: 'Changed'})[node.status] : node.detail.type;
            if (badge) label.append(el('small', badge));
            const entry = {node, button, details}; maps[key].set(pretty(node.path), entry);
            if (details) {
                details.append(label); row.append(details);
                let populated = false;
                function populate() {
                    if (populated) return;
                    populated = true; const list = el('ul');
                    node.children.forEach(child => list.append(item(key, child, depth + 1))); details.append(list);
                }
                details.ontoggle = () => {
                    if (details.open) populate();
                    if (active === 'migration') {
                        const other = maps[key === 'desired' ? 'current' : 'desired']?.get(pretty(node.path));
                        if (other?.details && other.details.open !== details.open) other.details.open = details.open;
                    }
                };
                details.open = depth < 2 || Boolean(query);
                if (details.open) populate();
            } else row.append(label);
            return row;
        }
        for (const key of keys) {
            maps[key] = new Map(); const host = $(`tree-${key}`);
            $(`detail-${key}`).textContent = 'Select a node to inspect its details.';
            const tree = trees[key] && filter(trees[key]);
            if (!tree) { host.replaceChildren(el('p', trees[key] ? (only && active === 'migration' && !query ? 'No JSON differences.' : 'No matching nodes.') : 'Load the configuration or read the comparison.', 'empty')); continue; }
            const list = el('ul'); list.append(item(key, tree, 0)); host.replaceChildren(list);
        }
    }
    async function compare() {
        const result = await api('compare', {configuration: config()});
        [trees.desired, trees.current] = comparisonTrees(result.desired, result.current);
        $('configuration-info').textContent = `${result.configuration} · Target: ${pretty(result.target)} · Managed schemas: ${result.schemas.join(', ')}`;
        render();
    }
    root.addEventListener('click', event => {
        const tab = event.target.closest('[data-tab]');
        if (tab) { selectTab(tab.dataset.tab); return; }
        const button = event.target.closest('[data-action]');
        if (!button) return;
        run(async () => {
            const action = button.dataset.action;
            if (action === 'refresh') {
                clear(); const previous = config(), data = await api('list');
                $('configuration').replaceChildren(new Option('Select a configuration', ''));
                data.configurations.forEach(name => $('configuration').add(new Option(name, name)));
                if (data.configurations.includes(previous)) $('configuration').value = previous;
                else if (data.configurations.length === 1) $('configuration').value = data.configurations[0];
                if (!data.configurations.length) $('configuration-info').textContent = 'No configurations registered on this server. Use asqueel register NAME FOLDER (ASQUEEL_HOME selects the registry).';
            } else if (action === 'load') {
                clear(); loaded = await api('inspect', {configuration: config()});
                trees.config = snapshot(loaded.configuration_tree); trees.objects = snapshot(loaded.object_tree);
                $('configuration-info').textContent = `${loaded.configuration} · ${loaded.backend} · Configuration loaded without database introspection`;
                selectTab('objects');
            } else if (action === 'compare') { forgetPlan(); await compare(); }
            else if (action === 'reset-trees') render();
            else if (action === 'plan') {
                forgetPlan();
                const allow = $('allow-removals').checked;
                const response = await api('plan', {configuration: config(), allow_removals: allow});
                const p = response.plan;
                $('migration-plan').replaceChildren(el('h3', `Plan for ${response.target.dbname}`),
                    el('p', `Managed schemas: ${response.schemas.join(', ')}`), el('pre', p.sql || 'No SQL changes.'),
                    el('pre', pretty({plan_id: p.plan_id, warnings: p.warnings, skipped: p.skipped})));
                if (!p.skipped.length && !p.empty) plan = {configuration: config(), allow_removals: allow, expected_plan: p.plan_id};
            } else if (action === 'apply') {
                if (!plan || plan.configuration !== config() || plan.allow_removals !== $('allow-removals').checked || $('confirm-configuration').value !== config()) throw new Error('Preview the plan and confirm the registered configuration name.');
                const request = {...plan, confirm_configuration: config()}; forgetPlan();
                const response = await api('apply', request); $('result').replaceChildren(el('pre', pretty(response)));
                await compare();
            }
        });
    });
    root.querySelector('[role=tablist]').addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault(); const key = event.key === 'Home' ? 'objects' : event.key === 'End' ? 'migration' : active === 'objects' ? 'migration' : 'objects';
        selectTab(key); $(`tab-${key}`).focus();
    });
    $('configuration').onchange = clear;
    $('allow-removals').onchange = forgetPlan;
    $('confirm-configuration').oninput = controls;
    $('tree-search').oninput = render;
    $('only-differences').onchange = render;
    render(); root.querySelector('[data-action=refresh]').click();
}
