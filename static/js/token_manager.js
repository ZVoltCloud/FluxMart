// ═══════════════════ TOKEN MANAGER ═══════════════════

let tmFiles = [];
let tmAccounts = [];
let tmActiveFile = null;
let tmSearchQuery = '';
let tmChecking = false;
let tmHasEmail = false;
let tmHasUsername = false;

const TM_CACHE_KEY = 'msk_tm_cache';
function tmCacheGet() {
    try { return JSON.parse(localStorage.getItem(TM_CACHE_KEY) || '{}'); } catch(e) { return {}; }
}
function tmCacheSave(cache) {
    try { localStorage.setItem(TM_CACHE_KEY, JSON.stringify(cache)); } catch(e) {}
}
function tmCacheSet(token, data) {
    const c = tmCacheGet(); c[token] = data; tmCacheSave(c);
}
function tmCacheDelete(tokens) {
    const c = tmCacheGet(); tokens.forEach(t => delete c[t]); tmCacheSave(c);
}

async function tmInit() {
    await tmRefreshFiles();
}

async function tmRefreshFiles() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const result = await window.pywebview.api.list_token_files();
        if (result.success) {
            tmFiles = result.files;
            tmRenderFileTabs();
            if (tmFiles.length > 0 && !tmActiveFile) {
                await tmSelectFile(tmFiles[0].name);
            }
        }
    } catch (e) {
        console.error('Token Manager refresh error:', e);
    }
}

function tmRenderFileTabs() {
    const container = document.getElementById('tm-file-tabs');
    if (!container) return;

    if (tmFiles.length === 0) {
        container.innerHTML = '<div class="tm-no-files">No token files found in data/output/</div>';
        return;
    }

    container.innerHTML = tmFiles.map(f => {
        const isActive = tmActiveFile === f.name;
        const shortName = f.name.replace('.txt', '');
        return `<button class="tm-tab ${isActive ? 'active' : ''}" onclick="tmSelectFile('${f.name.replace(/'/g, "\\'")}')" title="${f.name}">
            <span class="tm-tab-dot ${f.count > 0 ? 'has-data' : ''}"></span>
            <span class="tm-tab-name">${shortName}</span>
            <span class="tm-tab-count">${f.count}</span>
        </button>`;
    }).join('');
}

async function tmSelectFile(filename) {
    tmActiveFile = filename;
    tmRenderFileTabs();

    const table = document.getElementById('tm-table-body');
    if (table) table.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text-secondary)">Loading...</td></tr>';

    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const result = await window.pywebview.api.load_token_file(filename);
        if (result.success) {
            tmAccounts = result.accounts.map(a => ({ 
                ...a, 
                status: a.status || 'unchecked', 
                avatarUrl: a.avatar_url || '' 
            }));
            // Restore cached check results so reopening doesn't require re-checking from localStorage (fallback)
            const _cache = tmCacheGet();
            tmAccounts.forEach(a => {
                const cached = _cache[a.token];
                if (cached) {
                    if (!a.status || a.status === 'unchecked') a.status = cached.status || 'unchecked';
                    if (!a.username || a.username === 'unknown')  a.username  = cached.username;
                    if (!a.hypesquad) a.hypesquad = cached.hypesquad;
                    if (!a.avatarUrl) a.avatarUrl = cached.avatarUrl;
                }
            });
            // Detect if any account has an email or a real username
            tmHasEmail    = tmAccounts.some(a => a.email && a.email.trim() !== '');
            tmHasUsername = tmAccounts.some(a => a.username && a.username.trim() !== '' && a.username !== 'unknown');
            tmUpdateTableHeader();
            tmUpdateStats();
            tmRenderTable();

            const checkBtn = document.getElementById('tm-check-btn');
            if (checkBtn) {
                checkBtn.style.display = filename.toLowerCase().includes('linkverify') ? 'none' : 'flex';
            }
            
            const removeDeadBtn = document.getElementById('tm-removedead-btn');
            if (removeDeadBtn) {
                removeDeadBtn.style.display = filename.toLowerCase().includes('token') ? 'flex' : 'none';
            }
        }
    } catch (e) {
        console.error('Load file error:', e);
    }
}

function tmUpdateTableHeader() {
    const thead = document.querySelector('.tm-table thead tr');
    if (!thead) return;
    
    const showExtraCols = tmActiveFile && (tmActiveFile.toLowerCase().includes('token') || tmActiveFile.toLowerCase().includes('valid'));
    
    thead.innerHTML = `
        <th style="width:32px"><input type="checkbox" onchange="tmSelectAll(this.checked)"></th>
        ${tmHasUsername && showExtraCols ? '<th>USER</th>' : ''}
        <th>TOKEN</th>
        ${tmHasEmail ? '<th>EMAIL</th>' : ''}
        ${tmHasUsername && showExtraCols ? '<th>HYPESQUAD</th>' : ''}
        ${showExtraCols ? '<th>STATUS</th>' : ''}
        <th style="width:80px">ACTIONS</th>
    `;
}

