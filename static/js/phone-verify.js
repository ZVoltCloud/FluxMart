// ─── Phone Verify Tab ──────────────────────────────────────────────────────────
let isPhoneVerifying = false;
let _pvStatsCleared = false;
window._pvStatsCleared = false;

// ── Provider switching ────────────────────────────────────────────────────────
function pvSwitchProvider() {
    const sel = document.getElementById('pv-provider');
    if (!sel) return;
    const provider = sel.value;

    // Hide all provider config panels
    document.querySelectorAll('.pv-provider-config').forEach(el => {
        el.style.display = 'none';
    });

    // Show selected
    const target = document.getElementById('pv-config-' + provider);
    if (target) target.style.display = 'block';
}

// ── Check balance ─────────────────────────────────────────────────────────────
async function pvCheckBalance() {
    const provider = document.getElementById('pv-provider')?.value || 'fivesim';
    let apiKey = '';

    if (provider === 'fivesim') {
        apiKey = document.getElementById('pv-fivesim-key')?.value?.trim() || '';
    } else if (provider === 'onlinesim') {
        apiKey = document.getElementById('pv-onlinesim-key')?.value?.trim() || '';
    } else if (provider === 'hero_sms') {
        apiKey = document.getElementById('pv-hero_sms-key')?.value?.trim() || '';
    }

    if (!apiKey) {
        toast.error('Missing Key', 'Please enter your API key first.');
        return;
    }

    const btn = document.getElementById('pv-check-balance-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Checking...'; }

    try {
        if (!window.pywebview?.api?.pv_check_balance) {
            toast.error('Error', 'Backend not ready');
            return;
        }
        const result = await window.pywebview.api.pv_check_balance(provider, apiKey);
        if (result.success) {
            toast.success('Balance', `${result.provider}: $${result.balance}`);
            const balEl = document.getElementById('pv-balance-display');
            if (balEl) balEl.textContent = `$${parseFloat(result.balance).toFixed(2)}`;
        } else {
            toast.error('Balance Error', result.error || 'Could not fetch balance');
            const balEl = document.getElementById('pv-balance-display');
            if (balEl) balEl.textContent = 'Error';
        }
    } catch (e) {
        toast.error('Error', e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Check Balance'; }
    }
}

// ── Start phone verify ────────────────────────────────────────────────────────
async function startPhoneVerify() {
    if (isPhoneVerifying) return;

    const textarea = document.getElementById('pv-textarea');
    const tokens = textarea.value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

    if (tokens.length === 0) {
        toast.error('Error', 'No tokens loaded. Paste or upload tokens first.');
        return;
    }

    if (!window.pywebview?.api) {
        toast.error('Error', 'Application not ready');
        return;
    }

    const provider = document.getElementById('pv-provider')?.value || 'fivesim';
    const mode = document.getElementById('pv-mode')?.value || 'api';
    let apiKey = '';
    let country = '';

    if (provider === 'fivesim') {
        apiKey = document.getElementById('pv-fivesim-key')?.value?.trim() || '';
        country = document.getElementById('pv-fivesim-country')?.value?.trim() || 'any';
    } else if (provider === 'onlinesim') {
        apiKey = document.getElementById('pv-onlinesim-key')?.value?.trim() || '';
        country = document.getElementById('pv-onlinesim-country')?.value?.trim() || '7';
    } else if (provider === 'hero_sms') {
        apiKey = document.getElementById('pv-hero_sms-key')?.value?.trim() || '';
        country = document.getElementById('pv-hero_sms-country')?.value?.trim() || '62';
    }

    // Hero SMS extra params
    let maxPrice = 0;
    if (provider === 'hero_sms') {
        maxPrice = parseFloat(document.getElementById('pv-hero_sms-maxprice')?.value || '0') || 0;
    }

    if (!apiKey) {
        const names = { fivesim: '5sim', onlinesim: 'OnlineSim', hero_sms: 'Hero SMS' };
        toast.error('Missing Key', `Please enter your ${names[provider] || provider} API key.`);
        return;
    }

    try {
        isPhoneVerifying = true;
        window._pvStatsCleared = false;

        document.getElementById('pv-start-btn').disabled = true;
        document.getElementById('pv-stop-btn').disabled = false;
        const clearBtn = document.getElementById('pv-clear-btn');
        if (clearBtn) clearBtn.disabled = true;

        // Reset stats
        document.getElementById('pv-success').textContent = '0';
        document.getElementById('pv-failed').textContent = '0';
        document.getElementById('pv-pending').textContent = '0';
        document.getElementById('pv-progress').style.width = '0%';
        document.getElementById('pv-progress-text').textContent = '0/' + tokens.length;

        const config = { provider, apiKey, country, mode, maxPrice };
        const result = await window.pywebview.api.start_phone_verify(tokens, config);

        if (result.success) {
            addLog('[Phone] Starting phone verification for ' + tokens.length + ' tokens...', 'info');
            toast.success('Started', 'Phone verification started');
        } else {
            addLog('[Phone] Failed: ' + (result.error || ''), 'error');
            toast.error('Error', result.error || 'Failed to start');
            pvStopUI();
        }
    } catch (e) {
        addLog('[Phone] Error: ' + e.message, 'error');
        toast.error('Error', e.message);
        pvStopUI();
    }
}

// ── Stop phone verify ─────────────────────────────────────────────────────────
async function stopPhoneVerify() {
    try {
        if (window.pywebview?.api) {
            await window.pywebview.api.stop_phone_verify();
        }
        addLog('[Phone] Phone verification stopped', 'warning');
    } catch (e) { }
    pvStopUI();
}

function pvStopUI() {
    isPhoneVerifying = false;
    document.getElementById('pv-start-btn').disabled = false;
    document.getElementById('pv-stop-btn').disabled = true;
    const clearBtn = document.getElementById('pv-clear-btn');
    if (clearBtn) clearBtn.disabled = false;
}

// ── Clear ─────────────────────────────────────────────────────────────────────
async function clearPhoneVerify() {
    window._pvStatsCleared = true;

    const textarea = document.getElementById('pv-textarea');
    if (textarea) textarea.value = '';
    const fileInfo = document.getElementById('pv-file-info');
    if (fileInfo) fileInfo.textContent = 'No file selected';
    const fileInput = document.getElementById('pv-file');
    if (fileInput) fileInput.value = '';

    document.getElementById('pv-success').textContent = '0';
    document.getElementById('pv-failed').textContent = '0';
    document.getElementById('pv-pending').textContent = '0';
    document.getElementById('pv-progress').style.width = '0%';
    document.getElementById('pv-progress-text').textContent = '0/0';

    try {
        if (window.pywebview?.api?.reset_phone_verify_stats) {
            await window.pywebview.api.reset_phone_verify_stats();
        }
    } catch (e) {}

    toast.info('Cleared', 'Phone verify input and stats cleared');
}

// ── Stats polling (called from backend.js fetchStats) ─────────────────────────
async function pvFetchStats() {
    try {
        if (!window.pywebview?.api?.get_phone_verify_stats) return;
        const s = await window.pywebview.api.get_phone_verify_stats();
        if (!s || window._pvStatsCleared) return;

        document.getElementById('pv-success').textContent = s.success || 0;
        document.getElementById('pv-failed').textContent = s.failed || 0;
        document.getElementById('pv-pending').textContent = s.pending || 0;

        const total = s.total || 0;
        const current = s.current || 0;
        const pct = total > 0 ? Math.min((current / total) * 100, 100) : 0;
        document.getElementById('pv-progress').style.width = pct + '%';
        document.getElementById('pv-progress-text').textContent = current + '/' + total;

        if ((pct >= 100 && total > 0) || s.running === false) {
            pvStopUI();
        }
    } catch (e) {}
}

// ── Export globals ────────────────────────────────────────────────────────────
window.pvSwitchProvider = pvSwitchProvider;
window.pvCheckBalance = pvCheckBalance;
window.startPhoneVerify = startPhoneVerify;
window.stopPhoneVerify = stopPhoneVerify;
window.clearPhoneVerify = clearPhoneVerify;
window.pvFetchStats = pvFetchStats;
window.pvStopUI = pvStopUI;
