// ── Token Splitter ─────────────────────────────────────────────────
let _splitterLines = [];

// ── Drag & Drop wiring ────────────────────────────────────────────
(function initSplitterDragDrop() {
    document.addEventListener('DOMContentLoaded', () => {
        const area = document.getElementById('splitter-drag-area');
        const fileInput = document.getElementById('splitter-file');
        if (!area || !fileInput) return;

        area.addEventListener('click', () => fileInput.click());

        area.addEventListener('dragover', e => {
            e.preventDefault();
            area.classList.add('drag-over');
        });
        area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
        area.addEventListener('drop', e => {
            e.preventDefault();
            area.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) loadSplitterFile(file);
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) loadSplitterFile(fileInput.files[0]);
        });
    });
})();

function loadSplitterFile(file) {
    const info = document.getElementById('splitter-file-info');
    if (info) info.textContent = 'Loading: ' + file.name;
    const reader = new FileReader();
    reader.onload = e => {
        const textarea = document.getElementById('splitter-textarea');
        if (textarea) textarea.value = e.target.result;
        if (info) info.textContent = file.name + ' (' + file.size.toLocaleString() + ' bytes)';
        setSplitterStatus('File loaded: ' + file.name, 'success');
    };
    reader.readAsText(file, 'utf-8');
}

function clearSplitterInput() {
    const ta = document.getElementById('splitter-textarea');
    if (ta) ta.value = '';
    const fi = document.getElementById('splitter-file-info');
    if (fi) fi.textContent = 'No file selected';
    setSplitterStatus('', '');
    setSplitterStats(0, 0, 0, 0, 0);
}

// ── Main entry point ──────────────────────────────────────────────
async function startSplitter() {
    const textarea = document.getElementById('splitter-textarea');
    const raw = (textarea ? textarea.value : '').trim();
    if (!raw) {
        window.toast.error('Splitter', 'No tokens provided');
        return;
    }

    const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) {
        window.toast.error('Splitter', 'No valid lines found');
        return;
    }

    if (!window.pywebview || !window.pywebview.api) {
        window.toast.error('Splitter', 'Application not ready');
        return;
    }

    setSplitterStatus('Checking output file...', 'info');

    // Check if file already has tokens
    let cleanOld = false;

    if (window.hasOperationFinished) {
        let fileInfo;
        try {
            fileInfo = await window.pywebview.api.check_splitter_file();
        } catch (e) {
            fileInfo = { exists: false, count: 0 };
        }

        if (fileInfo.exists && fileInfo.count > 0) {
            // Show the clean dialog
            cleanOld = await showSplitterCleanDialog(fileInfo.count);
            if (cleanOld === null) {
                // User cancelled
                setSplitterStatus('Cancelled.', 'info');
                return;
            }
        }
    }

    await runSplitter(lines, cleanOld);
}

async function runSplitter(lines, cleanOld) {
    const btn = document.getElementById('splitter-start-btn');
    if (btn) btn.disabled = true;
    const stopBtn = document.getElementById('splitter-stop-btn');
    if (stopBtn) stopBtn.disabled = false;
    const clearBtn = document.getElementById('splitter-clear-btn');
    if (clearBtn) clearBtn.disabled = true;
    
    setSplitterStatus('Splitting tokens...', 'info');
    setSplitterStats(0, 0, 0, lines.length, 0);

    // Animate progress bar to show activity
    const bar = document.getElementById('splitter-progress');
    if (bar) bar.style.width = '30%';

    try {
        const result = await window.pywebview.api.split_tokens(lines, cleanOld);

        if (bar) bar.style.width = '100%';

        if (result.success) {
            setSplitterStats(result.saved, result.duplicates, result.skipped, lines.length, result.total_in_file);
            const pathEl = document.getElementById('splitter-output-path');
            if (pathEl) pathEl.textContent = 'Saved to: ' + result.path;

            const msg = result.saved + ' tokens saved' +
                (result.duplicates > 0 ? ', ' + result.duplicates + ' duplicates skipped' : '') +
                (result.skipped > 0 ? ', ' + result.skipped + ' invalid lines' : '') +
                (cleanOld ? ' (file cleared first)' : ' (appended)');

            setSplitterStatus(msg, 'success');
            window.toast.success('Splitter', result.saved + ' tokens saved to tokenSplited.txt');
        } else {
            setSplitterStatus('Error: ' + result.error, 'error');
            window.toast.error('Splitter', result.error || 'Failed');
            if (bar) bar.style.width = '0%';
        }
    } catch (e) {
        if (bar) bar.style.width = '0%';
        setSplitterStatus('Error: ' + e, 'error');
        window.toast.error('Splitter', String(e));
    } finally {
        if (btn) btn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        const clearBtn = document.getElementById('splitter-clear-btn');
        if (clearBtn) clearBtn.disabled = false;
        window.hasOperationFinished = true;
    }
}

