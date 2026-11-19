// ─── Avatar management ────────────────────────────────────────────────────────

let selectedAvatars = new Set();

async function loadAvatarsFromBackend() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const result = await window.pywebview.api.get_avatars();
        if (result && result.avatars) {
            renderAvatarGrid(result.avatars);
        }
    } catch (e) {
        console.error("Failed to load avatars:", e);
    }
}

function renderAvatarGrid(avatars) {
    const grid = document.getElementById('avatar-grid');
    if (!grid) return;

    grid.innerHTML = '';

    if (!avatars || avatars.length === 0) {
        grid.innerHTML = '<div class="avatar-loading">No avatar images found. Add images to data/input/profiles/avatars/</div>';
        return;
    }

    avatars.forEach(avatar => {
        const item = document.createElement('div');
        item.className = 'avatar-item selected';
        item.dataset.filename = avatar.filename;
        selectedAvatars.add(avatar.filename);

        const img = document.createElement('img');
        img.src = avatar.data;
        img.alt = avatar.filename;
        img.loading = 'lazy';

        item.appendChild(img);
        item.addEventListener('click', () => toggleAvatar(item, avatar.filename));
        grid.appendChild(item);
    });
}

function toggleAvatar(item, filename) {
    if (selectedAvatars.has(filename)) {
        selectedAvatars.delete(filename);
        item.classList.remove('selected');
    } else {
        selectedAvatars.add(filename);
        item.classList.add('selected');
    }
    saveSelectedAvatars();
}

function selectAllAvatars() {
    document.querySelectorAll('.avatar-item').forEach(item => {
        item.classList.add('selected');
        selectedAvatars.add(item.dataset.filename);
    });
    saveSelectedAvatars();
    toast.success("All Selected", selectedAvatars.size + " avatars selected");
}

function deselectAllAvatars() {
    document.querySelectorAll('.avatar-item').forEach(item => {
        item.classList.remove('selected');
    });
    selectedAvatars.clear();
    saveSelectedAvatars();
    toast.info("Deselected", "All avatars deselected");
}

function refreshAvatars() {
    loadAvatarsFromBackend();
    toast.info("Refreshed", "Avatar list refreshed");
}

async function saveSelectedAvatars() {
    try {
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.save_selected_avatars(Array.from(selectedAvatars));
        }
    } catch (e) {}
}

// ─── Existed Tokens / Humanizer runner ───────────────────────────────────────

let _humanizerPollTimer = null;
let _humanizerPollErrors = 0;
const _HUM_MAX_POLL_ERRORS = 5;

function clearHumanizerInput() {
    const ta = document.getElementById('humanizer-textarea');
    const fi = document.getElementById('humanizer-file-info');
    const fileInput = document.getElementById('humanizer-file');
    if (ta) ta.value = '';
    if (fi) fi.textContent = 'No file selected';
    if (fileInput) fileInput.value = '';
}

function _getHumanizerTokens() {
    const ta = document.getElementById('humanizer-textarea');
    const raw = ta ? ta.value.trim() : '';
    return raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
}

async function startHumanizer() {
    const tokens = _getHumanizerTokens();
    if (tokens.length === 0) {
        toast.warning("No Tokens", "Please add tokens to humanize.");
        return;
    }

    try {
        const result = await window.pywebview.api.start_humanizer(tokens);
        if (!result.success) {
            toast.error("Error", result.error || "Could not start humanizer.");
            return;
        }
    } catch (e) {
        toast.error("Error", String(e));
        return;
    }

    document.getElementById('humanizer-start-btn').disabled = true;
    document.getElementById('humanizer-stop-btn').disabled = false;
    const clearBtn = document.getElementById('humanizer-clear-btn');
    if (clearBtn) clearBtn.disabled = true;
    document.getElementById('humanizer-status-msg').textContent = 'Humanizing...';
    document.getElementById('humanizer-output-path').textContent = '';

    _resetHumanizerStats();
    _startHumanizerPoll();
}

async function stopHumanizer() {
    try {
        await window.pywebview.api.stop_humanizer();
    } catch (e) {}
    _stopHumanizerPoll();
    document.getElementById('humanizer-start-btn').disabled = false;
    document.getElementById('humanizer-stop-btn').disabled = true;
    const clearBtn = document.getElementById('humanizer-clear-btn');
    if (clearBtn) clearBtn.disabled = false;
    document.getElementById('humanizer-status-msg').textContent = 'Stopped.';
    window.hasOperationFinished = true;
}

