let mskSettings = {};
let _settingsLoading = false;

async function loadSettingsFromBackend() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const config = await window.pywebview.api.load_settings();
        if (config) {
            mskSettings = config;
            window.mskSettings = mskSettings;
            const migratedDomains = ['cybertemp', 'duckmail'].map(provider =>
                initializeDomainTracking(mskSettings.email_providers?.[provider])
            ).some(Boolean);
            await initializeLanguages();
            loadSettingsIntoUI();
            if (migratedDomains) await window.pywebview.api.save_settings(mskSettings);
        }
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

function loadSettingsIntoUI() {
    _settingsLoading = true;
    const s = mskSettings;

    setChecked('gen-headless', s.headless);
    setChecked('gen-auto-captcha', s.auto_solver_captcha !== false);
    setValue('gen-threads', s.threads || 1);
    


    setValue('gen-token-count', s.token_count || 1);
    setValue('settings-browser-method', s.browser_method || 'camoufox');
    setChecked('settings-windows-manager', s.use_windows_manager !== false);
    setChecked('settings-save-fingerprint', s.save_fingerprint === true);
    if (s.fingerprint_settings) {
        setChecked('settings-use-custom-fingerprint', s.fingerprint_settings.use_custom_fingerprint === true);
    }
    setChecked('settings-real-usernames', s.real_usernames === true);
    setValue('settings-language', s.language || 'en');


    setChecked('settings-proxies-enabled', s.proxies && s.proxies.enabled);
    setChecked('settings-remove-proxy-after-use', s.proxies && s.proxies.remove_after_use);
    setChecked('settings-data-saver', s.data_saver_enabled || false);
    setChecked('settings-update-browser-save', s.update_browser_save || false);
    setChecked('settings-ratelimit', s.rate_limit_checker && s.rate_limit_checker.enabled);

    setValue('settings-hcaptcha-accessibility-cookie', s.hcaptcha_accessibility_cookie || '');


    if (s.solver_ai) {
        setChecked('settings-ai-cloudflare-enabled', s.solver_ai.cloudflare);
        setChecked('settings-ai-groq-enabled', s.solver_ai.groq);
        setChecked('settings-ai-openrouter-enabled', s.solver_ai.openrouter);
    }



    if (s.ai_api) {
        if (s.ai_api.cloudflare) {
            setValue('settings-ai-cloudflare-account-id', s.ai_api.cloudflare.account_id || '');
            setValue('settings-ai-cloudflare-key', s.ai_api.cloudflare.api_key || '');
        }
        if (s.ai_api.groq) setValue('settings-ai-groq-key', s.ai_api.groq.api_key || '');
        if (s.ai_api.openrouter) setValue('settings-ai-openrouter-key', s.ai_api.openrouter.api_key || '');
    }

    if (s.webhook) {
        setChecked('settings-webhook-enabled', s.webhook.enabled || false);
        setValue('settings-webhook-url', s.webhook.url || '');
        setChecked('settings-webhook-notify-all', s.webhook.notify_all || false);
    }

    // Load VPN provider settings
    if (s.vpn_providers) {
        // Mullvad
        setChecked('settings-vpn-mullvad-enabled', s.vpn_providers.mullvad && s.vpn_providers.mullvad.enabled);
    } else {
        // Legacy support for mullvad boolean
        const legacy_mullvad = s.mullvad || false;
        setChecked('settings-vpn-mullvad-enabled', legacy_mullvad);
    }

    // Show/hide request-based API key row
    onBrowserMethodChange();

    // Load email provider settings
    if (s.email_providers) {
        const ep = s.email_providers;
        // CyberTemp
        const ct = ep.cybertemp || {};
        setChecked('settings-email-cybertemp-enabled', !!ct.enabled);
        setValue('settings-email-cybertemp-key', ct.api_key != null ? ct.api_key : '');
        setValue('settings-email-cybertemp-domain', ct.domain || 'random');

        // DuckMail
        const dm = ep.duckmail || {};
        setChecked('settings-email-duckmail-enabled', !!dm.enabled);
        setValue('settings-email-duckmail-key', dm.api_key != null ? dm.api_key : '');
        setValue('settings-email-duckmail-domain', dm.domain || 'random');

        // Mailcow
        const mc = ep.mailcow || {};
        setChecked('settings-email-mailcow-enabled', !!mc.enabled);
        setValue('settings-email-mailcow-host', mc.host_url != null ? mc.host_url : '');
        setValue('settings-email-mailcow-key', mc.api_key != null ? mc.api_key : '');
        setValue('settings-email-mailcow-domain', mc.domain != null ? mc.domain : '');

        // Zeus
        const zs = ep.zeus || {};
        setChecked('settings-email-zeus-enabled', !!zs.enabled);
        setValue('settings-email-zeus-key', zs.api_key != null ? zs.api_key : '');
        setValue('settings-email-zeus-type', zs.account_type || 'HOTMAIL');

        // Hotmail007
        const hm = ep.hotmail007 || {};
        setChecked('settings-email-hotmail007-enabled', !!hm.enabled);
        setValue('settings-email-hotmail007-key', hm.api_key != null ? hm.api_key : '');
        setValue('settings-email-hotmail007-type', hm.mail_type || 'hotmail');
        
        // Store productId in the selected option's dataset for later use
        if (hm.product_id) {
            const dropdown = document.getElementById('settings-email-hotmail007-type');
            if (dropdown.selectedOptions[0]) {
                dropdown.selectedOptions[0].dataset.productId = hm.product_id;
            }
        }

        // Lution
        const lt = ep.lution || {};
        setChecked('settings-email-lution-enabled', !!lt.enabled);
        setValue('settings-email-lution-key', lt.api_key != null ? lt.api_key : '');
        setValue('settings-email-lution-type', lt.account_type || 'hotmail');
    } else {
        setValue('settings-email-cybertemp-key', s.cybertemp_api_key || '');
        setChecked('settings-email-cybertemp-enabled', true);
        setTimeout(() => { try { saveSettingsInstant(); } catch(e) {} }, 500);
    }

    updateProviderBoxStates();

    // Load restock wait setting
    setChecked('settings-email-restock-wait', s.restock_wait !== undefined ? s.restock_wait : true);

    // Load Fast Mails settings
    if (s.fast_mails) {
        setChecked('settings-email-fast-mails', s.fast_mails.enabled || false);
        setValue('settings-email-fast-mails-buffer', s.fast_mails.buffer_size || 3);
    }
    // Toggle buffer row visibility
    const fastMailsRow = document.getElementById('fast-mails-buffer-row');
    if (fastMailsRow) {
        fastMailsRow.style.display = getChecked('settings-email-fast-mails') ? '' : 'none';
    }

    // Load Multi Buy settings
    if (s.multi_buy) {
        setChecked('settings-email-multi-buy', s.multi_buy.enabled || false);
        const mbProviders = s.multi_buy.providers || ['zeus', 'hotmail007', 'lution'];
        setChecked('multi-buy-zeus', mbProviders.includes('zeus'));
        setChecked('multi-buy-hotmail007', mbProviders.includes('hotmail007'));
        setChecked('multi-buy-lution', mbProviders.includes('lution'));
    }
    // Toggle providers row visibility
    const multiBuyRow = document.getElementById('multi-buy-providers-row');
    if (multiBuyRow) {
        multiBuyRow.style.display = getChecked('settings-email-multi-buy') ? '' : 'none';
    }

    // Update visual active states for provider boxes
    updateProviderBoxStates();
    updateVPNProviderBoxStates();
    updateAISolverBoxStates();

    if (s.humanizer) {
        setChecked('humanizer-enabled', s.humanizer.enabled);
        setChecked('humanizer-avatar', s.humanizer.avatar !== false);
        setChecked('humanizer-bio', s.humanizer.bio !== false);
        setChecked('humanizer-pronouns', s.humanizer.pronouns !== false);
        setChecked('humanizer-displayname', s.humanizer.display_name !== false);
        setChecked('humanizer-hypesquad', s.humanizer.hypesquad !== false);
    }

    if (s.smart_multithread) {
        setChecked('settings-smart-multithread', s.smart_multithread.enabled || false);
        setValue('settings-smart-multithread-trigger', s.smart_multithread.trigger || 'captcha_solved');
    }

    _styleSmartMultithreadTrigger();
    setupSmartMultithreadToggle();

    attachSettingsListeners();
    setupEmailProviderToggles();
    updateHotmailOptionsVisibility();
    setupVPNProviderToggles();
    setupAISolverToggles();
    setupFastMailsToggle();
    setupMultiBuyToggle();

    setupProxiesToggle();

    restoreCybertempDomains();
    restoreDuckmailDomains();
    _settingsLoading = false;
}