function tmUpdateStats() {
    const total = tmAccounts.length;
    const valid = tmAccounts.filter(a => a.status === 'valid').length;
    const invalid = tmAccounts.filter(a => a.status === 'invalid').length;
    const locked = tmAccounts.filter(a => a.status === 'locked').length;
    const unchecked = tmAccounts.filter(a => a.status === 'unchecked').length;

    document.getElementById('tm-stat-total').textContent = total;
    document.getElementById('tm-stat-valid').textContent = unchecked === total ? '—' : valid;
    document.getElementById('tm-stat-invalid').textContent = unchecked === total ? '—' : invalid;
    document.getElementById('tm-stat-locked').textContent = unchecked === total ? '—' : locked;
}

function tmGetStatusBadge(status) {
    switch (status) {
        case 'valid': return '<span class="tm-badge tm-badge-valid">Valid</span>';
        case 'invalid': return '<span class="tm-badge tm-badge-invalid">Invalid</span>';
        case 'locked': return '<span class="tm-badge tm-badge-locked">Locked</span>';
        case 'checking': return '<span class="tm-badge tm-badge-checking">⟳</span>';
        default: return '<span class="tm-badge tm-badge-unchecked">—</span>';
    }
}

function tmGetAvatarHtml(acc) {
    if (acc && acc.avatarUrl) {
        return `<img class="tm-avatar tm-avatar-img" src="${escapeHtml(acc.avatarUrl)}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="tm-avatar" style="display:none;background:#5865f2;">${((acc.username||'?')[0]).toUpperCase()}</div>`;
    }
    const colors = [
        '#5865f2','#57f287','#fee75c','#eb459e','#ed4245',
        '#3ba55c','#faa61a','#9b59b6','#e74c3c','#2ecc71',
    ];
    const name = (acc && acc.username) ? acc.username : '?';
    const letter = name[0].toUpperCase();
    const colorIdx = letter.charCodeAt(0) % colors.length;
    const bg = colors[colorIdx];
    return `<div class="tm-avatar" style="background:${bg};">${letter}</div>`;
}

