/**
 * MSK Stealth Fingerprint Injection
 * Injected via Playwright add_init_script() — runs BEFORE any page JS.
 * Each session gets a unique seed (window.__msk_seed) set by Python.
 *
 * IMPORTANT: Canvas/WebGL noise and timing jitter have been deliberately
 * removed. Strict ML-based tamper classifiers (hCaptcha, Discord) detect
 * the noise pattern itself as a tampering signal — coherent real values
 * score significantly better than synthetically perturbed ones.
 */
(function () {
    'use strict';

    // ── Seeded PRNG (mulberry32) — stateful, advances on every call ──
    const SEED = (window.__msk_seed || Math.random().toString(36).slice(2) + Date.now());
    let _prng_h;
    (function() {
        _prng_h = 0xdeadbeef;
        for (let i = 0; i < SEED.length; i++) {
            _prng_h = Math.imul(_prng_h ^ SEED.charCodeAt(i), 2654435761);
        }
        _prng_h = _prng_h >>> 0;
    })();
    const rng = function () {
        _prng_h |= 0; _prng_h = _prng_h + 0x6D2B79F5 | 0;
        let t = Math.imul(_prng_h ^ (_prng_h >>> 15), 1 | _prng_h);
        t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    function _choice(arr) { return arr[Math.floor(rng() * arr.length)]; }
    function _int(min, max) { return Math.floor(rng() * (max - min + 1)) + min; }

    // ── 1. Remove webdriver flag ──
    try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
    } catch (e) { }

    // ── 2. Remove Brave-specific APIs ──
    try { delete navigator.brave; } catch (e) { }
    try {
        if (window.navigator.brave) {
            Object.defineProperty(window.navigator, 'brave', { get: () => undefined, configurable: true });
        }
    } catch (e) { }

    // ── 3. Add window.chrome (missing in automation) ──
    try {
        if (!window.chrome) {
            window.chrome = {
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
                },
                runtime: {
                    OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                    PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                    PlatformArch: { ARM: 'arm', ARM64: 'arm64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
                    id: undefined,
                    connect: function () { return {}; },
                    sendMessage: function () { },
                },
                csi: function () { },
                loadTimes: function () { return {}; },
            };
        }
    } catch (e) { }

    // ── 4. Remove CDP / automation artifacts ──
    try {
        const cdpProps = [
            'cdc_adoQpoasnfa76pfcZLmcfl_Array',
            'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
            'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
            '__playwright_target__',
            '__pwInitScripts',
        ];
        for (const p of cdpProps) {
            try { delete window[p]; } catch (_) { }
        }
    } catch (e) { }

    // ── 5. Realistic hardware concurrency & device memory ──
    try {
        const cores = _choice([4, 6, 8, 12, 16]);
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => cores, configurable: true });
    } catch (e) { }
    try {
        const mem = _choice([4, 8, 16]);
        Object.defineProperty(navigator, 'deviceMemory', { get: () => mem, configurable: true });
    } catch (e) { }

    // ── 6. Platform ──
    try {
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32', configurable: true });
    } catch (e) { }

    // ── 7. Language ──
    try {
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
        Object.defineProperty(navigator, 'language', { get: () => 'en-US', configurable: true });
    } catch (e) { }

    // ── 8. Screen dimensions — realistic per session ──
    try {
        const resolutions = [
            [1920, 1080], [2560, 1440], [1366, 768],
            [1440, 900], [1536, 864], [1600, 900], [1280, 800],
        ];
        const [sw, sh] = _choice(resolutions);
        const taskbarH = _int(36, 48);
        Object.defineProperty(screen, 'width', { get: () => sw, configurable: true });
        Object.defineProperty(screen, 'height', { get: () => sh, configurable: true });
        Object.defineProperty(screen, 'availWidth', { get: () => sw, configurable: true });
        Object.defineProperty(screen, 'availHeight', { get: () => sh - taskbarH, configurable: true });
        Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });
        Object.defineProperty(window, 'outerWidth', { get: () => sw, configurable: true });
        Object.defineProperty(window, 'outerHeight', { get: () => sh, configurable: true });
    } catch (e) { }

    // ── 9. userAgentData — coherent with Camoufox Firefox engine ──
    // NOTE: Camoufox is Firefox-based so userAgentData is not present by default.
    // If it is somehow exposed, patch it to be coherent.
    try {
        if (navigator.userAgentData) {
            const brands = [
                { brand: 'Not/A)Brand', version: '8' },
                { brand: 'Chromium', version: '136' },
                { brand: 'Google Chrome', version: '136' }
            ];
            Object.defineProperty(navigator.userAgentData, 'brands', { get: () => brands, configurable: true });
            Object.defineProperty(navigator.userAgentData, 'mobile', { get: () => false, configurable: true });
            Object.defineProperty(navigator.userAgentData, 'platform', { get: () => 'Windows', configurable: true });
        }
    } catch (e) { }

    // ── 10. Plugins & MimeTypes (Legacy but checked) ──
    try {
        const plugins = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Google Chrome PDF Viewer' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Chromium PDF Viewer' },
            { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Microsoft Edge PDF Viewer' },
            { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'WebKit built-in PDF' }
        ];

        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const p = [...plugins];
                p.item = p.namedItem = (i) => p[i] || null;
                p.refresh = () => { };
                return p;
            },
            configurable: true
        });

        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => {
                const m = [{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }];
                m.item = m.namedItem = (i) => m[i] || null;
                return m;
            },
            configurable: true
        });
    } catch (e) { }

    // ── 11. WebGL vendor & renderer — unique per session ──
    // NOTE: Only spoofing the UNMASKED strings. Real GL calls pass through
    // untouched so the output cluster matches real hardware. No canvas noise.
    try {
        const UNMASKED_VENDOR = 0x9245;
        const UNMASKED_RENDERER = 0x9246;
        const vendors = ['Google Inc. (NVIDIA)', 'Google Inc. (Intel)', 'Google Inc. (AMD)'];
        const renderers = [
            'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (AMD, Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (NVIDIA, NVIDIA GeForce RTX 2070 Direct3D11 vs_5_0 ps_5_0, D3D11)',
        ];
        const vendor = _choice(vendors);
        const renderer = _choice(renderers);

        function patchWebGL(ctx) {
            if (!ctx) return;
            const origGetParam = ctx.prototype.getParameter;
            ctx.prototype.getParameter = function (p) {
                if (p === UNMASKED_VENDOR) return vendor;
                if (p === UNMASKED_RENDERER) return renderer;
                return origGetParam.call(this, p);
            };
        }
        patchWebGL(WebGLRenderingContext);
        if (typeof WebGL2RenderingContext !== 'undefined') {
            patchWebGL(WebGL2RenderingContext);
        }
    } catch (e) { }

    // ── 12. Permissions — avoid notification detection ──
    try {
        const _origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = function (params) {
            if (params && params.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission, onchange: null });
            }
            return _origQuery.call(this, params);
        };
    } catch (e) { }

    // ── 13. Hide MSK-injected globals from enumeration ──
    try {
        const _mskGlobals = [
            '__hcap_bridge', '__hcapListenerActive', '__hcapSenderActive',
            '__hcLangPatched', '__msk_seed', '__mskNopechaSolve__',
        ];
        setTimeout(() => {
            _mskGlobals.forEach(k => {
                try {
                    if (k in window) {
                        Object.defineProperty(window, k, { enumerable: false, configurable: true });
                    }
                } catch(e) {}
            });
        }, 500);
    } catch (e) { }

})();

