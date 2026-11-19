let isGenerating = false;
let _genPollInterval = null;
let _genPollErrors = 0;
let _genStartTime = 0;
let _genStopUnconfirmed = false;
let _genStopRequestPending = false;
const _GEN_MAX_POLL_ERRORS = 5;
// Grace period in ms: don't trigger stopGeneratorUI() from poll during warmup.
// Prevents instant UI revert when thread is still initializing.
const _GEN_GRACE_MS = 6000;

async function startGenerator() {
    if (isGenerating) return;

    window._dashActiveTimeMs = 0;
    window._dashLastTick = Date.now();
    window._dashSessionTokens = 0;
    window._dashLastTotal = 0;

    const tokenCount = Number(document.getElementById('gen-token-count').value) || 1;
    const threads = Number(document.getElementById('gen-threads').value) || 1;
    const headless = document.getElementById('gen-headless').checked;
    const autoCaptcha = document.getElementById('gen-auto-captcha').checked;

    if (!window.pywebview || !window.pywebview.api) {
        toast.error("Error", "Application not ready");
        return;
    }

    const startBtn = document.getElementById('gen-start-btn');
    const stopBtn  = document.getElementById('gen-stop-btn');
    const clearBtn = document.getElementById('gen-clear-btn');

    // Show loading state immediately so the button doesn't look frozen
    // while pywebview is talking to the backend (can take 1-3s)
    const _origStartText = startBtn ? startBtn.innerHTML : '';
    if (startBtn) { startBtn.disabled = true; startBtn.innerHTML = '⟳ Starting...'; }
    if (stopBtn)  stopBtn.disabled = true;
    if (clearBtn) clearBtn.disabled = true;

    try {
        isGenerating = true;
        window._genStatsCleared = false;

        document.getElementById('gen-valid').textContent = '0';
        document.getElementById('gen-locked').textContent = '0';
        document.getElementById('gen-invalid').textContent = '0';
        document.getElementById('gen-progress').style.width = '0%';
        document.getElementById('gen-progress-text').textContent = '0/' + tokenCount;

        const result = await window.pywebview.api.start_generator(tokenCount, threads, headless, autoCaptcha);

        if (result.success) {
            // Restore start label, lock UI in "running" state
            if (startBtn) { startBtn.innerHTML = _origStartText; startBtn.disabled = true; }
            if (stopBtn)  stopBtn.disabled = false;

            addLog("[Msk] Generator started: " + tokenCount + " tokens, " + threads + " threads", "success");
            toast.success("Started", "Token generation started");

            _genStartTime = Date.now();
            _genPollErrors = 0;
            if (_genPollInterval) clearInterval(_genPollInterval);
            _genPollInterval = setInterval(_pollGeneratorStats, 1500);
        } else {
            addLog("[Msk] Failed to start: " + (result.error || "Unknown error"), "error");
            toast.error("Error", result.error || "Failed to start generator");
            if (startBtn) startBtn.innerHTML = _origStartText;
            stopGeneratorUI();
        }
    } catch (e) {
        addLog("[Msk] Error starting generator: " + e.message, "error");
        toast.error("Error", e.message);
        if (startBtn) startBtn.innerHTML = _origStartText;
        stopGeneratorUI();
    }
}

async function _pollGeneratorStats() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const stats = await window.pywebview.api.get_stats();
        if (!stats) return;

        const el = id => document.getElementById(id);
        if (el('gen-valid'))   el('gen-valid').textContent   = stats.valid   || 0;
        if (el('gen-locked'))  el('gen-locked').textContent  = stats.locked  || 0;
        if (el('gen-invalid')) el('gen-invalid').textContent = stats.invalid || 0;

        const done  = (stats.valid || 0) + (stats.locked || 0) + (stats.invalid || 0);
        const total = stats.total || Number(document.getElementById('gen-token-count').value) || 0;
        if (total > 0) {
            const pct = Math.min(100, Math.round((done / total) * 100));
            if (el('gen-progress'))      el('gen-progress').style.width      = pct + '%';
            if (el('gen-progress-text')) el('gen-progress-text').textContent = `${done}/${total}`;
        }

        // Only check for completion after the grace period.
        // Without this, a thread that's still warming up looks "stopped"
        // and the UI reverts to Start state immediately.
        const pastGrace = (Date.now() - _genStartTime) > _GEN_GRACE_MS;
        if (pastGrace && stats.running === false && isGenerating && !_genStopUnconfirmed) {
            stopGeneratorUI();
            showToast('Generation complete!', 'success');
        }
        _genPollErrors = 0;
    } catch (e) {
        _genPollErrors++;
        if (_genPollErrors === _GEN_MAX_POLL_ERRORS) {
            _genStopUnconfirmed = true;
            addLog("[Msk] Connection lost. Task shutdown cannot be confirmed; Start remains disabled.", "error");
        }
    }
}

