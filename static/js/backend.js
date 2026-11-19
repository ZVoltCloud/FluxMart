let wasMinimized = false;
window.hasOperationFinished = false;

// ── Clear-stats guard flags ────────────────────────────────────────────────────
// When the user presses Clear, we stop fetchStats() from immediately
// re-populating the panel until the next operation starts.
window._genStatsCleared   = false;
window._checkerStatsCleared = false;

function minimizeWindow() {
    const main = document.getElementById('main-container');
    const login = document.getElementById('login-overlay');
    const loading = document.getElementById('loading-overlay');
    
    const activeEl = [main, login, loading].find(el => el && el.style.display !== 'none');
    
    if (activeEl) {
        document.documentElement.classList.add('animating');
        document.body.classList.add('animating');
        activeEl.classList.add('animate-exit');
        setTimeout(() => {
            if (window.pywebview && window.pywebview.api) {
                wasMinimized = true;
                window.pywebview.api.minimize();
            }
            setTimeout(() => {
                activeEl.classList.remove('animate-exit');
                document.documentElement.classList.remove('animating');
                document.body.classList.remove('animating');
            }, 1000);
        }, 400);
    } else if (window.pywebview && window.pywebview.api) {
        wasMinimized = true;
        window.pywebview.api.minimize();
    }
}

window.addEventListener('focus', () => {
    if (!wasMinimized) return;

    const main = document.getElementById('main-container');
    const login = document.getElementById('login-overlay');
    const loading = document.getElementById('loading-overlay');
    
    const activeEl = [main, login, loading].find(el => el && el.style.display !== 'none');
    
    if (activeEl) {
        activeEl.classList.remove('animate-enter');
        
        setTimeout(() => {
            document.documentElement.classList.add('animating');
            document.body.classList.add('animating');
            
            void activeEl.offsetWidth;
            
            activeEl.classList.add('animate-enter');
            
            setTimeout(() => {
                if (activeEl === login) {
                    const loginContent = document.querySelector('.login-content');
                    if (loginContent) loginContent.classList.add('animate-enter');
                } else {
                    activeEl.classList.remove('animate-enter');
                }
                document.documentElement.classList.remove('animating');
                document.body.classList.remove('animating');
                wasMinimized = false;
            }, 1000);
        }, 50);
    } else {
        wasMinimized = false;
    }
});

function closeWindow() {
    const main = document.getElementById('main-container');
    const login = document.getElementById('login-overlay');
    const loading = document.getElementById('loading-overlay');
    
    const activeEl = [main, login, loading].find(el => el && el.style.display !== 'none');
    
    if (activeEl) {
        document.documentElement.classList.add('animating');
        document.body.classList.add('animating');
        activeEl.classList.add('animate-exit');
        setTimeout(() => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.close();
            }
        }, 400);
    } else if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.close();
    }
}

async function refreshAccountInfo(showToast = true) {
    const refreshBtn = document.getElementById('refresh-account-btn');
    const refreshBtnHTML = refreshBtn ? refreshBtn.innerHTML : '';

    try {
        if (!window.pywebview || !window.pywebview.api) return;

        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 0.8s linear infinite"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refreshing...';
        }

        const usernameInput = document.getElementById('account-username');
        const passwordInput = document.getElementById('account-password');

        let currentUsername = (usernameInput && usernameInput.value && usernameInput.value !== 'N/A') ? usernameInput.value : null;
        let currentPassword = (passwordInput && passwordInput.value && passwordInput.value !== 'N/A') ? passwordInput.value : null;

        const info = await window.pywebview.api.get_account_info(currentUsername, currentPassword);
        if (info.success) {
            const passInput = document.getElementById('account-password');
            const toggle = document.getElementById('account-password-toggle');

            const uname = info.username || 'N/A';
            const sub = info.subscription || 'N/A';

            document.getElementById('account-username').value = uname;
            document.getElementById('account-license').value = info.license_key;
            document.getElementById('account-hwid').value = info.hwid;
            document.getElementById('account-subscription').value = sub;
            document.getElementById('account-creation').value = info.creation_date;
            document.getElementById('account-expiration').value = info.expiration_date;
            document.getElementById('account-lastlogin').value = info.last_login;

            const heroName = document.getElementById('acc-display-username');
            const heroSub = document.getElementById('acc-display-sub');
            if (heroName) heroName.textContent = uname;
            if (heroSub) heroSub.textContent = sub;

            if (passInput) {
                passInput.value = info.password;
                if (info.password !== "N/A") {
                    passInput.type = 'password';
                    if (toggle) toggle.style.display = 'flex';
                } else {
                    passInput.type = 'text';
                    if (toggle) toggle.style.display = 'none';
                }
            }

            try {
                if (window.pywebview && window.pywebview.api) {
                    const discordUser = await window.pywebview.api.discord_get_cached_user();
                    const discordEl = document.getElementById('account-discord');
                    const discordAvatar = document.getElementById('account-discord-avatar');
                    if (discordUser && discordUser.success && discordUser.user) {
                        const u = discordUser.user;
                        const tag = u.username || u.global_name || 'Not linked';
                        if (discordEl) discordEl.textContent = tag;
                        if (discordAvatar) discordAvatar.src = u.avatar_url || '/static/img/dsnopfp.png';
                    } else {
                        if (discordEl) discordEl.textContent = 'Not linked';
                        if (discordAvatar) discordAvatar.src = '/static/img/dsnopfp.png';
                    }
                }
            } catch (e) { }

            if (passInput && toggle) {
                const eyeOpen = toggle.querySelector('.eye-open');
                const eyeClosed = toggle.querySelector('.eye-closed');
                if (eyeOpen) eyeOpen.style.display = 'none';
                if (eyeClosed) eyeClosed.style.display = 'block';

                const newToggle = toggle.cloneNode(true);
                toggle.parentNode.replaceChild(newToggle, toggle);

                newToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const currentEyeOpen = newToggle.querySelector('.eye-open');
                    const currentEyeClosed = newToggle.querySelector('.eye-closed');
                    if (passInput.type === 'password') {
                        passInput.type = 'text';
                        if (currentEyeOpen) currentEyeOpen.style.display = 'block';
                        if (currentEyeClosed) currentEyeClosed.style.display = 'none';
                    } else {
                        passInput.type = 'password';
                        if (currentEyeOpen) currentEyeOpen.style.display = 'none';
                        if (currentEyeClosed) currentEyeClosed.style.display = 'block';
                    }
                });
            }

            if (showToast && window.toast) {
                window.toast.success('Refresh Successful', 'Account data updated from our server.');
            }
        } else {
            if (showToast && window.toast) {
                window.toast.error('Refresh Failed', info.error || 'Could not update account data.');
            }
        }
    } catch (e) {
        console.error("Error refreshing account info:", e);
        if (showToast && window.toast) {
            window.toast.error('Refresh Error', 'An unexpected error occurred while refreshing data.');
        }
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = refreshBtnHTML;
        }
    }
}

