// Native controls during the Gramlot beta. No experimental component APIs.
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
};
const value = id => $(id)?.value || '';
const pretty = data => JSON.stringify(data, null, 2);

export class Logic {
    start() { mount(); }
}

function mount() {
    const root = $('workbench');
    if (!root || root.dataset.started) return;
    root.dataset.started = 'true';
    if (root.dataset.page === 'shell') {
        const toggle = $('navigation-toggle');
        const navigation = collapsed => {
            root.classList.toggle('navigation-collapsed', collapsed);
            toggle.setAttribute('aria-expanded', String(!collapsed));
        };
        toggle.onclick = () => navigation(!root.classList.contains('navigation-collapsed'));
        root.addEventListener('click', event => {
            const link = event.target.closest('a[data-page-link]');
            if (!link) return;
            event.preventDefault();
            const key = link.dataset.pageLink;
            if (key === 'diagram') navigation(true);
            let frame = $(`frame-${key}`);
            if (!frame) {
                frame = el('iframe'); frame.id = `frame-${key}`;
                frame.src = key; frame.title = link.textContent; $('frames').append(frame);
            }
            for (const item of $('frames').children) item.hidden = item !== frame;
            for (const item of root.querySelectorAll('a[data-page-link]')) {
                if (item === link) item.setAttribute('aria-current', 'page');
                else item.removeAttribute('aria-current');
            }
        });
        return;
    }
    // Instructions are available without unlocking profiles or calling the API.
    if (root.dataset.page === 'home') return;
    const base = location.pathname.slice(0, location.pathname.lastIndexOf('/ui/'));
    let busy = false, guide = null, guideDatabase = null, session = null, plan = null;
    let profiles = [], canAdmin = false, diagramDetails = {};
    const db = () => value('database');
    const status = (message, error = false) => {
        $('status').textContent = message; $('status').classList.toggle('error', error);
    };
    async function api(action, data = {}) {
        const response = await fetch(`${base}/console_action`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin', body: JSON.stringify({action, data})
        });
        const text = await response.text();
        let result;
        try { result = JSON.parse(text); } catch { throw new Error(`Request failed (${response.status})`); }
        if (!response.ok) throw new Error(result.detail || (typeof result.error === 'string' ? result.error : result.error?.message) || result.message || `Request failed (${response.status})`);
        return result;
    }
    async function run(fn) {
        if (busy) return;
        busy = true; root.setAttribute('aria-busy', 'true'); status('Working…');
        try { await fn(); status('Done.'); }
        catch (error) { status(error.message || 'Operation failed', true); }
        finally { busy = false; root.removeAttribute('aria-busy'); updateControls(); }
    }
    function updateControls() {
        if ($('apply')) $('apply').disabled = !plan || !canAdmin;
        if ($('ask-button')) $('ask-button').disabled = !session;
        if ($('close-session')) $('close-session').disabled = !session;
        for (const action of ['backup', 'restore']) {
            const button = root.querySelector(`[data-action="${action}"]`);
            if (button) button.disabled = !canAdmin;
        }
        if ($('registration')) $('registration').querySelector('button').disabled = !canAdmin;
        if ($('database')) $('database').disabled = Boolean(session);
    }
    function show(data, target = 'result') { $(target).replaceChildren(el('pre', pretty(data))); }
    function table(columns, rows) {
        const wrap = el('div', null, 'scroll'), table = el('table'), head = el('tr');
        columns.forEach(c => head.append(el('th', c))); table.append(el('thead')); table.tHead.append(head);
        const body = el('tbody');
        rows.forEach(row => { const tr = el('tr'); row.forEach(v => tr.append(el('td', typeof v === 'object' && v !== null ? pretty(v) : v ?? '—'))); body.append(tr); });
        table.append(body); wrap.append(table); return wrap;
    }
    async function refresh() {
        const data = await api('list'); profiles = data.databases; canAdmin = data.can_administer;
        for (const select of root.querySelectorAll('select[data-databases]')) {
            const previous = select.value;
            select.replaceChildren(new Option('Select a database', ''));
            profiles.forEach(p => select.add(new Option(p.database, p.database)));
            if (profiles.some(p => p.database === previous)) select.value = previous;
            else if (profiles.length === 1) select.value = profiles[0].database;
        }
        if ($('database-list')) {
            const list = root.dataset.page === 'genropy' ? profiles.filter(p => p.source.kind === 'genropy') : profiles;
            $('database-list').replaceChildren(el('h2', 'Registered profiles'),
                list.length ? table(['Database', 'Source', 'AI enrollment'], list.map(p => [p.database, p.source.instance || 'PostgreSQL', p.enrollment])) : el('p', 'No profiles registered here yet.', 'empty'),
                el('p', `Identity: ${data.identity}${canAdmin ? '' : ' · Registration requires dbmanager_admin'}`, 'metadata'));
        }
    }
    function renderGuide(data) {
        guide = data.guide; guideDatabase = data.database;
        if (!guide) {
            $('guide-tables').replaceChildren(); $('guide-notes').value = '';
            $('guide-status').textContent = 'Not enrolled. Read the structure to start.'; return;
        }
        $('guide-status').textContent = `${data.stale ? 'stale' : guide.status} · ${Object.keys(guide.tables).length} tables · Updated ${guide.updated_at}`;
        $('guide-notes').value = guide.notes;
        const container = $('guide-tables'); container.replaceChildren();
        for (const [name, info] of Object.entries(guide.tables)) {
            const block = el('details', null, 'guide-table'); block.dataset.table = name;
            const summary = el('summary', name); summary.append(el('small', `${Object.keys(info.columns).length} columns`)); block.append(summary);
            const label = el('label', null, 'check'), checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = info.privacy === null; checkbox.dataset.privacy = 'table';
            label.append(checkbox, el('span', 'Share table data by default')); block.append(label);
            const desc = el('textarea'); desc.dataset.description = 'true'; desc.value = info.description; desc.rows = 2; desc.placeholder = 'Table explanation for the model'; desc.setAttribute('aria-label', `${name} description`); block.append(desc);
            const list = el('table'), head = el('tr'); ['Column', 'Type', 'Sharing', 'Effective'].forEach(c => head.append(el('th', c))); const thead = el('thead'); thead.append(head); list.append(thead);
            const body = el('tbody');
            const effective = () => { for (const row of body.rows) row.cells[3].textContent = row.querySelector('select').value === 'inherit' ? (checkbox.checked ? 'Allow' : 'Hide') : row.querySelector('select').value === 'allow' ? 'Allow' : 'Hide'; };
            for (const [col, attrs] of Object.entries(info.columns)) {
                const row = el('tr'); row.append(el('td', col), el('td', guide.details.tables[name].columns[col].dtype || ''));
                const cell = el('td'), select = el('select'); select.dataset.column = col; select.setAttribute('aria-label', `${name}.${col} privacy`);
                [['inherit', 'Inherit'], ['allow', 'Share'], ['hide', 'Hide']].forEach(([v,l]) => select.add(new Option(l,v)));
                select.value = Object.hasOwn(attrs, 'privacy') ? attrs.privacy === null ? 'allow' : 'hide' : 'inherit';
                select.addEventListener('change', effective); cell.append(select); row.append(cell, el('td')); body.append(row);
            }
            checkbox.addEventListener('change', effective); list.append(body); effective(); const wrap = el('div', null, 'scroll'); wrap.append(list); block.append(wrap); container.append(block);
        }
    }
    async function saveGuide(approve) {
        if (!guide || db() !== guideDatabase) throw new Error('Load the guide for this database first');
        const tables = {};
        for (const block of root.querySelectorAll('[data-table]')) {
            const columns = {};
            for (const select of block.querySelectorAll('select[data-column]')) columns[select.dataset.column] = select.value === 'inherit' ? {} : {privacy: select.value === 'allow' ? null : 'H'};
            tables[block.dataset.table] = {privacy: block.querySelector('[data-privacy]').checked ? null : 'H', description: block.querySelector('textarea').value, columns};
        }
        renderGuide(await api('save_guide', {database: db(), notes: value('guide-notes'), revision: guide.revision, tables, approve}));
    }
    root.addEventListener('click', event => {
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (!action) return;
        run(async () => {
            if (action === 'refresh') return refresh();
            if (action === 'close-session') {
                if (session) await api('close_session', {session_id: session.session_id});
                session = null; $('session-status').textContent = 'Session closed.'; return;
            }
            if (!db()) throw new Error('Select a database first');
            const data = {database: db()};
            if (['prepare','guide'].includes(action)) { renderGuide(await api(action, data)); return; }
            if (['save-draft','approve'].includes(action)) return saveGuide(action === 'approve');
            if (action === 'diagram') {
                const result = await api('diagram', data);
                // Ignore an in-flight result if the selected database has changed.
                if (db() !== data.database) return;
                const frame = $('database-diagram'); frame.src = result.url; frame.hidden = false;
                $('diagram-link').href = result.url; $('diagram-link').hidden = false;
                $('diagram-info').textContent = `${result.database} · ${result.tables} tables · ${result.relations} relations · ${new Date(result.computed_at).toLocaleString()}`;
                diagramDetails = result.table_details;
                $('index-table').replaceChildren(...Object.keys(diagramDetails).sort().map(name => new Option(name, name)));
                $('index-details').hidden = false; showIndexes(); return;
            }
            if (action === 'introspect') {
                const structure = await api(action, data); $('structure').value = pretty(structure); plan = null; show(structure); return;
            }
            if (action === 'plan') {
                plan = null; const structure = JSON.parse(value('structure'));
                const allow_removals = $('allow-removals').checked;
                const result = await api('plan', {...data, structure, allow_removals});
                plan = {database: db(), structure, allow_removals, expected_plan: result.plan_id}; show(result, 'plan-result'); return;
            }
            if (action === 'apply') {
                if (!plan || plan.database !== db() || pretty(plan.structure) !== pretty(JSON.parse(value('structure'))) || plan.allow_removals !== $('allow-removals').checked) throw new Error('Preview the current plan before applying');
                if (value('confirm-apply') !== db()) throw new Error('Type the database profile name to confirm');
                show(await api('apply', {...plan, confirm_database: value('confirm-apply')})); plan = null; return;
            }
            if (action === 'backup') { show(await api('backup', data)); return; }
            if (action === 'backups') {
                const {backups} = await api('backups', data);
                $('backup-list').replaceChildren(backups.length ? table(['Backup ID','Created','Bytes'], backups.map(b => [b.backup_id,b.created_at,b.size_bytes])) : el('p','No archives created here for this profile.','empty')); return;
            }
            if (action === 'restore') {
                if (!value('destination') || value('confirm-restore') !== value('destination')) throw new Error('Select and confirm the destination profile');
                show(await api('restore', {database:value('destination'), source_database:db(), backup_id:value('backup-id'), confirm_database:value('confirm-restore')})); return;
            }
            if (action === 'open-session') {
                if (session) throw new Error('Close the current session first');
                session = await api('open_session', data);
                $('session-status').textContent = `${session.database} · ${session.model} · Expires ${new Date(session.expires_at).toLocaleString()}`;
            }
        });
    });
    function showIndexes() {
        const info = diagramDetails[value('index-table')];
        if (!info) return;
        const target = $('table-indexes'); target.replaceChildren(el('p', `Primary key: ${info.primary_key || '—'}`));
        for (const [label, entries] of [['Indexes', info.indexes], ['Constraints', info.constraints]]) {
            target.append(el('h2', label));
            const rows = Object.entries(entries).map(([name, attrs]) => [attrs.index_name || attrs.constraint_name || name, pretty(attrs)]);
            target.append(rows.length ? table(['Name', 'Definition'], rows) : el('p', 'None reported by Migration.', 'muted'));
        }
    }
    $('index-table')?.addEventListener('change', showIndexes);
    $('database')?.addEventListener('change', () => {
        if (!$('database-diagram')) return;
        $('database-diagram').hidden = true; $('database-diagram').removeAttribute('src');
        $('diagram-link').hidden = true; $('diagram-info').textContent = ''; $('index-details').hidden = true;
        diagramDetails = {};
    });
    $('registration')?.addEventListener('submit', event => {
        event.preventDefault();
        const data = {database: value('profile')};
        const genropy = root.dataset.page === 'genropy';
        if (genropy) data.instance = value('instance');
        else { data.connection = {}; ['host','port','dbname','user','password'].forEach(k => { if (value(k)) data.connection[k] = value(k); }); }
        run(async () => { try { show(await api(genropy ? 'register_genropy' : 'register', data)); await refresh(); } finally { if ($('password')) $('password').value = ''; } });
    });
    $('structure-file')?.addEventListener('change', event => run(async () => {
        const file = event.target.files[0]; if (!file) return;
        if (file.size > 2_000_000) throw new Error('Structure file exceeds 2 MB');
        $('structure').value = pretty(JSON.parse(await file.text())); plan = null;
    }));
    $('structure')?.addEventListener('input', () => { plan = null; updateControls(); });
    $('allow-removals')?.addEventListener('change', () => { plan = null; updateControls(); });
    $('database')?.addEventListener('change', () => { plan = null; guide = null; guideDatabase = null; if ($('guide-tables')) { $('guide-tables').replaceChildren(); $('guide-status').textContent = ''; $('guide-notes').value = ''; } $('result').replaceChildren(); updateControls(); });
    $('ask')?.addEventListener('submit', event => {
        event.preventDefault();
        if (!session) return status('Open a session first', true);
        const question = value('question').trim(); if (!question) return;
        run(async () => {
            const answer = await api('ask', {session_id: session.session_id, question, output:value('output'), max_rows:100});
            const item = el('article', null, 'message'); item.append(el('p', question, 'question'));
            if (answer.clarification) item.append(el('p', answer.clarification));
            if (answer.error) item.append(el('pre', pretty(answer.error)));
            if (answer.result) {
                item.append(answer.result.rows.length ? table(answer.result.columns, answer.result.rows) : el('p', 'No matching rows.'));
                if (answer.result.truncated) item.append(el('p','First 100 rows shown.','muted'));
            }
            const details = el('details'); details.append(el('summary','SQL, parameters and assumptions'),el('pre',pretty({sql:answer.sql,params:answer.params,assumptions:answer.assumptions})));
            item.append(details,el('p',`${answer.usage?.elapsed_seconds ?? '—'} s · ${answer.usage?.cache_read_input_tokens ?? 0} cached input tokens · ${answer.corrections ?? 0} corrections`,'metadata'));
            $('conversation').append(item); $('question').value = ''; item.scrollIntoView({block:'nearest'});
        });
    });
    run(refresh);
}
