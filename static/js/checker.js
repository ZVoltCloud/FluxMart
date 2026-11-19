let isChecking = false;

// ── "File already has tokens?" dialog ─────────────────────────────────────────
function showCheckerCleanDialog(files) {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position:fixed; inset:0; background:rgba(0,0,0,0.65);
            display:flex; align-items:center; justify-content:center;
            z-index:10000;
        `;

        const fileList = files.map(f =>
            `<div style="font-size:12px; color:var(--text-muted); margin:2px 0;">
                ${f.name} — <strong style="color:var(--text);">${f.count}</strong> token${f.count !== 1 ? 's' : ''}
             </div>`
        ).join('');

        const box = document.createElement('div');
        box.style.cssText = `
            background:var(--card-bg); border-radius:12px;
            padding:14px 22px; min-width:320px; max-width:440px;
            box-shadow:0 8px 32px rgba(0,0,0,0.5);
            border:1px solid var(--border); text-align:center;
        `;
        box.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:center;margin-bottom:4px;font-size:28px;">
            </div>
            <h3 style="margin:0 0 4px; color:var(--text);">Output Files Already Have Tokens</h3>
            <p style="margin:0 0 6px; font-size:13px; color:var(--text-light);">
                The following output files already contain tokens:
            </p>
            <div style="margin-bottom:8px; text-align:left; background:var(--bg); border-radius:8px; padding:6px 12px;">
                ${fileList}
            </div>
            <p style="margin:0 0 10px; font-size:13px; color:var(--text-light);">
                Do you want to clear them before starting?<br>
                <span style="font-size:11px; opacity:0.7;">Choosing "Append" will skip duplicate tokens already in the files.</span>
            </p>
            <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
                <button id="chk-dlg-clean" style="
                    padding:9px 22px; background:var(--error); color:#fff;
                    border:none; border-radius:8px; cursor:pointer; font-size:13px; font-weight:500;">
                    Yes, Clean &amp; Start
                </button>
                <button id="chk-dlg-append" style="
                    padding:9px 22px; background:var(--primary); color:#fff;
                    border:none; border-radius:8px; cursor:pointer; font-size:13px; font-weight:500;">
                    No, Append New
                </button>
                <button id="chk-dlg-cancel" style="
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

        box.querySelector('#chk-dlg-clean').addEventListener('click', () => close('clean'));
        box.querySelector('#chk-dlg-append').addEventListener('click', () => close('append'));
        box.querySelector('#chk-dlg-cancel').addEventListener('click', () => close(null));
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
    });
}

async function startChecker() {
    if (isChecking) return;

    const textarea = document.getElementById('checker-textarea');
    const tokens = textarea.value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

    if (tokens.length === 0) {
        toast.error("Error", "No tokens loaded");
        return;
    }

    if (!window.pywebview || !window.pywebview.api) {
        toast.error("Error", "Application not ready");
        return;
    }

    // Check if output files already have tokens
    let cleanOld = false;
    if (window.hasOperationFinished) {
        try {
            const fileCheck = await window.pywebview.api.check_checker_files();
            const existingFiles = fileCheck.files
                ? fileCheck.files.filter(f => f.count > 0)
                : [];

            if (existingFiles.length > 0) {
                const choice = await showCheckerCleanDialog(existingFiles);
                if (choice === null) return;
                cleanOld = (choice === 'clean');
            }
        } catch (e) {
            // If check fails, proceed without cleaning
        }
    }

    try {
        isChecking = true;
        // Reset clear flag so stats display works again
        window._checkerStatsCleared = false;

        document.getElementById('checker-start-btn').disabled = true;
        document.getElementById('checker-stop-btn').disabled = false;
        const clearBtn = document.getElementById('checker-clear-btn');
        if (clearBtn) clearBtn.disabled = true;

        document.getElementById('checker-valid').textContent = '0';
        document.getElementById('checker-locked').textContent = '0';
        document.getElementById('checker-invalid').textContent = '0';
        document.getElementById('checker-progress').style.width = '0%';
        document.getElementById('checker-progress-text').textContent = '0/' + tokens.length;

        const result = await window.pywebview.api.start_checker(tokens, cleanOld);
        if (result.success) {
            addLog("[Msk] Checking " + tokens.length + " tokens...", "info");
            toast.success("Started", "Token checker started");
        } else {
            addLog("[Msk] Failed: " + (result.error || ""), "error");
            toast.error("Error", result.error || "Failed to start checker");
            stopCheckerUI();
        }
    } catch (e) {
        addLog("[Msk] Error: " + e.message, "error");
        toast.error("Error", e.message);
        stopCheckerUI();
    }
}

async function stopChecker() {
    try {
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.stop_checker();
        }
        addLog("[Msk] Checker stopped", "warning");
    } catch (e) { }
    stopCheckerUI();
}

function stopCheckerUI() {
    isChecking = false;
    document.getElementById('checker-start-btn').disabled = false;
    document.getElementById('checker-stop-btn').disabled = true;
    const clearBtn = document.getElementById('checker-clear-btn');
    if (clearBtn) clearBtn.disabled = false;
    window.hasOperationFinished = true;
}

async function clearCheckerInput() {
    // Set the cleared flag so fetchStats() won't re-populate checker panel
    window._checkerStatsCleared = true;

    const textarea = document.getElementById('checker-textarea');
    if (textarea) textarea.value = '';
    const fileInfo = document.getElementById('checker-file-info');
    if (fileInfo) fileInfo.textContent = 'No file selected';
    const fileInput = document.getElementById('checker-file');
    if (fileInput) fileInput.value = '';

    // Reset stats display
    document.getElementById('checker-valid').textContent = '0';
    document.getElementById('checker-locked').textContent = '0';
    document.getElementById('checker-invalid').textContent = '0';
    document.getElementById('checker-progress').style.width = '0%';
    document.getElementById('checker-progress-text').textContent = '0/0';

    // Reset backend stats too
    try {
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.reset_checker_stats();
        }
    } catch (e) {}

    toast.info("Cleared", "Input and stats cleared");
}

window.startChecker = startChecker;
window.stopChecker = stopChecker;
window.stopCheckerUI = stopCheckerUI;
window.clearCheckerInput = clearCheckerInput;