function setChecked(id, val) {
    const el = document.getElementById(id);
    if (el) el.checked = !!val;
}

function setValue(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val;
}

function setupAISolverToggles() {
    const solvers = ['cloudflare', 'groq', 'openrouter'];

    solvers.forEach(solver => {
        const toggle = document.getElementById(`settings-ai-${solver}-enabled`);
        if (toggle) {
            toggle.addEventListener('change', function () {
                if (this.checked) {
                    // Disable all other text-based solvers
                    solvers.forEach(otherSolver => {
                        if (otherSolver !== solver) {
                            const otherToggle = document.getElementById(`settings-ai-${otherSolver}-enabled`);
                            if (otherToggle) {
                                otherToggle.checked = false;
                            }
                        }
                    });
                }
                updateAISolverBoxStates();
                saveSettingsInstant();
            });
        }
    });
}

function updateAISolverBoxStates() {
    const solvers = ['cloudflare', 'groq', 'openrouter'];

    solvers.forEach(solver => {
        const toggle = document.getElementById(`settings-ai-${solver}-enabled`);
        const box = document.getElementById(`provider-ai-${solver}`);

        if (toggle && box) {
            if (toggle.checked) {
                box.classList.add('active');
            } else {
                box.classList.remove('active');
            }
        }
    });


}

function setupEmailProviderToggles() {
    const providers = ['cybertemp', 'duckmail', 'mailcow', 'zeus', 'hotmail007', 'lution'];

    providers.forEach(provider => {
        const toggle = document.getElementById(`settings-email-${provider}-enabled`);
        if (toggle) {
            toggle.addEventListener('change', function () {
                if (this.checked) {
                    // Disable all other providers
                    providers.forEach(otherProvider => {
                        if (otherProvider !== provider) {
                            const otherToggle = document.getElementById(`settings-email-${otherProvider}-enabled`);
                            if (otherToggle) {
                                otherToggle.checked = false;
                            }
                        }
                    });
                }
                updateProviderBoxStates();
                updateHotmailOptionsVisibility();
                saveSettingsInstant();
            });
        }
    });
}

function updateProviderBoxStates() {
    const providers = ['cybertemp', 'duckmail', 'mailcow', 'zeus', 'hotmail007', 'lution'];

    providers.forEach(provider => {
        const toggle = document.getElementById(`settings-email-${provider}-enabled`);
        const box = document.getElementById(`provider-${provider}`);

        if (toggle && box) {
            if (toggle.checked) {
                box.classList.add('active');
            } else {
                box.classList.remove('active');
            }
        }
    });
}

// Show Wait-for-Restock / Fast Mails / Multi Buy rows ONLY when at least one
// paid Hotmail-stock provider (Zeus, Hotmail007, Lution) is enabled.
function updateHotmailOptionsVisibility() {
    const group = document.getElementById('hotmail-options-group');
    if (!group) return;
    const hotmailProviders = ['zeus', 'hotmail007', 'lution'];
    const anyOn = hotmailProviders.some(p => {
        const t = document.getElementById(`settings-email-${p}-enabled`);
        return t && t.checked;
    });
    group.style.display = anyOn ? '' : 'none';
}

function setupVPNProviderToggles() {
    const providers = ['mullvad'];

    providers.forEach(provider => {
        const toggle = document.getElementById(`settings-vpn-${provider}-enabled`);
        if (toggle) {
            toggle.addEventListener('change', function () {
                updateVPNProviderBoxStates();
                saveSettingsInstant();
            });
        }
    });
}

function updateVPNProviderBoxStates() {
    const providers = ['mullvad'];

    providers.forEach(provider => {
        const toggle = document.getElementById(`settings-vpn-${provider}-enabled`);
        const box = document.getElementById(`provider-${provider}`);

        if (toggle && box) {
            if (toggle.checked) {
                box.classList.add('active');
            } else {
                box.classList.remove('active');
            }
        }
    });
}

let previousBrowserMethod = 'camoufox';

// All browsers support Text Solver
const TEXT_SOLVER_BROWSERS = ['camoufox', 'brave', 'chromium', 'chromium2', 'clearcote'];

function onBrowserMethodChange() {
    const methodEl = document.getElementById('settings-browser-method');
    const method = methodEl ? methodEl.value : 'camoufox';

    previousBrowserMethod = method;

    // Show/hide Text Solver compat note
    const note = document.getElementById('browser-textsolver-note');
    if (note) {
        note.style.display = TEXT_SOLVER_BROWSERS.includes(method) ? '' : 'none';
    }

    setTimeout(saveSettingsInstant, 50);
}

function attachSettingsListeners() {
    const allInputs = document.querySelectorAll(
        '#gen-headless, #gen-auto-captcha, #gen-threads, #gen-token-count,' +
        '#settings-browser-method, #settings-token-verify, #settings-language,' +
        '#settings-proxies-enabled, #settings-remove-proxy-after-use, #settings-data-saver, #settings-update-browser-save, #settings-ratelimit,' +
        '#settings-hcaptcha-accessibility-cookie,' +
        '#settings-ai-cloudflare-account-id, #settings-ai-cloudflare-key, #settings-ai-groq-key, #settings-ai-openrouter-key,' +
        '#settings-email-cybertemp-key, #settings-email-cybertemp-domain, #settings-email-duckmail-key, #settings-email-duckmail-domain, #settings-email-mailcow-host, #settings-email-mailcow-key, #settings-email-mailcow-domain, #settings-email-zeus-key, #settings-email-zeus-type,' +
        '#settings-email-hotmail007-key, #settings-email-hotmail007-type, #settings-email-lution-key, #settings-email-lution-type,' +
        '#settings-email-restock-wait, #settings-email-fast-mails, #settings-email-fast-mails-buffer, #settings-email-multi-buy,' +
        '#multi-buy-zeus, #multi-buy-hotmail007, #multi-buy-lution,' +
        '#humanizer-enabled, #humanizer-avatar, #humanizer-bio, #humanizer-pronouns, #humanizer-displayname, #humanizer-hypesquad,' +
        '#settings-webhook-enabled, #settings-webhook-url, #settings-webhook-notify-all,' +
        '#settings-smart-multithread, #settings-smart-multithread-trigger'
    );

    allInputs.forEach(input => {
        input.removeEventListener('change', saveSettingsInstant);
        input.removeEventListener('input', saveSettingsDebounced);
        input.addEventListener('change', saveSettingsInstant);
        if (input.type === 'text' || input.type === 'number') {
            input.addEventListener('input', saveSettingsDebounced);
        }
    });
}

