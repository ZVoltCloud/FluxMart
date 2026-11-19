/* ===== Verifier Page Logic ===== */

let verifierTokens = [];
let verifierInterval = null;
let _verifierRunning = false;
let _verifierPollErrors = 0;
const MAX_POLL_ERRORS = 5;

document.addEventListener('DOMContentLoaded', () => {
    initVerifierDragDrop();
    loadVerifierCaptchaSettings();
});

function initVerifierDragDrop() {
    setupDragDrop(
        'verifier-drag-area',
        'verifier-file',
        (files) => {
            const file = files[0];
            if (!file) return;

            document.getElementById('verifier-file-info').textContent = file.name;

            const reader = new FileReader();
            reader.onload = (e) => {
                const text = e.target.result;
                const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l);
                verifierTokens = lines;
                showToast(`Loaded ${lines.length} tokens from file.`, 'success');
            };
            reader.readAsText(file);
        }
    );
}

function clearVerifierInput() {
    document.getElementById('verifier-textarea').value = '';
    document.getElementById('verifier-file').value = '';
    document.getElementById('verifier-file-info').textContent = 'No file selected';
    verifierTokens = [];
    _setVerifierProgress(0, 0);
    document.getElementById('verifier-success').textContent = '0';
    document.getElementById('verifier-failed').textContent = '0';
    const logsEl = document.getElementById('verifier-logs');
    if (logsEl) logsEl.innerHTML = '';
}

function _setVerifierProgress(current, total) {
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const progressEl = document.getElementById('verifier-progress');
    const textEl = document.getElementById('verifier-progress-text');
    if (progressEl) progressEl.style.width = `${pct}%`;
    if (textEl) textEl.textContent = `${current}/${total}`;
}

async function startVerifier() {
    if (_verifierRunning) return;

    const textTokens = (document.getElementById('verifier-textarea').value || '')
        .split('\n')
        .map(l => l.trim())
        .filter(l => l);

    const allTokens = [...new Set([...verifierTokens, ...textTokens])];

    if (allTokens.length === 0) {
        showToast('Please provide tokens to verify.', 'error');
        return;
    }

    // Validate that every line matches mail:pass:token format
    const badLines = allTokens.filter(line => (line.match(/:/g) || []).length < 2);
    if (badLines.length > 0) {
        showToast(
            `Invalid format on ${badLines.length} line(s). Required: email:password:token`,
            'error',
            6000
        );
        return;
    }

    let mode = 'check';
    document.getElementsByName('verifier-mode').forEach(radio => {
        if (radio.checked) mode = radio.value;
    });

    const threads = Math.min(4, Math.max(1, parseInt(document.getElementById('verifier-threads').value) || 1));
    const headless = document.getElementById('verifier-headless').checked;

    // No MskSolver settings to save anymore
    
    _verifierRunning = true;
    _verifierPollErrors = 0;
    updateVerifierUIState(true);

    try {
        const result = await window.pywebview.api.start_verifier(allTokens, mode, threads, headless);
        if (!result || !result.success) {
            const errMsg = (result && result.error) ? result.error : 'Failed to start verifier';
            showToast(errMsg, 'error');
            _verifierRunning = false;
            updateVerifierUIState(false);
            return;
        }

        showToast('Verifier started!', 'success');
        const logsEl = document.getElementById('verifier-logs');
        if (logsEl) logsEl.innerHTML = '';
        _appendVerifierLog('Verifier started...', 'info');

        if (verifierInterval) clearInterval(verifierInterval);
        verifierInterval = setInterval(pollVerifierStats, 1000);

    } catch (e) {
        showToast('Error starting verifier: ' + e, 'error');
        _verifierRunning = false;
        updateVerifierUIState(false);
    }
}

async function stopVerifier() {
    if (!_verifierRunning) return;
    try {
        await window.pywebview.api.stop_verifier();
        showToast('Stopping verifier...', 'info');
        const stopBtn = document.getElementById('verifier-stop-btn');
        if (stopBtn) {
            stopBtn.disabled = true;
            stopBtn.textContent = 'Stopping...';
        }
    } catch (e) {
        showToast('Error stopping verifier', 'error');
    }
}

function updateVerifierUIState(running) {
    const startBtn = document.getElementById('verifier-start-btn');
    const stopBtn = document.getElementById('verifier-stop-btn');
    if (startBtn) startBtn.disabled = running;
    if (stopBtn) {
        stopBtn.disabled = !running;
        stopBtn.textContent = 'Stop';
    }

    const textarea = document.getElementById('verifier-textarea');
    const fileInput = document.getElementById('verifier-file');
    const threadsInput = document.getElementById('verifier-threads');
    const headlessInput = document.getElementById('verifier-headless');
    if (textarea) textarea.disabled = running;
    if (fileInput) fileInput.disabled = running;
    if (threadsInput) threadsInput.disabled = running;
    if (headlessInput) headlessInput.disabled = running;
    document.getElementsByName('verifier-mode').forEach(radio => { radio.disabled = running; });
}

function _appendVerifierLog(message, type) {
    const container = document.getElementById('verifier-logs');
    if (!container) return;

    const div = document.createElement('div');
    div.className = `verifier-log-entry ${type || 'info'}`;

    const timeSpan = document.createElement('span');
    timeSpan.className = 'log-time';
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    timeSpan.textContent = `[${hh}:${mm}:${ss}] `;

    div.appendChild(timeSpan);
    div.appendChild(document.createTextNode(message));
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

async function _flushVerifierLogs() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const logResult = await window.pywebview.api.get_verifier_logs();
        if (logResult && logResult.logs && logResult.logs.length > 0) {
            logResult.logs.forEach(log => _appendVerifierLog(log.message, log.type));
        }
    } catch (e) {
        /* silent */
    }
}

async function pollVerifierStats() {
    if (!window.pywebview || !window.pywebview.api) return;

    // Always flush logs first, independently — so logs show even if stats fail
    await _flushVerifierLogs();

    try {
        const result = await window.pywebview.api.get_verifier_stats();
        if (result) {
            const success = result.success || 0;
            const failed = result.failed || 0;
            const total = result.total || 0;
            const current = result.current || 0;

            const successEl = document.getElementById('verifier-success');
            const failedEl = document.getElementById('verifier-failed');
            if (successEl) successEl.textContent = success;
            if (failedEl) failedEl.textContent = failed;
            _setVerifierProgress(current, total);
        }

        _verifierPollErrors = 0;

        // Check if finished
        if (result && !result.running && _verifierRunning) {
            // Do one final log flush before stopping
            await _flushVerifierLogs();
            _verifierRunning = false;
            if (verifierInterval) {
                clearInterval(verifierInterval);
                verifierInterval = null;
            }
            updateVerifierUIState(false);
            showToast('Verifier finished!', 'success');
            _appendVerifierLog('--- Verifier finished ---', 'info');
        }

    } catch (e) {
        _verifierPollErrors++;
        console.warn(`Verifier poll error (${_verifierPollErrors}):`, e);

        if (_verifierPollErrors >= MAX_POLL_ERRORS) {
            // Too many errors in a row - assume verifier crashed/stopped
            _verifierRunning = false;
            if (verifierInterval) {
                clearInterval(verifierInterval);
                verifierInterval = null;
            }
            updateVerifierUIState(false);
            _appendVerifierLog('Lost connection to verifier backend', 'error');
            showToast('Verifier connection lost', 'error');
        }
    }
}