async function stopGenerator() {
    if (_genStopRequestPending) return;
    _genStopRequestPending = true;
    const startBtn = document.getElementById('gen-start-btn');
    const stopBtn = document.getElementById('gen-stop-btn');
    const clearBtn = document.getElementById('gen-clear-btn');
    if (stopBtn) { stopBtn.disabled = true; stopBtn.textContent = 'Stopping...'; }
    try {
        if (!window.pywebview || !window.pywebview.api) {
            throw new Error('Backend unavailable.');
        }
        const result = await window.pywebview.api.stop_generator();
        if (!result || result.success !== true) {
            throw new Error((result && result.error) || 'Stop request failed.');
        }
        if (result.stopped) {
            // Backend confirmed all threads have exited
            addLog("[Msk] Generator stopped", "warning");
            toast.warning("Stopped", "All tasks stopped successfully");
            _genStopUnconfirmed = false;
            stopGeneratorUI();
        } else {
            // Backend sent stop signal but threads are still running
            _genStopUnconfirmed = true;
            addLog("[Msk] Stop requested. Some tasks may still be finishing.", "warning");
            toast.warning("Stopping", "Tasks are being stopped...");
            // Keep polling - the poll will detect running=false and call stopGeneratorUI
        }
    } catch (e) {
        const message = e && e.message ? e.message : 'Stop request failed.';
        _genStopUnconfirmed = true;
        addLog("[Msk] " + message, "error");
        toast.error("Error", message);
    } finally {
        _genStopRequestPending = false;
        // Only update stop button if we didn't already reset via stopGeneratorUI
        if (_genStopUnconfirmed && stopBtn) {
            stopBtn.disabled = false;
            stopBtn.textContent = 'Retry Stop';
        }
    }
}

function stopGeneratorUI() {
    // Allow reset when: natural completion (running=false), or backend confirmed stop
    if (_genStopUnconfirmed) return;
    if (_genPollInterval) {
        clearInterval(_genPollInterval);
        _genPollInterval = null;
    }
    isGenerating = false;
    _genStartTime = 0;
    const startBtn = document.getElementById('gen-start-btn');
    const stopBtn  = document.getElementById('gen-stop-btn');
    const clearBtn = document.getElementById('gen-clear-btn');
    if (startBtn) { startBtn.disabled = false; }
    if (stopBtn)  stopBtn.disabled = true;
    if (clearBtn) clearBtn.disabled = false;
    window.hasOperationFinished = true;
}

async function clearGeneratorStats() {
    if (isGenerating) return;

    // Set the cleared flag so fetchStats() won't re-populate
    window._genStatsCleared = true;
    window._dashActiveTimeMs = 0;
    window._dashLastTick = Date.now();
    window._dashSessionTokens = 0;
    window._dashLastTotal = 0;

    document.getElementById('gen-valid').textContent = '0';
    document.getElementById('gen-locked').textContent = '0';
    document.getElementById('gen-invalid').textContent = '0';
    document.getElementById('gen-progress').style.width = '0%';
    document.getElementById('gen-progress-text').textContent = '0/0';

    // Reset backend stats too so they stay at 0
    try {
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.reset_stats();
        }
    } catch (e) {}

    toast.info("Cleared", "Generator stats cleared");
}

window.startGenerator = startGenerator;
window.stopGenerator = stopGenerator;
window.stopGeneratorUI = stopGeneratorUI;
window.clearGeneratorStats = clearGeneratorStats;