let saveTimeout = null;
function saveSettingsDebounced() {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(saveSettingsInstant, 500);
}

function setupFastMailsToggle() {
    const toggle = document.getElementById('settings-email-fast-mails');
    const bufferRow = document.getElementById('fast-mails-buffer-row');
    if (toggle && bufferRow) {
        toggle.addEventListener('change', function() {
            bufferRow.style.display = this.checked ? '' : 'none';
            saveSettingsInstant();
        });
    }
}

function setupProxiesToggle() {
    const toggle = document.getElementById('settings-proxies-enabled');
    const removeProxyRow = document.getElementById('settings-remove-proxy-wrapper');
    const baseBrowserContainer = document.getElementById('base-browser-save-container');
    const dataSaverContainer = document.getElementById('data-saver-container');
    
    if (toggle && removeProxyRow) {
        const updateVisibility = () => {
            removeProxyRow.style.display = toggle.checked ? '' : 'none';
            if (baseBrowserContainer) {
                baseBrowserContainer.style.display = toggle.checked ? 'flex' : 'none';
                if (!toggle.checked) {
                    const baseBrowserToggle = document.getElementById('settings-update-browser-save');
                    if (baseBrowserToggle) baseBrowserToggle.checked = false;
                }
            }
            if (dataSaverContainer) {
                dataSaverContainer.style.display = toggle.checked ? 'flex' : 'none';
                if (!toggle.checked) {
                    const dataSaverToggle = document.getElementById('settings-data-saver');
                    if (dataSaverToggle) dataSaverToggle.checked = false;
                }
            }
        };
        toggle.addEventListener('change', function() {
            updateVisibility();
            saveSettingsInstant();
        });
        updateVisibility(); // Initial state
    }
}

function setupMultiBuyToggle() {
    const toggle = document.getElementById('settings-email-multi-buy');
    const providersRow = document.getElementById('multi-buy-providers-row');
    if (toggle && providersRow) {
        toggle.addEventListener('change', function() {
            providersRow.style.display = this.checked ? '' : 'none';
            saveSettingsInstant();
        });
    }
}





function getChecked(id) {
    const el = document.getElementById(id);
    return el ? el.checked : false;
}

function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}

async function saveSettingsInstant() {
  if (_settingsLoading) return;
  try {
    mskSettings.headless = getChecked('gen-headless');
    mskSettings.auto_solver_captcha = getChecked('gen-auto-captcha');
    mskSettings.threads = Number(getVal('gen-threads')) || 1;
    mskSettings.token_count = Number(getVal('gen-token-count')) || 1;
    mskSettings.browser_method = getVal('settings-browser-method') || 'camoufox';
    mskSettings.token_verify = true;  // Always verify email
    mskSettings.use_windows_manager = getChecked('settings-windows-manager');
    mskSettings.save_fingerprint = getChecked('settings-save-fingerprint');
    if (!mskSettings.fingerprint_settings) mskSettings.fingerprint_settings = { use_custom_fingerprint: false, load_folder: 'data/input/fingerprints.txt', remove_after_use: true };
    mskSettings.fingerprint_settings.use_custom_fingerprint = getChecked('settings-use-custom-fingerprint');
    mskSettings.real_usernames = getChecked('settings-real-usernames');
    const oldLanguage = mskSettings.language;
    mskSettings.language = getVal('settings-language') || 'en';
    mskSettings.hcaptcha_accessibility_cookie = getVal('settings-hcaptcha-accessibility-cookie');

    // Apply translation if language changed
    if (mskSettings.language !== oldLanguage) {
        // Pass true to indicate this IS a manual change (show success toast)
        applyLanguage(mskSettings.language, true);
        if (window.retranslateLogs) {
            window.retranslateLogs(mskSettings.language);
        }
    }


    if (!mskSettings.proxies) mskSettings.proxies = {};
    mskSettings.proxies.enabled = getChecked('settings-proxies-enabled');
    mskSettings.proxies.remove_after_use = getChecked('settings-remove-proxy-after-use');

    mskSettings.data_saver_enabled = getChecked('settings-data-saver');
    mskSettings.update_browser_save = getChecked('settings-update-browser-save');

    if (!mskSettings.rate_limit_checker) mskSettings.rate_limit_checker = {};
    mskSettings.rate_limit_checker.enabled = getChecked('settings-ratelimit');


    if (!mskSettings.solver_ai) mskSettings.solver_ai = {};
    mskSettings.solver_ai.cloudflare = getChecked('settings-ai-cloudflare-enabled');
    mskSettings.solver_ai.groq = getChecked('settings-ai-groq-enabled');
    mskSettings.solver_ai.openrouter = getChecked('settings-ai-openrouter-enabled');

    if (!mskSettings.ai_api) mskSettings.ai_api = {
        cloudflare: { account_id: '', api_key: '', model: '@cf/openai/gpt-oss-120b' },
        openrouter: { api_key: '', model: 'nvidia/nemotron-3-super-120b-a12b:free' },
        groq: { api_key: '', model: 'llama-3.3-70b-versatile' }
    };
    if (!mskSettings.ai_api.cloudflare) mskSettings.ai_api.cloudflare = { account_id: '', api_key: '', model: '@cf/openai/gpt-oss-120b' };
    mskSettings.ai_api.cloudflare.account_id = getVal('settings-ai-cloudflare-account-id');
    mskSettings.ai_api.cloudflare.api_key = getVal('settings-ai-cloudflare-key');
    if (!mskSettings.ai_api.groq) mskSettings.ai_api.groq = { api_key: '', model: 'llama-3.3-70b-versatile' };
    mskSettings.ai_api.groq.api_key = getVal('settings-ai-groq-key');
    if (!mskSettings.ai_api.openrouter) mskSettings.ai_api.openrouter = { api_key: '', model: 'nvidia/nemotron-3-super-120b-a12b:free' };
    mskSettings.ai_api.openrouter.api_key = getVal('settings-ai-openrouter-key');



    // Save VPN provider settings
    if (!mskSettings.vpn_providers) mskSettings.vpn_providers = {
        mullvad: { enabled: true }
    };

    mskSettings.vpn_providers.mullvad = {
        enabled: getChecked('settings-vpn-mullvad-enabled')
    };

    // Save email provider settings
    if (!mskSettings.email_providers) mskSettings.email_providers = {
        cybertemp: { enabled: true, api_key: '' },
        duckmail: { enabled: false, api_key: '' },
        mailcow: { enabled: false, host_url: '', api_key: '', domain: '' },
        zeus: { enabled: false, api_key: '', account_type: 'HOTMAIL' },
        hotmail007: { enabled: false, api_key: '', mail_type: 'hotmail', product_id: null },
        lution: { enabled: false, api_key: '', account_type: 'hotmail' }
    };

    mskSettings.email_providers.cybertemp = {
        ...(mskSettings.email_providers.cybertemp || {}),
        enabled: getChecked('settings-email-cybertemp-enabled'),
        api_key: getVal('settings-email-cybertemp-key'),
        domain: getVal('settings-email-cybertemp-domain') || 'random'
    };

    mskSettings.email_providers.duckmail = {
        ...(mskSettings.email_providers.duckmail || {}),
        enabled: getChecked('settings-email-duckmail-enabled'),
        api_key: getVal('settings-email-duckmail-key'),
        domain: getVal('settings-email-duckmail-domain') || 'random'
    };

    mskSettings.email_providers.mailcow = {
        enabled: getChecked('settings-email-mailcow-enabled'),
        host_url: getVal('settings-email-mailcow-host'),
        api_key: getVal('settings-email-mailcow-key'),
        domain: getVal('settings-email-mailcow-domain')
    };

    mskSettings.email_providers.zeus = {
        enabled: getChecked('settings-email-zeus-enabled'),
        api_key: getVal('settings-email-zeus-key'),
        account_type: getVal('settings-email-zeus-type')
    };

    mskSettings.email_providers.hotmail007 = {
        enabled: getChecked('settings-email-hotmail007-enabled'),
        api_key: getVal('settings-email-hotmail007-key'),
        mail_type: getVal('settings-email-hotmail007-type'),
        product_id: document.getElementById('settings-email-hotmail007-type').selectedOptions[0]?.dataset?.productId || null
    };

    mskSettings.email_providers.lution = {
        enabled: getChecked('settings-email-lution-enabled'),
        api_key: getVal('settings-email-lution-key'),
        account_type: getVal('settings-email-lution-type')
    };

    // Save restock wait setting
    mskSettings.restock_wait = getChecked('settings-email-restock-wait');

    // Save Fast Mails settings
    mskSettings.fast_mails = {
        enabled: getChecked('settings-email-fast-mails'),
        buffer_size: parseInt(getVal('settings-email-fast-mails-buffer') || '3', 10)
    };

    // Save Multi Buy settings
    const multiBuyProviders = [];
    if (getChecked('multi-buy-zeus')) multiBuyProviders.push('zeus');
    if (getChecked('multi-buy-hotmail007')) multiBuyProviders.push('hotmail007');
    if (getChecked('multi-buy-lution')) multiBuyProviders.push('lution');
    mskSettings.multi_buy = {
        enabled: getChecked('settings-email-multi-buy'),
        providers: multiBuyProviders
    };

    if (!mskSettings.webhook) mskSettings.webhook = {};
    mskSettings.webhook.enabled = getChecked('settings-webhook-enabled');
    mskSettings.webhook.url = getVal('settings-webhook-url');
    mskSettings.webhook.notify_all = getChecked('settings-webhook-notify-all');

    if (!mskSettings.humanizer) mskSettings.humanizer = {};
    mskSettings.humanizer.enabled = getChecked('humanizer-enabled');
    mskSettings.humanizer.avatar = getChecked('humanizer-avatar');
    mskSettings.humanizer.bio = getChecked('humanizer-bio');
    mskSettings.humanizer.pronouns = getChecked('humanizer-pronouns');
    mskSettings.humanizer.display_name = getChecked('humanizer-displayname');
    mskSettings.humanizer.hypesquad = getChecked('humanizer-hypesquad');

    if (!mskSettings.smart_multithread) mskSettings.smart_multithread = {};
    mskSettings.smart_multithread.enabled = getChecked('settings-smart-multithread');
    mskSettings.smart_multithread.trigger = getVal('settings-smart-multithread-trigger') || 'captcha_solved';

    if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.save_settings(mskSettings);
    }
  } catch (e) {
    console.error("[MSK] saveSettingsInstant error:", e);
    try {
        if (window.toast) window.toast.error('Settings', 'Save failed: ' + (e && e.message ? e.message : String(e)));
    } catch (_) {}
  }
}