function tmRenderTable() {
    const table = document.getElementById('tm-table-body');
    if (!table) return;

    let filtered = tmAccounts;

    if (tmSearchQuery) {
        const q = tmSearchQuery.toLowerCase();
        filtered = filtered.filter(a =>
            (a.username || '').toLowerCase().includes(q) ||
            (a.email || '').toLowerCase().includes(q) ||
            (a.token || '').toLowerCase().includes(q) ||
            (a.status || '').toLowerCase().includes(q)
        );
    }

    const showExtraCols = tmActiveFile && (tmActiveFile.toLowerCase().includes('token') || tmActiveFile.toLowerCase().includes('valid'));
    const colCount = 3 + (tmHasUsername && showExtraCols ? 2 : 0) + (tmHasEmail ? 1 : 0) + (showExtraCols ? 1 : 0);
    
    if (filtered.length === 0) {
        table.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;padding:40px;color:var(--text-secondary)">
            ${tmAccounts.length === 0 ? 'No accounts in this file' : 'No matching results'}
        </td></tr>`;
        return;
    }

    table.innerHTML = filtered.map((acc) => {
        const realIdx = tmAccounts.indexOf(acc);
        const shortToken = acc.token.length > 28 ? acc.token.substring(0, 26) + '...' : acc.token;

        const userCells = tmHasUsername && showExtraCols
            ? `<td class="tm-cell-user"><div style="display:flex;align-items:center;gap:8px;">${tmGetAvatarHtml(acc)}<span>${escapeHtml(acc.username || '')}</span></div></td>`
            : '';

        const emailCell = tmHasEmail
            ? `<td class="tm-cell-email" title="${escapeHtml(acc.email)}">${escapeHtml(acc.email.length > 26 ? acc.email.substring(0,24)+'...' : acc.email)}</td>`
            : '';

        const hypesquadCell = tmHasUsername && showExtraCols
            ? `<td class="tm-cell-hypesquad">${acc.hypesquad ? escapeHtml(acc.hypesquad) : '<span class="tm-badge tm-badge-unchecked">—</span>'}</td>`
            : '';
            
        const statusCell = showExtraCols
            ? `<td class="tm-cell-status">${tmGetStatusBadge(acc.status)}</td>`
            : '';

        return `<tr class="tm-row-${acc.status}">
            <td><input type="checkbox" class="tm-row-check" data-idx="${realIdx}"></td>
            ${userCells}
            <td class="tm-cell-token" title="${escapeHtml(acc.token)}">${escapeHtml(shortToken)}</td>
            ${emailCell}
            ${hypesquadCell}
            ${statusCell}
            <td class="tm-cell-actions">
                <button class="tm-action-btn tm-copy-btn" onclick="tmCopyToken(${realIdx})" title="Copy Token">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
                <button class="tm-action-btn tm-login-btn" onclick="tmLoginToken(${realIdx})" title="Login with Token">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                </button>
            </td>
        </tr>`;
    }).join('');
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text || '';
    return d.innerHTML;
}

function tmCopyToken(idx) {
    if (tmAccounts[idx]) {
        navigator.clipboard.writeText(tmAccounts[idx].token).catch(() => {});
        tmShowToast('Token copied');
    }
}

function tmCopyFull(idx) {
    if (tmAccounts[idx]) {
        navigator.clipboard.writeText(tmAccounts[idx].raw).catch(() => {});
        tmShowToast('Full line copied');
    }
}

async function tmLoginToken(idx) {
    if (!tmAccounts[idx]) return;
    const raw_line = tmAccounts[idx].raw;
    try {
        if (window.pywebview && window.pywebview.api) {
            tmShowToast('Opening browser...');
            await window.pywebview.api.login_with_token(raw_line);
        }
    } catch (e) {
        console.error('Login error:', e);
        tmShowToast('Login failed');
    }
}

function tmShowToast(msg) {
    return window.toast.info('Token Manager', msg);
}

function tmSearch(value) {
    tmSearchQuery = value;
    tmRenderTable();
}

async function tmExport(format) {
    if (!tmActiveFile) return;
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const result = await window.pywebview.api.export_tokens(tmActiveFile, format);
        if (result.success) {
            navigator.clipboard.writeText(result.data).catch(() => {});
            tmShowToast(`Exported ${result.count} tokens`);
        }
    } catch (e) {
        console.error('Export error:', e);
    }
}

// ═══════════════════ TOKEN CHECKER ═══════════════════

async function tmStartCheck() {
    if (tmChecking || tmAccounts.length === 0) return;
    tmChecking = true;

    const btn = document.getElementById('tm-check-btn');
    if (btn) btn.innerHTML = '⟳ Checking...';

    tmAccounts.forEach(a => a.status = 'checking');
    tmRenderTable();
    tmUpdateStats();

    const batchSize = 5;
    for (let i = 0; i < tmAccounts.length; i += batchSize) {
        if (!tmChecking) break;
        const batch = tmAccounts.slice(i, i + batchSize);
        const checks = batch.map(async (acc) => {
            try {
                const r = await checkSingleToken(acc.token);
                acc.status = r.status;
                if (r.username) {
                    acc.username = r.username;
                    acc.hypesquad = r.hypesquad;
                    // Once we have real usernames, show that column
                    if (!tmHasUsername) {
                        tmHasUsername = true;
                        tmUpdateTableHeader();
                    }
                }
                if (r.avatarUrl) acc.avatarUrl = r.avatarUrl;
                // Persist check results so reopening doesn't require re-checking
                tmCacheSet(acc.token, { status: acc.status, username: acc.username || '', hypesquad: acc.hypesquad || '', avatarUrl: acc.avatarUrl || '' });
            } catch (e) {
                acc.status = 'invalid';
            }
        });
        await Promise.all(checks);
        tmRenderTable();
        tmUpdateStats();
    }

    tmChecking = false;
    if (btn) btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Check`;
    tmShowToast('Check complete');
}

async function checkSingleToken(token) {
    try {
        if (!window.pywebview || !window.pywebview.api) return { status: 'invalid' };
        const result = await window.pywebview.api.check_single_token(token);
        return {
            status:    (result.success && result.status) ? result.status : 'invalid',
            username:  result.username  || '',
            avatarUrl: result.avatar_url || '',
            hypesquad: result.hypesquad || '',
        };
    } catch (e) {
        return { status: 'invalid' };
    }
}

function tmSelectAll(checked) {
    document.querySelectorAll('.tm-row-check').forEach(cb => cb.checked = checked);
}

async function tmCleanAllTxt() {
    if (tmFiles.length === 0) {
        tmShowToast('No files to clean');
        return;
    }

    const confirmed = await new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:9999;display:flex;align-items:center;justify-content:center;';
        const box = document.createElement('div');
        box.style.cssText = 'background:#161618;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:28px 32px;max-width:380px;width:90%;text-align:center;';
        box.innerHTML = `
            <div style="font-size:15px;font-weight:600;color:#f0f0f0;margin-bottom:10px;">Delete all output files?</div>
            <div style="font-size:13px;color:#888;margin-bottom:22px;">This will permanently delete all <strong style="color:#f0f0f0">${tmFiles.length}</strong> .txt file(s) from <code>data/output</code>. This action cannot be undone.</div>
            <div style="display:flex;gap:10px;justify-content:center;">
                <button id="_msk-cancel" style="padding:8px 22px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:transparent;color:#aaa;cursor:pointer;font-size:13px;">Cancel</button>
                <button id="_msk-confirm" style="padding:8px 22px;border-radius:6px;border:none;background:#dc3545;color:#fff;cursor:pointer;font-size:13px;font-weight:600;">Delete All</button>
            </div>`;
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        const cleanup = (val) => { document.body.removeChild(overlay); resolve(val); };
        box.querySelector('#_msk-cancel').onclick  = () => cleanup(false);
        box.querySelector('#_msk-confirm').onclick = () => cleanup(true);
        overlay.addEventListener('click', e => { if (e.target === overlay) cleanup(false); });
    });
    if (!confirmed) return;

    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const btn = document.getElementById('tm-clean-btn');
        if (btn) btn.innerHTML = '⟳ Cleaning...';
        const result = await window.pywebview.api.clean_all_txt_files();
        if (result.success) {
            tmShowToast(`Deleted ${result.deleted} file(s)`);
            tmActiveFile = null;
            tmAccounts = [];
            tmFiles = [];
            tmHasEmail    = false;
            tmHasUsername = false;
            try { localStorage.removeItem(TM_CACHE_KEY); } catch(e) {}
            tmUpdateStats();
            tmRenderTable();
            await tmRefreshFiles();
        } else {
            tmShowToast('Clean failed: ' + (result.error || 'Unknown error'));
        }
        if (btn) btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg> Clean All`;
    } catch (e) {
        console.error('Clean all error:', e);
        tmShowToast('Clean failed');
    }
}

async function tmRemoveDead() {
    if (!tmActiveFile) {
        tmShowToast('Select a file first');
        return;
    }

    const lockedOrInvalid = tmAccounts.filter(a => a.status === 'locked' || a.status === 'invalid');
    if (lockedOrInvalid.length === 0) {
        // If there are unchecked accounts, warn the user
        const unchecked = tmAccounts.filter(a => a.status === 'unchecked' || a.status === 'checking');
        if (unchecked.length > 0) {
            tmShowToast('Please Check tokens first!');
        } else {
            tmShowToast('No dead tokens found');
        }
        return;
    }

    const confirmed = await new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:9999;display:flex;align-items:center;justify-content:center;';
        const box = document.createElement('div');
        box.style.cssText = 'background:#161618;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:28px 32px;max-width:380px;width:90%;text-align:center;';
        box.innerHTML = `
            <div style="font-size:15px;font-weight:600;color:#f0f0f0;margin-bottom:10px;">Remove Dead Tokens?</div>
            <div style="font-size:13px;color:#888;margin-bottom:22px;">This will remove <strong style="color:#f0f0f0">${lockedOrInvalid.length}</strong> locked/invalid tokens from the file.</div>
            <div style="display:flex;gap:10px;justify-content:center;">
                <button id="_msk-cancel" style="padding:8px 22px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:transparent;color:#aaa;cursor:pointer;font-size:13px;">Cancel</button>
                <button id="_msk-confirm" style="padding:8px 22px;border-radius:6px;border:none;background:#dc3545;color:#fff;cursor:pointer;font-size:13px;font-weight:600;">Remove</button>
            </div>`;
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        const cleanup = (val) => { document.body.removeChild(overlay); resolve(val); };
        box.querySelector('#_msk-cancel').onclick  = () => cleanup(false);
        box.querySelector('#_msk-confirm').onclick = () => cleanup(true);
        overlay.addEventListener('click', e => { if (e.target === overlay) cleanup(false); });
    });
    
    if (!confirmed) return;

    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const btn = document.getElementById('tm-removedead-btn');
        if (btn) btn.innerHTML = '⟳ Removing...';
        
        // Pass the list of raw strings to keep
        const validAccounts = tmAccounts.filter(a => a.status !== 'locked' && a.status !== 'invalid');
        const linesToKeep = validAccounts.map(a => a.raw);

        const result = await window.pywebview.api.remove_dead_tokens(tmActiveFile, linesToKeep);
        if (result.success) {
            tmShowToast(`Removed dead tokens`);
            // Clean removed tokens from cache so they don't persist
            tmCacheDelete(lockedOrInvalid.map(a => a.token));
            await tmSelectFile(tmActiveFile); // Reload the file
        } else {
            tmShowToast('Remove failed: ' + (result.error || 'Unknown error'));
        }
        if (btn) btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg> Remove Dead`;
    } catch (e) {
        console.error('Remove error:', e);
        tmShowToast('Remove failed');
    }
}