async function fetchLogs() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const logs = await window.pywebview.api.get_logs();
        if (logs && logs.length > 0) {
            for (const log of logs) {
                addLog(log.message, log.type);
            }
        }
    } catch (e) {
        console.error('Error fetching logs:', e);
    }
}

function renderGenerationStatus(stats) {
    const valid = stats.valid || stats.tokens || 0;
    const locked = stats.locked || 0;
    const invalid = stats.invalid || 0;
    const amount = stats.amount || stats.total || stats.target || 0;
    const current = stats.current || valid + locked + invalid;

    document.getElementById('gen-valid').textContent = valid;
    document.getElementById('gen-locked').textContent = locked;
    document.getElementById('gen-invalid').textContent = invalid;

    const percent = amount > 0 ? Math.min((current / amount) * 100, 100) : (current > 0 ? 100 : 0);
    document.getElementById('gen-progress').style.width = percent + '%';
    document.getElementById('gen-progress-text').textContent = current + '/' + (amount > 0 ? amount : '0');

    return { percent, amount };
}

async function fetchStats() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;

        // ── Generator stats ────────────────────────────────────────────────────
        const stats = await window.pywebview.api.get_stats();
        if (stats && !window._genStatsCleared) {
            const amount = stats.amount || stats.target || 0;
            const current = (stats.valid || stats.tokens || 0) + (stats.locked || 0) + (stats.invalid || 0);
            const hasGenerationData = stats.running === true || amount > 0 || current > 0;

            if (hasGenerationData) {
                renderGenerationStatus(stats);

                if (stats.running === false) {
                    stopGeneratorUI();
                }
            } else if (stats.running === false && typeof isGenerating !== 'undefined' && isGenerating) {
                stopGeneratorUI();
            }
        }

        // ── Checker stats ──────────────────────────────────────────────────────
        // NOTE: Checker stats go ONLY to the checker panel. Never to gen panel.
        const checkerStats = await window.pywebview.api.get_checker_stats();
        if (checkerStats && !window._checkerStatsCleared) {
            document.getElementById('checker-valid').textContent = checkerStats.valid || 0;
            document.getElementById('checker-locked').textContent = checkerStats.locked || 0;
            document.getElementById('checker-invalid').textContent = checkerStats.invalid || 0;

            const cTotal = checkerStats.total || 0;
            const cCurrent = checkerStats.current || 0;
            const cPercent = cTotal > 0 ? Math.min((cCurrent / cTotal) * 100, 100) : 0;
            document.getElementById('checker-progress').style.width = cPercent + '%';
            document.getElementById('checker-progress-text').textContent = cCurrent + '/' + cTotal;

            if ((cPercent >= 100 && cTotal > 0) || checkerStats.running === false) {
                if (typeof stopCheckerUI === 'function') {
                    stopCheckerUI();
                }
            }
        }
    } catch (e) {}

    // ── Phone Verify stats ────────────────────────────────────────────────
    if (typeof pvFetchStats === 'function') {
        try { await pvFetchStats(); } catch (e) {}
    }
}