function _resetHumanizerStats() {
    ['humanizer-success', 'humanizer-failed', 'humanizer-skipped'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '0';
    });
    const prog = document.getElementById('humanizer-progress');
    if (prog) prog.style.width = '0%';
    const progTxt = document.getElementById('humanizer-progress-text');
    if (progTxt) progTxt.textContent = '0/0';
}

function _startHumanizerPoll() {
    _stopHumanizerPoll();
    _humanizerPollTimer = setInterval(_pollHumanizerStats, 800);
}

function _stopHumanizerPoll() {
    if (_humanizerPollTimer) {
        clearInterval(_humanizerPollTimer);
        _humanizerPollTimer = null;
    }
}

async function _pollHumanizerStats() {
    try {
        const s = await window.pywebview.api.get_humanizer_stats();
        if (!s) return;

        const total   = s.total   || 0;
        const current = s.current || 0;
        const success = s.success || 0;
        const failed  = s.failed  || 0;
        const skipped = s.skipped || 0;

        const el = (id) => document.getElementById(id);
        if (el('humanizer-success')) el('humanizer-success').textContent = success;
        if (el('humanizer-failed'))  el('humanizer-failed').textContent  = failed;
        if (el('humanizer-skipped')) el('humanizer-skipped').textContent = skipped;
        if (el('humanizer-progress-text')) el('humanizer-progress-text').textContent = `${current}/${total}`;

        const pct = total > 0 ? Math.round((current / total) * 100) : 0;
        if (el('humanizer-progress')) el('humanizer-progress').style.width = pct + '%';

        // Done?
        if ((total > 0 && current >= total) || s.running === false) {
            const elStart = el('humanizer-start-btn');
            const elStop = el('humanizer-stop-btn');
            const elClear = el('humanizer-clear-btn');
            const elMsg = el('humanizer-status-msg');
            const elOut = el('humanizer-output-path');

            _stopHumanizerPoll();
            if (elStart) elStart.disabled = false;
            if (elStop)  elStop.disabled  = true;
            if (elClear) elClear.disabled = false;
            window.hasOperationFinished = true;
            if (elMsg) elMsg.textContent =
                `Done! ${success} humanized, ${failed} failed, ${skipped} skipped`;
            if (elOut) elOut.textContent = 'Saved to data/output/humanized.txt';
        }
        _humanizerPollErrors = 0;
    } catch (e) {
        _humanizerPollErrors++;
        if (_humanizerPollErrors >= _HUM_MAX_POLL_ERRORS) {
            _stopHumanizerPoll();
            const elStart = document.getElementById('humanizer-start-btn');
            const elStop  = document.getElementById('humanizer-stop-btn');
            const elClear = document.getElementById('humanizer-clear-btn');
            const elMsg   = document.getElementById('humanizer-status-msg');
            if (elStart) elStart.disabled = false;
            if (elStop)  elStop.disabled  = true;
            if (elClear) elClear.disabled = false;
            if (elMsg)   elMsg.textContent = 'Connection lost — humanizer may have crashed.';
            window.hasOperationFinished = true;
        }
    }
}

// ─── Drag & Drop for Humanizer token file ────────────────────────────────────

(function () {
    function setupHumanizerDragDrop() {
        const area     = document.getElementById('humanizer-drag-area');
        const fileInp  = document.getElementById('humanizer-file');
        const fileInfo = document.getElementById('humanizer-file-info');
        const textarea = document.getElementById('humanizer-textarea');
        if (!area) return;

        area.addEventListener('click', (e) => {
            if (e.target !== fileInp) fileInp.click();
        });

        fileInp.addEventListener('change', () => {
            const file = fileInp.files[0];
            if (!file) return;
            fileInfo.textContent = file.name;
            const reader = new FileReader();
            reader.onload = (ev) => { if (textarea) textarea.value = ev.target.result; };
            reader.readAsText(file);
        });

        area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('drag-over'); });
        area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (!file) return;
            fileInfo.textContent = file.name;
            const reader = new FileReader();
            reader.onload = (ev) => { if (textarea) textarea.value = ev.target.result; };
            reader.readAsText(file);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupHumanizerDragDrop);
    } else {
        setupHumanizerDragDrop();
    }
})();

// ─── Exports ─────────────────────────────────────────────────────────────────

window.loadAvatarsFromBackend = loadAvatarsFromBackend;
window.selectAllAvatars = selectAllAvatars;
window.deselectAllAvatars = deselectAllAvatars;
window.refreshAvatars = refreshAvatars;
window.startHumanizer = startHumanizer;
window.stopHumanizer = stopHumanizer;
window.clearHumanizerInput = clearHumanizerInput;