function _styleSmartMultithreadTrigger() {
    // No special styling — trigger dropdown uses default select appearance.
}

function setupSmartMultithreadToggle() {
    const toggle = document.getElementById('settings-smart-multithread');
    const triggerRow = document.getElementById('smart-multithread-trigger-row');
    if (!toggle || !triggerRow) return;
    const updateVisibility = () => {
        triggerRow.style.display = toggle.checked ? '' : 'none';
    };
    updateVisibility();
    toggle.addEventListener('change', () => {
        updateVisibility();
        saveSettingsInstant();
    });
}

async function checkMailcowApi() {
    const hostUrl = document.getElementById('settings-email-mailcow-host').value.trim();
    const apiKey = document.getElementById('settings-email-mailcow-key').value.trim();
    const domain = document.getElementById('settings-email-mailcow-domain').value.trim();
    const btn = document.getElementById('mailcow-check-btn');
    const status = document.getElementById('mailcow-check-status');

    if (!hostUrl || !apiKey || !domain) {
        window.toast.error('Missing Fields', 'Please fill in Host URL, API Key, and Domain first.');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="mailcow-check-icon"></span> Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_mailcow_api(hostUrl, apiKey, domain);
        const c = result.checks || {};
        const chk = '[PASS]';
        const xmk = '[FAIL]';
        const details =
            (c.connection ? chk : xmk) + ' Connection  ' +
            (c.create_mailbox ? chk : xmk) + ' Create  ' +
            (c.delete_mailbox ? chk : xmk) + ' Delete';

        if (result.success) {
            window.toast.success('Mailcow API', result.message);
            status.innerHTML = details;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Mailcow API', result.message, 10000);
            status.innerHTML = details + '  —  ' + result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Mailcow API', 'Failed to reach backend: ' + e, 10000);
        status.innerHTML = '[FAIL] Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="mailcow-check-icon"></span> Check API Access';
    }
}

async function checkZeusApi() {
    const apiKey = document.getElementById('settings-email-zeus-key').value.trim();
    const btn = document.getElementById('zeus-check-btn');
    const status = document.getElementById('zeus-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter a Zeus API key first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_zeus_api(apiKey);
        if (result.success) {
            window.toast.success('Zeus API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Zeus API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Zeus API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check API Key';
    }
}

async function refreshHotmail007Products() {
    const apiKey = document.getElementById('settings-email-hotmail007-key').value.trim();
    const dropdown = document.getElementById('settings-email-hotmail007-type');
    const status = document.getElementById('hotmail007-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter a Hotmail007 API key first.');
        return;
    }

    const currentValue = dropdown.value;
    status.textContent = 'Fetching products...';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.fetch_hotmail007_products(apiKey);
        if (result.success && result.products && result.products.length > 0) {
            // Clear existing options
            dropdown.innerHTML = '';
            
            // Add products from API
            result.products.forEach(product => {
                const option = document.createElement('option');
                
                // Use mailType directly from API as the value
                // This will be exactly what the API expects: "hotmail IMAP", "outlook Premium", etc.
                option.value = product.mailType;
                
                // Format display text: Name — Price (Stock: X)
                let displayText = product.name;
                if (product.price) {
                    displayText += ` — $${product.price}`;
                }
                if (product.stock !== undefined) {
                    displayText += ` (Stock: ${product.stock})`;
                }
                
                option.textContent = displayText;
                option.dataset.productId = product.productId;
                option.dataset.mailType = product.mailType;
                option.dataset.stock = product.stock;
                option.dataset.price = product.price;
                dropdown.appendChild(option);
            });

            // Try to restore previous selection
            if (currentValue) {
                const matchingOption = Array.from(dropdown.options).find(opt => opt.value === currentValue);
                if (matchingOption) {
                    dropdown.value = currentValue;
                }
            }

            window.toast.success('Hotmail007 Products', `Loaded ${result.products.length} products`);
            status.textContent = `${result.products.length} products loaded`;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Hotmail007 Products', result.message || 'No products available', 10000);
            status.textContent = result.message || 'No products found';
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Hotmail007 Products', 'Failed to fetch products: ' + e, 10000);
        status.textContent = 'Fetch failed — ' + e;
        status.className = 'mailcow-check-status error';
    }
}

async function checkHotmail007Api() {
    const apiKey = document.getElementById('settings-email-hotmail007-key').value.trim();
    const btn = document.getElementById('hotmail007-check-btn');
    const status = document.getElementById('hotmail007-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter a Hotmail007 API key first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_hotmail007_api(apiKey);
        if (result.success) {
            window.toast.success('Hotmail007 API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
            
            // Automatically refresh products after successful API check
            await refreshHotmail007Products();
        } else {
            window.toast.error('Hotmail007 API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Hotmail007 API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check API Key';
    }
}

async function checkCloudflareApi() {
    const accountId = document.getElementById('settings-ai-cloudflare-account-id').value.trim();
    const apiKey = document.getElementById('settings-ai-cloudflare-key').value.trim();
    const btn = document.getElementById('cloudflare-check-btn');
    const status = document.getElementById('cloudflare-check-status');

    if (!accountId || !apiKey) {
        window.toast.error('Missing Fields', 'Please enter both Account ID and API Token first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_cloudflare_api(accountId, apiKey);
        if (result.success) {
            window.toast.success('Cloudflare API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Cloudflare API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Cloudflare API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check Key';
    }
}

async function checkGroqApi() {
    const apiKey = document.getElementById('settings-ai-groq-key').value.trim();
    const btn = document.getElementById('groq-check-btn');
    const status = document.getElementById('groq-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter a Groq API key first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_groq_api(apiKey);
        if (result.success) {
            window.toast.success('Groq API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Groq API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Groq API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check Key';
    }
}

async function checkOpenRouterApi() {
    const apiKey = document.getElementById('settings-ai-openrouter-key').value.trim();
    const btn = document.getElementById('openrouter-check-btn');
    const status = document.getElementById('openrouter-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter an OpenRouter API key first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_openrouter_api(apiKey);
        if (result.success) {
            window.toast.success('OpenRouter API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('OpenRouter API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('OpenRouter API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check Key';
    }
}

async function checkLutionApi() {
    const apiKey = document.getElementById('settings-email-lution-key').value.trim();
    const btn = document.getElementById('lution-check-btn');
    const status = document.getElementById('lution-check-status');

    if (!apiKey) {
        window.toast.error('Missing Field', 'Please enter a Lution API key first.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_lution_api(apiKey);
        if (result.success) {
            window.toast.success('Lution API', result.message);
            status.textContent = result.message;
            status.className = 'mailcow-check-status success';
        } else {
            window.toast.error('Lution API', result.message, 10000);
            status.textContent = result.message;
            status.className = 'mailcow-check-status error';
        }
    } catch (e) {
        window.toast.error('Lution API', 'Failed to reach backend: ' + e, 10000);
        status.textContent = 'Check failed — ' + e;
        status.className = 'mailcow-check-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Check API Key';
    }
}

function normalizeDomainName(domain) {
    return typeof domain === 'string' ? domain.trim().toLowerCase() : '';
}

function initializeDomainTracking(provider) {
    if (!provider || provider.domain_tracking?.version === 1) return false;
    const domains = [...new Set((provider.cached_domains || [])
        .map(d => normalizeDomainName(d.domain)).filter(Boolean))];
    if (!domains.length) return false;

    // Legacy tags were not based on discovery dates; start with a clean baseline.
    provider.domain_tracking = { version: 1, seen_domains: domains, latest_domains: [] };
    provider.cached_domains = domains.map(domain => ({ domain, tag: 'known' }));
    return true;
}

function trackRefreshedDomains(providerName, result) {
    if (!mskSettings.email_providers) mskSettings.email_providers = {};
    const provider = mskSettings.email_providers[providerName] ||= {};
    initializeDomainTracking(provider);
    const domains = [...new Set(result.domains
        .map(d => normalizeDomainName(d.domain)).filter(Boolean))];
    let tracking = provider.domain_tracking;

    // A fallback response must not advance history or replace the latest batch.
    if (!result.cached && domains.length) {
        if (!tracking) {
            tracking = { version: 1, seen_domains: domains, latest_domains: [] };
        } else {
            const seen = new Set(tracking.seen_domains);
            const added = domains.filter(domain => !seen.has(domain));
            tracking = {
                version: 1,
                seen_domains: [...new Set([...seen, ...domains])],
                latest_domains: added.length ? added : tracking.latest_domains
            };
        }
        provider.domain_tracking = tracking;
    }

    const latest = new Set(tracking?.latest_domains || []);
    const tagged = domains.map(domain => ({ domain, tag: latest.has(domain) ? 'new' : 'known' }));
    tagged.sort((a, b) => Number(b.tag === 'new') - Number(a.tag === 'new') || a.domain.localeCompare(b.domain));
    if (!result.cached && domains.length) {
        provider.cached_domains = tagged;
        provider.last_refresh = new Date().toISOString();
    }
    return tagged;
}

async function refreshCybertempDomains() {
    const btn = document.getElementById('cybertemp-refresh-btn');
    const status = document.getElementById('cybertemp-domain-status');
    const select = document.getElementById('settings-email-cybertemp-domain');

    if (!select) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="mailcow-check-icon"></span> Loading...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_cybertemp_domains();
        if (result.success && result.domains && result.domains.length > 0) {
            const domains = trackRefreshedDomains('cybertemp', result);
            // Save current selection
            const currentVal = select.value;

            // Clear existing options except Random
            select.innerHTML = '<option value="random">Random (All Domains)</option>';

            // Provider tags are ignored; freshness comes from persisted discovery history.
            domains.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.domain;
                opt.textContent = d.domain + (d.tag === 'new' ? ' [new]' : '');
                select.appendChild(opt);
            });

            // Restore previous selection if still available
            if (currentVal) {
                select.value = currentVal;
                if (select.value !== currentVal) select.value = 'random';
            }

            saveSettingsInstant();

            // Update last refresh display
            updateCybertempRefreshTime();

            status.textContent = (result.cached ? 'Loaded ' : 'Found ') + domains.length + ' domains';
            status.className = 'mailcow-check-status success';
            if (result.cached) {
                window.toast.warning('CyberTemp', result.message || 'Loaded cached domains (API unavailable)');
            } else {
                window.toast.success('CyberTemp', result.message);
            }
        } else {
            status.innerHTML = (result.message || 'No domains found');
            status.className = 'mailcow-check-status error';
            window.toast.error('CyberTemp', result.message || 'Failed to fetch domains');
        }
    } catch (e) {
        status.innerHTML = 'Error: ' + e;
        status.className = 'mailcow-check-status error';
        window.toast.error('CyberTemp', 'Failed to reach backend: ' + e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="mailcow-check-icon"></span> Refresh Domains';
    }
}

function restoreCybertempDomains() {
    const ct = mskSettings.email_providers && mskSettings.email_providers.cybertemp;
    if (!ct || !ct.cached_domains || !ct.cached_domains.length) return;

    const select = document.getElementById('settings-email-cybertemp-domain');
    if (!select) return;

    const savedDomain = ct.domain || 'random';
    select.innerHTML = '<option value="random">Random (All Domains)</option>';
    ct.cached_domains.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.domain;
        opt.textContent = d.domain + (d.tag === 'new' ? ' [new]' : '');
        select.appendChild(opt);
    });
    select.value = savedDomain;
    if (select.value !== savedDomain) select.value = 'random';

    updateCybertempRefreshTime();

    // Auto-refresh if last refresh was >24h ago
    if (ct.last_refresh) {
        const lastRefresh = new Date(ct.last_refresh);
        const now = new Date();
        const hoursSince = (now - lastRefresh) / (1000 * 60 * 60);
        if (hoursSince > 24) {
            setTimeout(() => refreshCybertempDomains(), 2000);
        }
    }
}

function updateCybertempRefreshTime() {
    const el = document.getElementById('cybertemp-last-refresh');
    if (!el) return;
    const ct = mskSettings.email_providers && mskSettings.email_providers.cybertemp;
    if (ct && ct.last_refresh) {
        const d = new Date(ct.last_refresh);
        el.textContent = d.toLocaleString();
    } else {
        el.textContent = 'never';
    }
}

async function refreshDuckmailDomains() {
    const btn = document.getElementById('duckmail-refresh-btn');
    const status = document.getElementById('duckmail-domain-status');
    const select = document.getElementById('settings-email-duckmail-domain');

    if (!select) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="mailcow-check-icon"></span> Loading...';
    status.textContent = '';
    status.className = 'mailcow-check-status';

    try {
        const result = await window.pywebview.api.check_duckmail_domains();
        if (result.success && result.domains && result.domains.length > 0) {
            const domains = trackRefreshedDomains('duckmail', result);
            const currentVal = select.value;
            select.innerHTML = '<option value="random">Random (All Domains)</option>';

            domains.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.domain;
                opt.textContent = d.domain + (d.tag === 'new' ? ' [new]' : '');
                select.appendChild(opt);
            });

            if (currentVal) {
                select.value = currentVal;
                if (select.value !== currentVal) select.value = 'random';
            }

            saveSettingsInstant();

            updateDuckmailRefreshTime();

            status.textContent = (result.cached ? 'Loaded ' : 'Found ') + domains.length + ' domains';
            status.className = 'mailcow-check-status success';
            if (result.cached) {
                window.toast.warning('DuckMail', result.message || 'Loaded cached domains');
            } else {
                window.toast.success('DuckMail', result.message);
            }
        } else {
            status.innerHTML = (result.message || 'No domains found');
            status.className = 'mailcow-check-status error';
            window.toast.error('DuckMail', result.message || 'Failed to fetch domains');
        }
    } catch (e) {
        status.innerHTML = 'Error: ' + e;
        status.className = 'mailcow-check-status error';
        window.toast.error('DuckMail', 'Failed to reach backend: ' + e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="mailcow-check-icon"></span> Refresh Domains';
    }
}

function restoreDuckmailDomains() {
    const dm = mskSettings.email_providers && mskSettings.email_providers.duckmail;
    if (!dm || !dm.cached_domains || !dm.cached_domains.length) return;

    const select = document.getElementById('settings-email-duckmail-domain');
    if (!select) return;

    const savedDomain = dm.domain || 'random';
    select.innerHTML = '<option value="random">Random (All Domains)</option>';
    dm.cached_domains.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.domain;
        opt.textContent = d.domain + (d.tag === 'new' ? ' [new]' : '');
        select.appendChild(opt);
    });
    select.value = savedDomain;
    if (select.value !== savedDomain) select.value = 'random';

    updateDuckmailRefreshTime();
}

function updateDuckmailRefreshTime() {
    const el = document.getElementById('duckmail-last-refresh');
    if (!el) return;
    const dm = mskSettings.email_providers && mskSettings.email_providers.duckmail;
    if (dm && dm.last_refresh) {
        const d = new Date(dm.last_refresh);
        el.textContent = d.toLocaleString();
    } else {
        el.textContent = 'never';
    }
}

// ── Translation System ─────────────────────────────────────────────

let translationCache = {};
let originalTexts = new Map();

async function initializeLanguages() {
    try {
        if (!window.pywebview || !window.pywebview.api) return;
        const result = await window.pywebview.api.get_supported_languages();
        if (result.success && result.languages) {
            const select = document.getElementById('settings-language');
            if (!select) return;

            // Keep English as the first option
            select.innerHTML = '';

            const enOpt = document.createElement('option');
            enOpt.value = 'en';
            enOpt.textContent = 'English (Default)';
            enOpt.setAttribute('data-original-name', 'English');
            select.appendChild(enOpt);

            result.languages.forEach(lang => {
                if (lang.code !== 'en') {
                    const opt = document.createElement('option');
                    opt.value = lang.code;
                    opt.textContent = lang.name;
                    opt.setAttribute('data-original-name', lang.name);
                    select.appendChild(opt);
                }
            });

            // Restore selected language
            if (mskSettings.language) {
                select.value = mskSettings.language;
            }
        }
    } catch (e) {
        console.error("Failed to fetch languages:", e);
    }
}

// Multi-language string cache: { 'it': { 'Hello': 'Ciao' }, 'de': { ... } }
let translatedStrings = {};

let _translateQueue = [];     // [{text, langCode, resolve, reject}]
let _translateTimer = null;
const _TRANSLATE_BATCH_DELAY = 150; // ms debounce

function _flushTranslateQueue() {
    _translateTimer = null;
    if (_translateQueue.length === 0) return;

    // Group by language code (in practice there's usually only one)
    const byLang = {};
    for (const item of _translateQueue) {
        if (!byLang[item.langCode]) byLang[item.langCode] = [];
        byLang[item.langCode].push(item);
    }
    _translateQueue = [];

    for (const [langCode, items] of Object.entries(byLang)) {
        const texts = items.map(it => it.text);
        window.pywebview.api.translate_texts(texts, langCode).then(result => {
            if (result.success && result.translations) {
                if (!translatedStrings[langCode]) translatedStrings[langCode] = {};
                result.translations.forEach((trans, i) => {
                    if (trans) {
                        translatedStrings[langCode][items[i].text] = trans;
                    }
                    items[i].resolve(trans || items[i].text);
                });
            } else {
                items.forEach(it => it.resolve(it.text));
            }
        }).catch(() => {
            items.forEach(it => it.resolve(it.text));
        });
    }
}

async function translateString(enText, langCode) {
    if (!enText || !langCode || langCode === 'en') return enText;

    // Check if it's "Loading" or contains "Loading" - User requested NOT to translate "Loading"
    if (enText.toLowerCase() === 'loading' || enText.toLowerCase().startsWith('loading...')) {
        return enText;
    }

    // Check for [Msk] prefix and extract core text
    let prefix = "";
    let textToTranslate = enText;
    if (enText.startsWith("[Msk] ")) {
        prefix = "[Msk] ";
        textToTranslate = enText.substring(6);
    }

    // Instant cache hit
    if (translatedStrings[langCode] && translatedStrings[langCode][textToTranslate]) {
        return prefix + translatedStrings[langCode][textToTranslate];
    }

    // Check if it contains ANSI codes
    const ansiRegex = /(\x1b\[[0-9;]*m)/g;
    if (ansiRegex.test(textToTranslate)) {
        // Split text by ANSI codes to preserve exact color placements
        const parts = textToTranslate.split(ansiRegex);
        let translatedText = "";

        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (!part) continue;

            // If it's an ANSI code, just append it directly
            if (part.startsWith('\x1b[')) {
                translatedText += part;
            } else {
                // Determine if this part has the '[Msk]' prefix or just needs direct translation
                let partToTranslate = part;
                let partPrefixHtml = "";

                // If it's the very first text part and has a prefix
                if (partToTranslate.includes('[') && partToTranslate.includes(']')) {
                    const prefixMatch = partToTranslate.match(/^.*\[.*?\].*?\s/);
                    if (prefixMatch) {
                        partPrefixHtml = prefixMatch[0];
                        partToTranslate = partToTranslate.substring(partPrefixHtml.length);
                    }
                }

                let translatedPart = await translateString(partToTranslate, langCode);
                translatedText += partPrefixHtml + translatedPart;
            }
        }

        return prefix + translatedText;
    }

    // Handle common dynamic patterns (no ANSI but maybe [Msk] prefix)
    const welcomeLoginMatch = textToTranslate.match(/^(.*?)Login successful! Welcome, (.*?)!$/i);
    if (welcomeLoginMatch) {
        const matchPrefix = welcomeLoginMatch[1];
        const name = welcomeLoginMatch[2];

        // Try exact match with ! first, then without
        let translatedLoginSuccess = await translateString("Login successful!", langCode);
        if (translatedLoginSuccess === "Login successful!") {
            translatedLoginSuccess = await translateString("Login successful", langCode);
            if (translatedLoginSuccess !== "Login successful") {
                translatedLoginSuccess += "!";
            }
        }

        const translatedWelcome = await translateString("Welcome", langCode);
        return `${prefix}${matchPrefix}${translatedLoginSuccess} ${translatedWelcome}, ${name}!`;
    }

    const welcomeMatch = textToTranslate.match(/^(.*?)Welcome, (.*?)!$/i);
    if (welcomeMatch) {
        const matchPrefix = welcomeMatch[1];
        const name = welcomeMatch[2];
        const translatedWelcome = await translateString("Welcome", langCode);
        return `${prefix}${matchPrefix}${translatedWelcome}, ${name}!`;
    }

    const statLogMatch = textToTranslate.match(/^(.*?)[├└]─ (.*?): (.*?)$/i);
    if (statLogMatch) {
        const matchPrefix = statLogMatch[1] + (textToTranslate.includes('├') ? '├' : '└') + '─ ';
        const statName = statLogMatch[2];
        const statValue = statLogMatch[3];
        const translatedStatName = await translateString(statName, langCode);
        const translatedStatValue = await translateString(statValue, langCode);
        return `${prefix}${matchPrefix}${translatedStatName}: ${translatedStatValue}`;
    }

    const connectedIpMatch = textToTranslate.match(/^(.*?)Connected to (.*?) IP: (.*?)$/i);
    if (connectedIpMatch) {
        const matchPrefix = connectedIpMatch[1];
        const provider = connectedIpMatch[2];
        const ip = connectedIpMatch[3];
        const translatedConnected = await translateString("Connected to", langCode);
        return `${prefix}${matchPrefix}${translatedConnected} ${provider} IP: ${ip}`;
    }

    // Queue for batched translation instead of individual HTTP call
    return new Promise((resolve, reject) => {
        _translateQueue.push({ text: textToTranslate, langCode, resolve: (val) => resolve(prefix + val), reject });
        if (_translateTimer) clearTimeout(_translateTimer);
        _translateTimer = setTimeout(_flushTranslateQueue, _TRANSLATE_BATCH_DELAY);
    });
}

async function translateDropdowns(langCode) {
    // Translate language names in the dropdown
    const langSelect = document.getElementById('settings-language');
    if (langSelect) {
        const langOptions = Array.from(langSelect.options);
        const namesToTranslate = langOptions.map(opt => {
            const baseName = opt.getAttribute('data-original-name') || opt.textContent.split(' (')[0];
            if (!opt.getAttribute('data-original-name')) {
                opt.setAttribute('data-original-name', baseName);
            }
            return baseName;
        });

        const langTranslations = await window.pywebview.api.translate_texts(namesToTranslate, langCode);
        if (langTranslations.success && langTranslations.translations) {
            const translatedDefaultWord = await translateString('Default', langCode);
            langOptions.forEach((opt, i) => {
                let translatedName = langTranslations.translations[i];
                if (translatedName && translatedName.length > 0) {
                    translatedName = translatedName.charAt(0).toUpperCase() + translatedName.slice(1);
                }

                if (opt.value === 'en') {
                    const defSuffix = langCode === 'en' ? '(Default)' : `(${translatedDefaultWord})`;
                    opt.textContent = `${translatedName} ${defSuffix}`;
                } else {
                    opt.textContent = translatedName;
                }
            });
        }
    }

    // Special handling for browser engine "Default"
    const browserSelect = document.getElementById('settings-browser-method');
    if (browserSelect) {
        for (let opt of browserSelect.options) {
            if (opt.textContent.includes('(Default)') || opt.hasAttribute('data-original-text')) {
                const originalText = opt.getAttribute('data-original-text') || opt.textContent;
                if (!opt.hasAttribute('data-original-text')) {
                    opt.setAttribute('data-original-text', originalText);
                }

                const engineName = originalText.split(' (')[0];
                const translatedDefault = langCode !== 'en' ? await translateString('Default', langCode) : 'Default';
                opt.textContent = `${engineName} (${translatedDefault})`;
            }
        }
    }
}

async function applyLanguage(langCode, isManual = true, showProgress = true) {
    if (!window.pywebview || !window.pywebview.api) return;

    // Show loading overlay for a "refresh" feel if not already visible
    const overlay = document.getElementById("loading-overlay");
    const progressText = document.getElementById("loading-status");
    const progressBar = document.getElementById("loading-progress");
    const wasVisible = overlay && (overlay.style.display === "flex" || overlay.style.display === "block");

    if (overlay && !wasVisible && showProgress) {
        overlay.style.display = "flex";
        if (progressText && isManual) progressText.textContent = "Scanning UI elements...";
        if (progressBar && isManual) progressBar.style.width = "0%";
        if (isManual) await new Promise(r => setTimeout(r, 100));
        if (progressBar && isManual) progressBar.style.width = "5%";
    }

    if (langCode === 'en') {
        if (isManual && progressText) progressText.textContent = "Restoring English UI...";
        if (isManual && progressBar) progressBar.style.width = "25%";
        restoreOriginalTexts();
        await translateDropdowns('en');
        if (isManual && progressBar) progressBar.style.width = "100%";
        if (isManual && progressText) progressText.textContent = "UI restored to English!";
        if (isManual) await new Promise(r => setTimeout(r, 450));
        if (overlay && !wasVisible && showProgress) overlay.style.display = "none";
        if (isManual) window.toast.success('Language', 'UI restored to English!');
        return;
    }

    // Identify all elements with text to translate
    const rawElements = document.querySelectorAll('h1, h2, h3, p, span, label, button, .tab-btn, .setting-description, .stat-label, option, .detect-gauge-subtitle, .detect-gauge-status, .btn-text, .detect-empty-text, .detect-modal h3, .detect-modal p, #refresh-account-btn');
    const elements = Array.from(new Set(rawElements));
    const placeholders = Array.from(new Set(document.querySelectorAll('input[placeholder], textarea[placeholder]')));
    const titledElements = Array.from(new Set(document.querySelectorAll('[title]')));

    let textsToTranslate = [];
    let elementsToUpdate = [];

    // Collect text from elements
    elements.forEach(el => {
        if (el.classList.contains('no-translate') || el.closest('.no-translate')) return;
        if (el.closest('#log-container')) return;
        if (el.closest('.output-file-item')) return;
        if (el.closest('#settings-browser-method')) return;
        if (el.closest('#settings-language')) return;

        // Special handling for elements with children but no direct text node sometimes
        if (el.id === 'refresh-account-btn') {
            const text = el.innerText.trim();
            if (text.length > 1) {
                let sourceText = originalTexts.get(el) || text;
                if (!originalTexts.has(el)) {
                    originalTexts.set(el, text);
                }
                textsToTranslate.push(sourceText);
                elementsToUpdate.push({ type: 'button-text', node: el });
            }
            return;
        }

        for (let node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.trim();
                if (text.length > 1) {
                    if (text.toLowerCase().includes('loading')) {
                        if (text.toLowerCase() === 'loading...') return;
                        if (text.toLowerCase().startsWith('loading')) return;
                    }

                    let sourceText = originalTexts.get(node) || text;
                    if (!originalTexts.has(node)) {
                        originalTexts.set(node, text);
                    }
                    textsToTranslate.push(sourceText);
                    elementsToUpdate.push({ type: 'text', node: node });
                }
            }
        }
    });

    // Collect placeholders
    placeholders.forEach(el => {
        if (el.classList.contains('no-translate') || el.closest('.no-translate')) return;
        const text = el.placeholder.trim();
        if (text.length > 1) {
            if (text.toLowerCase().includes('loading')) return;
            const sourceText = originalTexts.get(el) || text;
            if (!originalTexts.has(el)) {
                originalTexts.set(el, text);
            }
            textsToTranslate.push(sourceText);
            elementsToUpdate.push({ type: 'placeholder', node: el });
        }
    });

    // Collect titles (tooltips)
    titledElements.forEach(el => {
        if (el.classList.contains('no-translate') || el.closest('.no-translate')) return;
        const text = el.title.trim();
        if (text.length > 1) {
            if (text.toLowerCase().includes('loading')) return;
            const sourceText = el.dataset.originalTitle || text;
            if (!el.dataset.originalTitle) {
                el.dataset.originalTitle = text;
            }
            textsToTranslate.push(sourceText);
            elementsToUpdate.push({ type: 'title', node: el });
        }
    });

    if (textsToTranslate.length === 0) {
        if (overlay && !wasVisible && showProgress) overlay.style.display = "none";
        return;
    }

    if (isManual && progressText) {
        progressText.textContent = `Preparing translation...`;
        if (progressBar && isManual) progressBar.style.width = "15%";
        await new Promise(r => setTimeout(r, 300));
    }

    try {
        const chunkSize = 100;
        const totalChunks = Math.ceil(textsToTranslate.length / chunkSize);
        let completedChunks = 0;

        if (isManual && progressText) {
            progressText.textContent = `Contacting translation server...`;
            if (progressBar && isManual) progressBar.style.width = "30%";
            await new Promise(r => setTimeout(r, 300));
        }

        const chunkPromises = [];
        for (let i = 0; i < textsToTranslate.length; i += chunkSize) {
            const chunk = textsToTranslate.slice(i, i + chunkSize);
            const promise = window.pywebview.api.translate_texts(chunk, langCode).then(result => {
                completedChunks++;
                // Scale 30% to 70% (40% range)
                const chunkPercent = Math.round(30 + (completedChunks / totalChunks) * 40);
                if (progressBar && isManual) {
                    progressBar.style.width = chunkPercent + "%";
                }
                if (progressText && isManual) {
                    progressText.textContent = `Receiving data...`;
                }
                return { result, index: i };
            });
            chunkPromises.push(promise);
        }

        const results = await Promise.all(chunkPromises);
        results.sort((a, b) => a.index - b.index);

        if (isManual && progressText) {
            progressText.textContent = "Processing translations...";
            if (progressBar && isManual) progressBar.style.width = "75%";
            await new Promise(r => setTimeout(r, 300));
        }

        let allTranslations = [];
        results.forEach(({ result, index }) => {
            if (result.success && result.translations) {
                allTranslations = allTranslations.concat(result.translations);
            } else {
                const chunk = textsToTranslate.slice(index, index + chunkSize);
                allTranslations = allTranslations.concat(chunk);
            }
        });

        if (isManual && progressText) {
            progressText.textContent = "Applying changes to UI...";
            if (progressBar && isManual) progressBar.style.width = "85%";
            await new Promise(r => setTimeout(r, 400));
        }

        // Apply translations
        allTranslations.forEach((translatedText, index) => {
            const item = elementsToUpdate[index];
            if (item && translatedText) {
                // Ensure section names (tabs and H2) have only initial capitalization
                let finalText = translatedText;
                if (item.type === 'text' && item.node.parentElement && (
                    item.node.parentElement.classList.contains('tab-btn') ||
                    item.node.parentElement.tagName === 'H2'
                )) {
                    finalText = translatedText.charAt(0).toUpperCase() + translatedText.slice(1).toLowerCase();
                }

                if (item.type === 'text') {
                    item.node.textContent = finalText;
                } else if (item.type === 'button-text') {
                    item.node.innerText = finalText;
                } else if (item.type === 'placeholder') {
                    item.node.placeholder = finalText;
                } else if (item.type === 'title') {
                    item.node.title = finalText;
                }
            }
        });

        if (isManual && progressText) {
            progressText.textContent = "Finalizing UI updates...";
            if (progressBar && isManual) progressBar.style.width = "95%";
        }
        await translateDropdowns(langCode);

        if (progressBar && isManual) progressBar.style.width = "100%";
        if (progressText && !wasVisible && isManual) {
            progressText.textContent = "UI updated successfully!";
            await new Promise(r => setTimeout(r, 450));
        }

        if (overlay && !wasVisible && showProgress) overlay.style.display = "none";

        if (isManual) window.toast.success('Language', 'UI updated successfully!');
    } catch (e) {
        console.error("Translation error:", e);
        if (overlay && !wasVisible && showProgress) overlay.style.display = "none";
        if (isManual) window.toast.error('Translation Error', 'Failed to translate UI: ' + (e.message || 'Unknown error'));
    }
}

function restoreOriginalTexts() {
    originalTexts.forEach((originalText, node) => {
        if (node.nodeType === Node.TEXT_NODE) {
            node.textContent = originalText;
        } else if (node.id === 'refresh-account-btn') {
            node.innerText = originalText;
        } else if (node.placeholder !== undefined) {
            node.placeholder = originalText;
        }
    });

    // Also restore titles
    document.querySelectorAll('[data-original-title]').forEach(el => {
        el.title = el.dataset.originalTitle;
    });
}

// ── End Translation System ─────────────────────────────────────────────

async function testWebhook() {
    const btn = document.getElementById('test-webhook-btn');
    const url = (document.getElementById('settings-webhook-url') || {}).value || '';
    if (!url) {
        showToast('Please enter a webhook URL first.', 'error');
        return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
    try {
        if (!window.pywebview || !window.pywebview.api) throw new Error('No API');
        const result = await window.pywebview.api.test_webhook(url);
        if (result && result.success) {
            showToast('Test embed sent successfully!', 'success');
        } else {
            showToast('Webhook test failed: ' + (result && result.error ? result.error : 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Webhook test error: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Send Test'; }
    }
}



window.loadSettingsFromBackend = loadSettingsFromBackend;
window.testWebhook = testWebhook;
window.mskSettings = mskSettings;
window.checkMailcowApi = checkMailcowApi;
window.refreshCybertempDomains = refreshCybertempDomains;
window.refreshDuckmailDomains = refreshDuckmailDomains;
window.initializeLanguages = initializeLanguages;
window.applyLanguage = applyLanguage;
window.translateString = translateString;
window.loadTrainingStats = loadTrainingStats;

document.addEventListener('DOMContentLoaded', () => {
    loadTrainingStats();
});