setInterval(async () => {
    await fetchLogs();
    await fetchStats();
    updateDashboard();
}, 500);

// ── Stats Dashboard + Status Bar Updater ───────────────────────────────────────
var _dashSessionStart = Date.now();
var _dashActiveTimeMs = 0;
var _dashLastTick = Date.now();
var _dashSessionTokens = 0;
var _dashLastTotal = 0;

function updateDashboard() {
    try {
        var now = Date.now();
        var delta = now - _dashLastTick;
        _dashLastTick = now;
        
        if (typeof isGenerating !== 'undefined' && isGenerating) {
            _dashActiveTimeMs += delta;
        }

        var validEl = document.getElementById('gen-valid');
        var lockedEl = document.getElementById('gen-locked');
        var invalidEl = document.getElementById('gen-invalid');
        if (!validEl) return;

        var valid = parseInt(validEl.textContent) || 0;
        var locked = parseInt(lockedEl.textContent) || 0;
        var invalid = parseInt(invalidEl.textContent) || 0;
        var total = valid + locked + invalid;

        // Track ALL tokens generated this session (not just valid)
        if (total > _dashLastTotal) {
            _dashSessionTokens += (total - _dashLastTotal);
        }
        _dashLastTotal = total;

        // Update dashboard cards
        var totalEl = document.getElementById('dash-total');
        var rateEl = document.getElementById('dash-rate');
        var speedEl = document.getElementById('dash-speed');
        var sessionEl = document.getElementById('dash-session');

        if (totalEl) totalEl.textContent = total;
        if (rateEl) rateEl.textContent = total > 0 ? Math.round((valid / total) * 100) + '%' : '0%';

        // Use backend tph payload if server sends real stats (stats.tph) and it's valid, otherwise use frontend calculation
        if (typeof stats !== 'undefined' && stats.tph !== undefined && stats.tph > 0) {
             if (speedEl) speedEl.textContent = Math.round(stats.tph);
             window._dashOverallTph = Math.round(stats.tph);
        } else {
             var activeSeconds = _dashActiveTimeMs / 1000;
             if (_dashSessionTokens > 0) {
                 var avgSecsPerToken = activeSeconds / _dashSessionTokens;
                 if (speedEl) speedEl.textContent = activeSeconds > 2 ? Math.round(3600 / avgSecsPerToken) : '0';
             } else {
                 if (speedEl) speedEl.textContent = '0';
             }
        }
        if (sessionEl) sessionEl.textContent = _dashSessionTokens;

        // ── Status Bar: Running count ──────────────────────────────────────────
        var workersEl = document.getElementById('status-workers');
        if (workersEl) {
            if (typeof isGenerating !== 'undefined' && isGenerating) {
                var threads = parseInt(document.getElementById('gen-threads').value) || 1;
                workersEl.textContent = 'Running: ' + threads;
            } else {
                workersEl.textContent = 'Running: 0';
            }
        }

        // ── Status Bar: Connection status and task state ───────────────────────
        var connDot = document.getElementById('status-connection');
        var connText = document.getElementById('status-connection-text');
        if (connDot && connText) {
            if (window.pywebview && window.pywebview.api) {
                if (typeof isGenerating !== 'undefined' && isGenerating) {
                    connDot.className = 'status-dot warning';
                    connText.textContent = 'Generating';
                } else if (typeof isCheckerRunning !== 'undefined' && isCheckerRunning) {
                    connDot.className = 'status-dot warning';
                    connText.textContent = 'Checking';
                } else {
                    connDot.className = 'status-dot online';
                    connText.textContent = 'Ready';
                }
            } else {
                connDot.className = 'status-dot offline';
                connText.textContent = 'Disconnected';
            }
        }
    } catch(e) {}
}

function openOutputFile(filename) {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.open_output_file(filename);
    }
}

async function testWebhook() {
    const btn = document.getElementById('test-webhook-btn');
    const url = document.getElementById('settings-webhook-url');
    if (!url || !url.value.trim()) {
        if (window.toast) window.toast.error('No URL', 'Please enter a webhook URL first.');
        return;
    }
    if (!window.pywebview || !window.pywebview.api) return;
    if (btn) { btn.disabled = true; btn.innerText = 'Sending...'; }
    try {
        const result = await window.pywebview.api.test_webhook(url.value.trim());
        if (result && result.success) {
            if (window.toast) window.toast.success('Webhook Sent', 'Test embed sent successfully!');
        } else {
            if (window.toast) window.toast.error('Webhook Failed', result && result.error ? result.error : 'Could not send test embed.');
        }
    } catch (e) {
        if (window.toast) window.toast.error('Webhook Error', 'An error occurred sending the test.');
    } finally {
        if (btn) { btn.disabled = false; btn.innerText = 'Send Test'; }
    }
}