// ── Clean dialog ──────────────────────────────────────────────────
function showSplitterCleanDialog(existingCount) {
    return new Promise(resolve => {
        // Build modal overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position:fixed; inset:0; background:rgba(0,0,0,0.65);
            display:flex; align-items:center; justify-content:center;
            z-index:10000;
        `;

        const box = document.createElement('div');
        box.style.cssText = `
            background:var(--card-bg); border-radius:12px;
            padding:28px 32px; min-width:320px; max-width:420px;
            box-shadow:0 8px 32px rgba(0,0,0,0.5);
            border:1px solid var(--border); text-align:center;
        `;

        box.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:center;margin-bottom:4px;font-size:28px;">
            </div>
            <h3 style="margin:0 0 4px; color:var(--text);">File Already Has Tokens</h3>
            <p style="margin:0 0 10px; font-size:13px; color:var(--text-light);">
                <strong>tokenSplited.txt</strong> already contains <strong>${existingCount}</strong> token${existingCount !== 1 ? 's' : ''}.<br>
                Do you want to clear the old tokens before saving the new ones?
            </p>
            <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
                <button id="splitter-dlg-clean" style="
                    padding:9px 22px; background:var(--error); color:#fff;
                    border:none; border-radius:8px; cursor:pointer; font-size:13px; font-weight:500;">
                    Yes, Clean &amp; Replace
                </button>
                <button id="splitter-dlg-append" style="
                    padding:9px 22px; background:var(--primary); color:#fff;
                    border:none; border-radius:8px; cursor:pointer; font-size:13px; font-weight:500;">
                    No, Append New
                </button>
                <button id="splitter-dlg-cancel" style="
                    padding:9px 22px; background:var(--border); color:var(--text);
                    border:none; border-radius:8px; cursor:pointer; font-size:13px;">
                    Cancel
                </button>
            </div>
        `;

        overlay.appendChild(box);
        document.body.appendChild(overlay);

        function close(val) {
            document.body.removeChild(overlay);
            resolve(val);
        }

        box.querySelector('#splitter-dlg-clean').addEventListener('click', () => close(true));
        box.querySelector('#splitter-dlg-append').addEventListener('click', () => close(false));
        box.querySelector('#splitter-dlg-cancel').addEventListener('click', () => close(null));
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
    });
}

// ── Stats helpers ─────────────────────────────────────────────────
function setSplitterStats(saved, dupes, skipped, total, inFile) {
    const el = id => document.getElementById(id);
    if (el('splitter-saved'))   el('splitter-saved').textContent   = saved;
    if (el('splitter-dupes'))   el('splitter-dupes').textContent   = dupes;
    if (el('splitter-skipped')) el('splitter-skipped').textContent = skipped;
    const pct = total > 0 ? Math.round(((saved + dupes + skipped) / total) * 100) : 0;
    const bar = el('splitter-progress');
    if (bar) bar.style.width = pct + '%';
    const txt = el('splitter-progress-text');
    if (txt) txt.textContent = (saved + dupes + skipped) + '/' + total;
}

function setSplitterStatus(msg, type) {
    const el = document.getElementById('splitter-status-msg');
    if (!el) return;
    el.textContent = msg;
    el.style.color = type === 'success' ? 'var(--success)'
        : type === 'error' ? 'var(--error)'
        : 'var(--text-light)';
}

function stopSplitter() {
    const btn = document.getElementById('splitter-start-btn');
    if (btn) btn.disabled = false;
    const stopBtn = document.getElementById('splitter-stop-btn');
    if (stopBtn) stopBtn.disabled = true;
    
    const bar = document.getElementById('splitter-progress');
    if (bar) bar.style.width = '0%';
    
    setSplitterStatus('Splitter stopped', 'info');
    toast.info("Stopped", "Splitter process stopped");
}

window.startSplitter = startSplitter;
window.stopSplitter = stopSplitter;
window.clearSplitterInput = clearSplitterInput;
