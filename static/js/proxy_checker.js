/* FluxMart — Proxy Checker */
(function () {
    'use strict';

    let _pollTimer = null;
    let _running = false;
    let _currentTab = 'fast';
    const _lists = { fast: [], slow: [], dead: [] };

    /* ── Helpers ── */
    function $id(id) { return document.getElementById(id); }

    function pcSetRunning(on) {
        _running = on;
        $id('pc-start-btn').disabled = on;
        $id('pc-stop-btn').disabled = !on;
        $id('pc-export-btn').disabled = on || (_lists.fast.length + _lists.slow.length === 0);
    }

    function pcRenderItem(proxy, ms, category) {
        const el = document.createElement('div');
        el.className = `pc-result-item pc-item-${category}`;
        const badge = category === 'fast'
            ? `<span class="pc-badge pc-badge-fast">${ms}ms</span>`
            : category === 'slow'
                ? `<span class="pc-badge pc-badge-slow">${ms}ms</span>`
                : `<span class="pc-badge pc-badge-dead">dead</span>`;
        el.innerHTML = `<span class="pc-proxy-text">${proxy}</span>${badge}`;
        return el;
    }

    function pcAppendResult(data) {
        const cat = data.category;
        _lists[cat].push(data);

        const listEl = $id(`pc-list-${cat}`);
        if (listEl) {
            listEl.appendChild(pcRenderItem(data.proxy, data.ms, cat));
        }

        $id('pc-count-fast').textContent = _lists.fast.length;
        $id('pc-count-slow').textContent = _lists.slow.length;
        $id('pc-count-dead').textContent = _lists.dead.length;
        $id('pc-count-total').textContent = _lists.fast.length + _lists.slow.length + _lists.dead.length;
    }

    function pcUpdateProgress(done, total) {
        const pct = total > 0 ? Math.round((done / total) * 100) : 0;
        const bar = $id('pc-progress-bar');
        if (bar) bar.style.width = pct + '%';
        const txt = $id('pc-progress-text');
        if (txt) txt.textContent = `${done} / ${total}`;
    }

    /* ── Tab switching ── */
    window.pcTabSwitch = function (tab, btn) {
        _currentTab = tab;
        document.querySelectorAll('.pc-rtab').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        ['fast', 'slow', 'dead'].forEach(t => {
            const el = $id(`pc-list-${t}`);
            if (el) el.style.display = t === tab ? '' : 'none';
        });
    };

    /* ── Start ── */
    window.pcStart = function () {
        const raw = ($id('pc-input') || {}).value || '';
        const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
        if (!lines.length) {
            if (typeof showToast === 'function') showToast('Paste at least one proxy.', 'error');
            return;
        }

        // Clear old results
        _lists.fast = [];
        _lists.slow = [];
        _lists.dead = [];
        ['fast', 'slow', 'dead'].forEach(t => {
            const el = $id(`pc-list-${t}`);
            if (el) el.innerHTML = '';
        });
        $id('pc-count-fast').textContent = '0';
        $id('pc-count-slow').textContent = '0';
        $id('pc-count-dead').textContent = '0';
        $id('pc-count-total').textContent = '0';
        pcUpdateProgress(0, 0);

        const threads = parseInt(($id('pc-threads') || {}).value || '10', 10);
        const timeout = parseInt(($id('pc-timeout') || {}).value || '10', 10);
        const fastMs = parseInt(($id('pc-fast-threshold') || {}).value || '2000', 10);

        pcSetRunning(true);

        pywebview && pywebview.api
            ? pywebview.api.proxy_checker_start({ proxies: lines, threads, timeout, fast_ms: fastMs })
                .then(() => _startPoll())
                .catch(e => {
                    if (typeof showToast === 'function') showToast('Failed to start checker.', 'error');
                    pcSetRunning(false);
                })
            : fetch('/api/proxy_checker/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proxies: lines, threads, timeout, fast_ms: fastMs })
            }).then(() => _startPoll()).catch(() => pcSetRunning(false));
    };

    /* ── Stop ── */
    window.pcStop = function () {
        pywebview && pywebview.api
            ? pywebview.api.proxy_checker_stop()
            : fetch('/api/proxy_checker/stop', { method: 'POST' });
    };

    /* ── Clear ── */
    window.pcClear = function () {
        if (_running) return;
        const inp = $id('pc-input');
        if (inp) inp.value = '';
        _lists.fast = [];
        _lists.slow = [];
        _lists.dead = [];
        ['fast', 'slow', 'dead'].forEach(t => {
            const el = $id(`pc-list-${t}`);
            if (el) el.innerHTML = '';
        });
        $id('pc-count-fast').textContent = '0';
        $id('pc-count-slow').textContent = '0';
        $id('pc-count-dead').textContent = '0';
        $id('pc-count-total').textContent = '0';
        pcUpdateProgress(0, 0);
        $id('pc-export-btn').disabled = true;
    };

    /* ── Export ── */
    window.pcExport = function () {
        const working = [..._lists.fast, ..._lists.slow].map(d => d.proxy);
        if (!working.length) return;
        const blob = new Blob([working.join('\n')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'working_proxies.txt';
        a.click();
        URL.revokeObjectURL(url);
    };

    /* ── Polling ── */
    let _lastResultIndex = 0;

    function _startPoll() {
        _lastResultIndex = 0;
        if (_pollTimer) clearInterval(_pollTimer);
        _pollTimer = setInterval(_poll, 500);
    }

    function _poll() {
        const doFetch = pywebview && pywebview.api
            ? pywebview.api.proxy_checker_status({ since: _lastResultIndex })
            : fetch(`/api/proxy_checker/status?since=${_lastResultIndex}`).then(r => r.json());

        Promise.resolve(doFetch).then(data => {
            if (!data) return;
            const results = data.results || [];
            results.forEach(r => {
                pcAppendResult(r);
                _lastResultIndex++;
            });
            pcUpdateProgress(data.done || 0, data.total || 0);
            if (!data.running) {
                clearInterval(_pollTimer);
                _pollTimer = null;
                pcSetRunning(false);
                if (typeof showToast === 'function')
                    showToast(`Done — ${_lists.fast.length} fast, ${_lists.slow.length} slow, ${_lists.dead.length} dead.`, 'success');
            }
        }).catch(() => { });
    }

})();
