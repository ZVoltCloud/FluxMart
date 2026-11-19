"""
Discord registration using Botasaurus Driver (Chromium 2).

Botasaurus Driver has superior anti-detection built into the C++ level:
  - No CDP automation flags leaked
  - No navigator.webdriver
  - No window.chrome issues
  - Built-in proxy auth support
  - Human-like mouse movements
  - No stealth JS injection needed -- the driver itself is undetectable
"""

import os
import sys
import time
import random
import re
import string
import tempfile
import shutil
import warnings
from typing import Optional, Dict, Tuple, List

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)


from ..MskColors.color import MskColor
from ..Utils.utils import Utils, Config, get_base_path, get_resource_path
from ..Utils.logger import Logger
from ..Utils.proxy_manager import ProxyManager


class GeneratorStoppedError(Exception):
    """Raised when the user stops generation mid-flow."""
    pass


class DiscordRegisterChromium2:
    """Discord account registration using Botasaurus Driver (Chromium 2)."""

    def __init__(self):
        self.proxy_manager = ProxyManager("data/input/proxies.txt")
        self.password = Utils.random_password()
        self._driver = None
        self._zeus_refresh_token = ""
        self._zeus_client_id = ""

    def _check_stop(self):
        if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):
            raise GeneratorStoppedError("Stopped by user")
        if hasattr(self, '_trigger_parent') and getattr(self._trigger_parent, 'should_stop', False):
            raise GeneratorStoppedError("Stopped by user")

    def _sleep(self, seconds):
        remaining = seconds
        while remaining > 0:
            self._check_stop()
            chunk = min(remaining, 0.5)
            time.sleep(chunk)
            remaining -= chunk

    @property
    def config(self) -> Dict:
        return Config.config

    def _js(self, script: str, timeout: int = 30):
        """Run JS on the driver safely.
        
        Botasaurus run_js requires 'return' to get a value back.
        Auto-prepend 'return' only for IIFE expressions that start with '('.
        Async IIFEs and other statements are passed as-is.
        """
        if self._driver is None:
            return None
        try:
            self._check_stop()
        except Exception:
            return None
        try:
            s = script.strip()
            # Only auto-return for sync IIFEs: (() => {...})() or (function(){...})()
            if s.startswith('(') and not s.startswith('(async'):
                if not s.startswith('return '):
                    s = 'return ' + s
            return self._driver.run_js(s, timeout=timeout)
        except Exception as e:
            err_msg = str(e)[:120]
            noise = ['timeout', 'close', 'target', 'session', 'websocket',
                     'nonetype', 'has no attribute', 'connection', 'refused',
                     'referenceerror']
            if not any(m in err_msg.lower() for m in noise):
                try:
                    Logger.STATUS = f"{MskColor.GREY}JS: {err_msg}"
                    Logger.queue_log(worker_id=0)
                except Exception:
                    pass
            return None

    def _create_browser(self, headless: bool = False, proxy: Optional[Dict] = None, wm_pos: Optional[tuple] = None):
        """Start Botasaurus Driver and navigate to Discord register."""
        from botasaurus_driver import Driver

        # Resolve proxy geo for locale/timezone matching
        _geo_locale = "en-US"
        _geo_tz = "America/New_York"
        if proxy and proxy.get("server"):
            try:
                from ..Utils.geo_lookup import lookup_proxy_geo
                _geo_tz, _geo_locale = lookup_proxy_geo(proxy)
            except Exception:
                pass

        # Build proxy string for botasaurus
        proxy_str = None
        if proxy and proxy.get("server"):
            server_raw = proxy["server"]
            if "://" in server_raw:
                server_raw = server_raw.split("://", 1)[1]
            username = proxy.get("username", "")
            password = proxy.get("password", "")
            if username and password:
                proxy_str = f"http://{username}:{password}@{server_raw}"
            else:
                proxy_str = f"http://{server_raw}"

        # Window size
        window_size = None
        if wm_pos and len(wm_pos) >= 4:
            window_size = (wm_pos[2], wm_pos[3])
        else:
            window_size = (1920, 1080)

        # Extra chrome arguments for stealth
        extra_args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--no-service-autorun",
            "--password-store=basic",
            "--disable-background-networking",
            "--metrics-recording-only",
            f"--lang={_geo_locale}",
        ]

        if headless:
            extra_args.append("--window-position=-10000,-10000")

        driver = Driver(
            headless=headless,
            proxy=proxy_str,
            block_images=False,
            wait_for_complete_page_load=True,
            window_size=window_size,
            lang=_geo_locale,
            arguments=extra_args,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        )

        self._driver = driver
        self._extracted_token = None

        # Capture Discord authorization token directly from HTTP request headers
        def _on_request(request_id, request, request_will_be_sent):
            try:
                headers = getattr(request, "headers", {}) or {}
                for k, v in headers.items():
                    if k.lower() == 'authorization' and v:
                        raw_v = str(v).strip().strip('"').strip("'")
                        if len(raw_v) > 50 and '.' in raw_v and '{' not in raw_v and '<' not in raw_v:
                            self._extracted_token = raw_v
            except Exception:
                pass

        try:
            driver.before_request_sent(_on_request)
        except Exception:
            pass

        # Inject hCaptcha postMessage bridge for text solver
        try:
            from .text_solver_truedriver import _HCAP_BRIDGE_JS
            driver.run_on_new_document(_HCAP_BRIDGE_JS)
        except Exception:
            pass

        # Inject token capture hook for fetch and XMLHttpRequest
        _token_hook_js = r"""
(function(){
    function saveToken(t) {
        if (!t || typeof t !== 'string') return;
        t = t.trim().replace(/^["']|["']$/g, '');
        if (t.length > 50 && t.indexOf('.') > -1 && t.indexOf('{') === -1 && t.indexOf('<') === -1) {
            window.__discord_token = t;
            try { window.localStorage.setItem('token', t); } catch(e) {}
        }
    }

    try {
        const origFetch = window.fetch;
        window.fetch = function(...args) {
            try {
                const opts = args[1] || {};
                if (opts.headers) {
                    if (opts.headers instanceof Headers) {
                        saveToken(opts.headers.get('Authorization') || opts.headers.get('authorization'));
                    } else if (typeof opts.headers === 'object') {
                        for (const k in opts.headers) {
                            if (k.toLowerCase() === 'authorization') saveToken(opts.headers[k]);
                        }
                    }
                }
            } catch(e) {}
            return origFetch.apply(this, args).then(res => {
                try {
                    const clone = res.clone();
                    clone.json().then(data => {
                        if (data && data.token) saveToken(data.token);
                    }).catch(() => {});
                } catch(e) {}
                return res;
            });
        };
    } catch(e) {}

    try {
        const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
            try {
                if (header && header.toLowerCase() === 'authorization') saveToken(value);
            } catch(e) {}
            return origSetHeader.apply(this, arguments);
        };
        const origOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function() {
            this.addEventListener('load', function() {
                try {
                    if (this.responseText) {
                        const data = JSON.parse(this.responseText);
                        if (data && data.token) saveToken(data.token);
                    }
                } catch(e) {}
            });
            return origOpen.apply(this, arguments);
        };
    } catch(e) {}
})();
"""
        try:
            driver.run_on_new_document(_token_hook_js)
        except Exception:
            pass

        # Inject minimal stealth -- botasaurus handles most of it natively
        _stealth_js = r"""
(function(){
    // Hide any residual CDP signals
    try {
        const leaks = ['__driver_evaluate','__webdriver_evaluate','__selenium_evaluate',
            'cdc_adoQpoasnfa76pfcZLmcfl_Array','cdc_adoQpoasnfa76pfcZLmcfl_Promise',
            '__puppeteer_evaluation_script__','__playwright_target__','domAutomation',
            'domAutomationController'];
        leaks.forEach(k => { try { delete window[k]; } catch(e) {} });
    } catch(e) {}

    // Realistic permissions.query
    try {
        const _origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function(params) {
            if (params && params.name === 'notifications')
                return Promise.resolve({ state: Notification.permission || 'default', onchange: null });
            return _origQuery(params);
        };
    } catch(e) {}
})();
"""
        try:
            driver.run_on_new_document(_stealth_js)
        except Exception:
            pass

        # Set locale and timezone to match proxy
        try:
            driver.set_locale_and_timezone(locale=_geo_locale, timezone_id=_geo_tz)
        except Exception:
            pass

        # Navigate to Discord register
        driver.get("https://discord.com/register")
        return driver

    def _cleanup(self):
        self._driver_ref = self._driver
        self._driver = None  # Immediately prevent _js() calls
        try:
            if self._driver_ref:
                self._driver_ref.close()
        except Exception:
            pass
        self._driver_ref = None

    def _check_passed(self) -> bool:
        result = self._js("""
            (() => {
                const url = window.location.href || '';
                const frames = document.querySelectorAll('iframe[src*="hcaptcha"]');
                for (const f of frames) {
                    const rect = f.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) return 'captcha_visible';
                }
                if (url.includes('/channels') || url.includes('/@me') || url.includes('/app')) {
                    if (!url.includes('/register')) return 'passed_url';
                }
                if (url.includes('check-your-email') || url.includes('/verify')) return 'passed_url';
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        let k = localStorage.key(i);
                        if (k && k.toLowerCase().includes('token')) {
                            let v = localStorage.getItem(k);
                            if (v && v.length > 50 && !v.includes('{')) return 'passed_token';
                        }
                    }
                } catch(e) {}
                return 'not_passed';
            })()
        """)
        return result in ('passed_url', 'passed_token')

    def _has_hcaptcha(self) -> bool:
        return bool(self._js("""
            (() => {
                const frames = document.querySelectorAll('iframe');
                for (const f of frames) {
                    const src = (f.getAttribute('src') || '').toLowerCase();
                    if (src.includes('hcaptcha')) {
                        const rect = f.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return true;
                    }
                }
                if (document.querySelector('[data-hcaptcha-widget-id]')) return true;
                if (document.querySelector('.h-captcha')) return true;
                return false;
            })()
        """))

    def _extract_token(self) -> Optional[str]:
        # 1. Captured from HTTP request headers (most reliable on modern Discord)
        if getattr(self, "_extracted_token", None):
            token = self._clean_token(self._extracted_token)
            if token:
                return token

        # 2. Extract from window.__discord_token, webpack module store, or browser storage
        raw = self._js("""
            (() => {
                try {
                    if (window.__discord_token) return window.__discord_token;
                } catch(e) {}
                try {
                    if (window.webpackChunkdiscord_app) {
                        let token = null;
                        window.webpackChunkdiscord_app.push([
                            [Symbol()],
                            {},
                            (req) => {
                                for (const m of Object.values(req.c)) {
                                    try {
                                        const exp = m?.exports;
                                        if (exp?.default?.getToken) {
                                            const t = exp.default.getToken();
                                            if (t) { token = t; break; }
                                        }
                                        if (exp?.getToken) {
                                            const t = exp.getToken();
                                            if (t) { token = t; break; }
                                        }
                                    } catch(_) {}
                                }
                            }
                        ]);
                        if (token) return token;
                    }
                } catch(e) {}
                try {
                    var t = window.localStorage.getItem('token');
                    if (t) return t;
                } catch(e) {}
                try {
                    for (var i = 0; i < window.localStorage.length; i++) {
                        var k = window.localStorage.key(i);
                        var v = window.localStorage.getItem(k) || '';
                        v = v.replace(/"/g, '').trim();
                        if (v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1 && v.indexOf('<') === -1) return v;
                    }
                } catch(e) {}
                try {
                    for (var i = 0; i < window.sessionStorage.length; i++) {
                        var k = window.sessionStorage.key(i);
                        var v = window.sessionStorage.getItem(k) || '';
                        v = v.replace(/"/g, '').trim();
                        if (v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1 && v.indexOf('<') === -1) return v;
                    }
                } catch(e) {}
                return null;
            })()
        """)
        token = self._clean_token(raw)
        if token:
            self._extracted_token = token
            return token
        return None

    @staticmethod
    def _clean_token(raw) -> Optional[str]:
        if raw is None:
            return None
        if not isinstance(raw, str):
            raw = str(raw)
        token = raw.strip().strip('"').strip("'").strip()
        if len(token) > 50 and '.' in token and '{' not in token and '<' not in token and not token.startswith('('):
            return token
        return None

    def _fill_field(self, selectors: str, value: str, field_name: str, worker_id: int) -> bool:
        """Fill an input field via native React setter + _valueTracker reset so it works even when window is unfocused."""
        safe_val = value.replace('\\', '\\\\').replace("'", "\\'")
        result = self._js(f"""
            (() => {{
                const selectors = {selectors};
                let el = null;
                for (const sel of selectors) {{
                    const found = document.querySelector(sel);
                    if (found && found.offsetParent !== null) {{ el = found; break; }}
                }}
                if (!el) {{
                    const allInps = document.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"])');
                    for (const inp of allInps) {{
                        const name = (inp.getAttribute('name') || '').toLowerCase();
                        const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
                        const label = (inp.getAttribute('aria-label') || '').toLowerCase();
                        const fieldLower = '{field_name}'.toLowerCase();
                        if (name.includes(fieldLower) || ph.includes(fieldLower) || label.includes(fieldLower)) {{
                            el = inp;
                            break;
                        }}
                    }}
                }}

                if (!el) return 'NOT_FOUND';

                el.scrollIntoView({{block: 'center', behavior: 'instant'}});
                el.focus();
                el.click();

                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, '{safe_val}');

                const tracker = el._valueTracker;
                if (tracker) {{
                    tracker.setValue('');
                }}

                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));

                return el.value === '{safe_val}' ? 'OK' : 'VALUE_MISMATCH';
            }})()
        """)
        return result == 'OK'

    def _fill_form(self, email: str, username: str, worker_id: int):
        """Fill Discord registration form field by field without requiring OS window focus."""
        display_name = username[:8]
        driver = self._driver
        if not driver:
            return

        # Use React-safe JS setter first so input never fails when another app is focused
        self._fill_field(
            '["input[name=\\"email\\"]", "input[type=\\"email\\"]", "input[autocomplete=\\"email\\"]", "input[placeholder*=\\"email\\" i]"]',
            email, "email", worker_id
        )
        self._sleep(0.1)

        self._fill_field(
            '["input[name=\\"global_name\\"]", "input[name=\\"display_name\\"]", "input[aria-label*=\\"display\\" i]"]',
            display_name, "display", worker_id
        )
        self._sleep(0.1)

        self._fill_field(
            '["input[name=\\"username\\"]", "input[autocomplete=\\"username\\"]", "input[aria-label*=\\"username\\" i]"]',
            username, "username", worker_id
        )
        self._sleep(0.1)

        self._fill_field(
            '["input[name=\\"password\\"]", "input[type=\\"password\\"]", "input[autocomplete=\\"new-password\\"]"]',
            self.password, "password", worker_id
        )
        self._sleep(0.15)

        # Fill DOB using JS (dropdowns require JS interaction)
        month_idx = random.randint(0, 11)
        day = str(random.randint(1, 28))
        year = str(random.randint(1995, 2007))

        self._js(f"""
        (async () => {{
            const delay = ms => new Promise(r => setTimeout(r, ms));

            const selectOption = async (dropdownLabelRegex, targetValue, isIndex = false) => {{
                const allElements = Array.from(document.querySelectorAll('*'));
                let btn = allElements.find(el => {{
                    const label = el.getAttribute('aria-label') || '';
                    return dropdownLabelRegex.test(label) && (el.getAttribute('role') === 'button' || el.hasAttribute('aria-haspopup'));
                }});
                if (!btn) {{
                    const textElem = allElements.find(el => dropdownLabelRegex.test(el.innerText) && (el.tagName === 'SPAN' || el.tagName === 'DIV'));
                    if (textElem) btn = textElem.closest('[role="button"], [aria-haspopup="listbox"], [class*="container"]');
                }}
                if (!btn) {{
                    const clickable = allElements.find(el => {{
                        const text = (el.innerText || '').trim();
                        return dropdownLabelRegex.test(text) && el.offsetParent !== null
                            && (el.tagName === 'DIV' || el.tagName === 'SPAN')
                            && el.getBoundingClientRect().width > 30;
                    }});
                    if (clickable) btn = clickable.closest('[class*="css-"]') || clickable;
                }}
                if (!btn) return false;
                btn.scrollIntoView({{behavior: 'instant', block: 'center'}});
                btn.click();
                await delay(250);
                let options = Array.from(document.querySelectorAll('[role="option"]'));
                if (options.length === 0) return false;
                if (isIndex) {{
                    const target = options[targetValue - 1];
                    if (target) {{ target.scrollIntoView({{block:'nearest'}}); target.click(); return true; }}
                    return false;
                }}
                // Direct match first -- exact only to avoid partial matches (e.g. "13" matching "2013")
                let target = options.find(o => o.innerText.trim() === targetValue);
                if (target) {{ target.scrollIntoView({{block:'nearest'}}); target.click(); return true; }}
                // Scroll to find the option (for year dropdown which has many entries)
                let container = null;
                let el = options[0];
                while (el && el !== document.body) {{
                    const s = window.getComputedStyle(el);
                    if (s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflow === 'auto' || s.overflow === 'scroll') {{
                        container = el; break;
                    }}
                    el = el.parentElement;
                }}
                if (!container) return false;
                // Reset scroll to top to scan complete list
                container.scrollTop = 0;
                await delay(80);
                for (let i = 0; i < 250; i++) {{
                    options = Array.from(document.querySelectorAll('[role="option"]'));
                    target = options.find(o => o.innerText.trim() === targetValue);
                    if (target) break;
                    container.scrollTop += 120;
                    await delay(25);
                }}
                if (!target) return false;
                target.scrollIntoView({{block: 'nearest'}});
                await delay(40);
                target.click();
                return true;
            }};

            await selectOption(/Month|Maand|Mois|Mes|Mês|Mese|Monat/i, {month_idx + 1}, true);
            await delay(150);
            await selectOption(/Day|Dag|Jour|Día|Dia|Giorno|Tag/i, "{day}");
            await delay(150);
            await selectOption(/Year|Jaar|Année|Año|Ano|Anno|Jahr/i, "{year}");
            await delay(200);

            // Handle ToS checkbox
            try {{
                const tosKw = ['terms of service', 'privacy policy', 'agree', 'consent', 'accept',
                               'nutzungsbedingungen', 'condiciones', 'conditions', 'termini'];
                for (const lbl of Array.from(document.querySelectorAll('label'))) {{
                    const t = (lbl.innerText || '').toLowerCase();
                    if (!tosKw.some(kw => t.includes(kw))) continue;
                    const cb = lbl.querySelector('input[type="checkbox"]');
                    if (cb && !cb.checked) {{ cb.click(); await delay(80); }}
                    else {{ lbl.click(); await delay(80); }}
                    break;
                }}
                for (const cb of Array.from(document.querySelectorAll('input[type="checkbox"]'))) {{
                    if (cb.checked) continue;
                    const par = cb.closest('label,div,li') || cb.parentElement;
                    const t = (par ? par.innerText || '' : '').toLowerCase();
                    if (tosKw.some(kw => t.includes(kw))) {{
                        cb.click(); await delay(80); break;
                    }}
                }}
            }} catch(e) {{}}

            // NOTE: Do NOT click submit here -- _submit_form() handles that
            // separately after this async IIFE. Clicking submit from inside the
            // IIFE AND from _submit_form caused a double registration API call
            // which Discord rate-limits or treats as a duplicate.
        }})();
        """)

    def _submit_form(self, worker_id: int = 0):
        """Click the submit button using botasaurus native click."""
        if not self._driver:
            return
        try:
            if self._driver.is_element_present('button[type="submit"]', wait=2):
                self._driver.click('button[type="submit"]', wait=2)
                return
        except Exception:
            pass
        # Fallback: JS click
        self._js("""
            (() => {
                const btn = document.querySelector('button[type="submit"]');
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return 'ok'; }
                const kw = ['create account', 'continue', 'register'];
                for (const b of document.querySelectorAll('button')) {
                    const t = (b.innerText || '').toLowerCase();
                    if (kw.some(k => t.includes(k))) { b.click(); return 'ok'; }
                }
                return 'not_found';
            })()
        """)

    def _create_email(self, worker_id: int) -> Tuple[Optional[str], str]:
        """Generate email based on selected provider (same as brave/chromium)."""
        email_providers = self.config.get("email_providers") or {}
        email_password = self.password

        # Fast mails pool
        fast_mails = self.config.get("fast_mails") or {}
        if fast_mails.get("enabled", False):
            try:
                from .email_pool import EmailPool
                pool = EmailPool.instance()
                account = pool.get_email(worker_id=worker_id, timeout=120)
                if account:
                    self._zeus_refresh_token = account.get('refresh_token', '')
                    self._zeus_client_id = account.get('client_id', '')
                    return account['email'], account['password']
            except Exception:
                pass

        # CyberTemp
        if email_providers.get("cybertemp", {}).get("enabled", False):
            cybertemp_key = email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", "")
            domain = email_providers.get("cybertemp", {}).get("domain", "random")
            if not domain or domain == "random":
                try:
                    from ..Helper.mail import MskMailApi
                    _api = MskMailApi(api_key=cybertemp_key)
                    _domains = _api.get_domains(domain_type="discord")
                    domain = random.choice(_domains) if _domains else Utils.get_domain()
                except Exception:
                    domain = Utils.get_domain()
            use_real = self.config.get("real_usernames", False)
            username = Utils.generate_real_username(use_api=use_real)
            email_address = f"{username}@{domain}"
            try:
                from ..Helper.mail import MskMailApi
                email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)
                Logger.STATUS = f"{MskColor.PRIMARY}CyberTemp email created: {email}"
                Logger.queue_log(worker_id=worker_id)
                return email, email_password
            except Exception:
                return email_address, email_password

        # DuckMail
        if email_providers.get("duckmail", {}).get("enabled", False):
            dm = email_providers.get("duckmail", {})
            dm_key = dm.get("api_key", "")
            domain = dm.get("domain", "").strip()
            try:
                from ..Helper.mail import DuckMailApi
                duck_api = DuckMailApi(api_key=dm_key)
                if not domain:
                    domains = duck_api.get_domains() or []
                    domain = random.choice(domains) if domains else ""
                if not domain:
                    Logger.STATUS = f"{MskColor.RED}DuckMail: no domain available"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password
                use_real = self.config.get("real_usernames", False)
                username = Utils.generate_real_username(use_api=use_real)
                email_address = f"{username}@{domain}"
                email = duck_api.create_account(email=email_address, password=email_password)
                Logger.STATUS = f"{MskColor.PRIMARY}DuckMail email created: {email}"
                Logger.queue_log(worker_id=worker_id)
                return email or email_address, email_password
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}DuckMail error: {str(e)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                return None, email_password

        # Mailcow
        if email_providers.get("mailcow", {}).get("enabled", False):
            mc = email_providers.get("mailcow", {})
            host_url = mc.get("host_url", "")
            if host_url and not host_url.startswith("http"):
                host_url = f"https://{host_url}"
            api_key = mc.get("api_key", "")
            domain = mc.get("domain", "").strip()
            if not domain:
                Logger.STATUS = f"{MskColor.RED}Mailcow domain not configured."
                Logger.queue_log(worker_id=worker_id)
                return None, email_password
            try:
                from ..Helper.mail import MailcowApi
                mailcow_api = MailcowApi(host_url=host_url, api_key=api_key)
                use_real = self.config.get("real_usernames", False)
                username = Utils.generate_real_username(use_api=use_real)
                email_address = f"{username}@{domain}"
                email = mailcow_api.create_account(email=email_address, password=email_password)
                Logger.STATUS = f"{MskColor.PRIMARY}Mailcow email created: {email}"
                Logger.queue_log(worker_id=worker_id)
                return email or email_address, email_password
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Mailcow error: {str(e)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                return None, email_password

        # Zeus
        if email_providers.get("zeus", {}).get("enabled", False):
            zeus_config = email_providers.get("zeus", {})
            from ..Helper.mail import ZeusApi
            zeus_api = ZeusApi(api_key=zeus_config.get("api_key", ""), account_type=zeus_config.get("account_type", "HOTMAIL"))
            try:
                account_data = zeus_api.create_account()
                if account_data:
                    self._zeus_refresh_token = account_data.get('refresh_token', '')
                    self._zeus_client_id = account_data.get('client_id', '')
                    return account_data['email'], account_data['password']
            except Exception:
                pass

        # Hotmail007
        if email_providers.get("hotmail007", {}).get("enabled", False):
            h007_config = email_providers.get("hotmail007", {})
            from ..Helper.mail import Hotmail007Api
            h007_api = Hotmail007Api(api_key=h007_config.get("api_key", ""), mail_type=h007_config.get("mail_type", "hotmail"))
            try:
                account_data = h007_api.create_account()
                if account_data:
                    self._zeus_refresh_token = account_data.get('refresh_token', '')
                    self._zeus_client_id = account_data.get('client_id', '')
                    return account_data['email'], account_data['password']
            except Exception:
                pass

        # Lution
        if email_providers.get("lution", {}).get("enabled", False):
            lution_config = email_providers.get("lution", {})
            from ..Helper.mail import LutionApi
            lution_api = LutionApi(api_key=lution_config.get("api_key", ""), category=lution_config.get("account_type", "hotmail"))
            try:
                account_data = lution_api.create_account()
                if account_data:
                    self._zeus_refresh_token = account_data.get('refresh_token', '')
                    self._zeus_client_id = account_data.get('client_id', '')
                    return account_data['email'], account_data['password']
            except Exception:
                pass

        # Fallback: no provider explicitly enabled — use CyberTemp if key exists, else fail
        cybertemp_key = self.config.get("cybertemp_api_key", "")
        if not cybertemp_key:
            Logger.STATUS = f"{MskColor.RED}No email provider enabled! Enable one in settings."
            Logger.queue_log(worker_id=worker_id)
            return None, email_password
        use_real = self.config.get("real_usernames", False)
        username = Utils.generate_real_username(use_api=use_real)
        domain = Utils.get_domain()
        email_address = f"{username}@{domain}"
        try:
            from ..Helper.mail import MskMailApi
            email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)
            return email or email_address, email_password
        except Exception:
            return email_address, email_password

    @staticmethod
    def _censor_token(token: str) -> str:
        if not token or not isinstance(token, str):
            return "N/A"
        if len(token) > 20:
            return token[:6] + "*" * (len(token) - 10) + token[-4:]
        return token

    def _get_hcap_iframe(self, link_pattern: str = 'hcaptcha'):
        """Get the hCaptcha challenge iframe as an IframeElement for direct JS access."""
        for pattern in (link_pattern, f'iframe[src*="{link_pattern}"]', f'iframe[title*="{link_pattern}"]'):
            try:
                iframe = self._driver.get_iframe_by_link(pattern, wait=2)
                if iframe:
                    return iframe
            except Exception:
                pass
            try:
                iframe = self._driver.select_iframe(pattern if 'iframe' in pattern else f'iframe[src*="{pattern}"]', wait=2)
                if iframe:
                    return iframe
            except Exception:
                pass
        return None

    def _js_in_iframe(self, iframe, script: str):
        """Run JS inside an IframeElement safely. Auto-prepend 'return' for IIFEs."""
        if iframe is None:
            return None
        try:
            s = script.strip()
            if s.startswith('(') and not s.startswith('(async'):
                if not s.startswith('return '):
                    s = 'return ' + s
            return iframe.run_js(s)
        except Exception:
            return None

    def _open_accessibility_in_iframe(self, challenge_iframe) -> bool:
        """Open the accessibility text challenge inside the challenge iframe.
        First changes language to Dutch, then opens accessibility menu."""
        if not challenge_iframe:
            return False

        # First check if text input is already present
        try:
            has_input = self._js_in_iframe(challenge_iframe, """
                (function() {
                    var inp = document.querySelector('input.response-input, input[id^="response"], input[name="response"], input[type="text"], input[name="captcha"]');
                    return !!inp;
                })()
            """)
            if has_input:
                return True
        except Exception:
            pass

        # Step 1: Change language to Dutch FIRST (click EN -> select Nederlands)
        try:
            lang_changed = self._js_in_iframe(challenge_iframe, """
                (function() {
                    var log = [];
                    
                    // Find the language button (usually shows "EN" at the bottom)
                    var langBtn = document.querySelector('button[aria-label*="language" i], button[class*="language"], [data-language], .language-selector button');
                    if (!langBtn) {
                        // Try to find button with text "EN" or similar
                        var buttons = document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {
                            var text = (buttons[i].textContent || buttons[i].innerText || '').trim().toUpperCase();
                            if (text === 'EN' || text === 'ENGLISH' || text.length === 2) {
                                langBtn = buttons[i];
                                break;
                            }
                        }
                    }
                    
                    if (!langBtn) {
                        log.push('Language button not found');
                        return JSON.stringify({success: false, reason: 'no_lang_button', log: log});
                    }
                    
                    log.push('Found language button');
                    langBtn.click();
                    log.push('Clicked language button');
                    
                    // Wait for language menu to appear
                    var start = Date.now();
                    while (Date.now() - start < 1000) {
                        // Busy wait
                    }
                    
                    // Find and click Dutch option (shown as "Dutch" in the menu)
                    var dutchBtn = null;
                    var links = document.querySelectorAll('a, button, [role="menuitem"], [role="option"], li, div[role="button"]');
                    for (var j = 0; j < links.length; j++) {
                        var text = (links[j].textContent || links[j].innerText || '').trim().toLowerCase();
                        var lang = (links[j].getAttribute('lang') || '').toLowerCase();
                        var value = (links[j].getAttribute('value') || '').toLowerCase();
                        
                        // Look for "Dutch" text (most reliable)
                        if (text === 'dutch' || text.includes('dutch')) {
                            dutchBtn = links[j];
                            break;
                        }
                        // Fallback to language codes
                        if (lang.includes('nl') || value.includes('nl') || text === 'nl') {
                            dutchBtn = links[j];
                            break;
                        }
                    }
                    
                    if (!dutchBtn) {
                        log.push('Dutch option not found in menu');
                        return JSON.stringify({success: false, reason: 'no_dutch_option', log: log});
                    }
                    
                    log.push('Found Dutch option');
                    dutchBtn.click();
                    log.push('Clicked Dutch option');
                    
                    return JSON.stringify({success: true, log: log});
                })()
            """)
            if lang_changed:
                import json
                res = json.loads(lang_changed)
                if res.get('success'):
                    time.sleep(1)  # Wait for language change to apply
        except Exception:
            pass

        # Step 2: Now open the accessibility menu (3-dot menu)
        for attempt in range(5):
            try:
                result = self._js_in_iframe(challenge_iframe, """
                    (function() {
                        var log = [];
                        
                        // Step 1: Find and click the menu button (3-dot icon)
                        var menuBtn = document.querySelector('button[aria-haspopup="true"]');
                        if (!menuBtn) {
                            menuBtn = document.querySelector('#menu-info button');
                        }
                        if (!menuBtn) {
                            var allBtns = document.querySelectorAll('button');
                            for (var i = 0; i < allBtns.length; i++) {
                                var btn = allBtns[i];
                                if (btn.querySelector('svg')) {
                                    menuBtn = btn;
                                    break;
                                }
                            }
                        }
                        
                        if (!menuBtn) {
                            return JSON.stringify({success: false, reason: 'no_menu_button', log: log});
                        }
                        
                        log.push('Found menu button');
                        menuBtn.click();
                        log.push('Clicked menu button');
                        
                        // Step 2: Wait a tiny bit for menu to appear
                        var start = Date.now();
                        while (Date.now() - start < 500) {
                            // Busy wait
                        }
                        
                        // Step 3: Find and click accessibility option
                        var accessBtn = document.querySelector('a[href*="accessibility"], button[aria-label*="accessibility" i]');
                        if (!accessBtn) {
                            var links = document.querySelectorAll('a, button, [role="button"], [role="menuitem"]');
                            for (var j = 0; j < links.length; j++) {
                                var link = links[j];
                                var text = (link.textContent || link.innerText || '').toLowerCase();
                                var href = (link.getAttribute('href') || '').toLowerCase();
                                if (text.includes('accessibility') || href.includes('accessibility') || 
                                    text.includes('toegankelijkheid') || text.includes('audio') || text.includes('text')) {
                                    accessBtn = link;
                                    break;
                                }
                            }
                        }
                        
                        if (!accessBtn) {
                            return JSON.stringify({success: false, reason: 'no_accessibility_option', log: log});
                        }
                        
                        log.push('Found accessibility button');
                        accessBtn.click();
                        log.push('Clicked accessibility button');
                        
                        return JSON.stringify({success: true, log: log});
                    })()
                """)
                
                if result:
                    import json
                    res = json.loads(result)
                    if res.get('success'):
                        time.sleep(1.5)  # Wait for accessibility challenge to load
                        return True
                    
            except Exception as e:
                pass
            
            time.sleep(0.5)

        return False

    def _solve_captcha_text(self, worker_id: int) -> bool:
        """Solve hCaptcha accessibility text challenge using Knowledge Base + AI."""
        Logger.STATUS = f"{MskColor.YELLOW}Solving captcha via Text/AI solver..."
        Logger.queue_log(worker_id=worker_id)
        
        # Inject Dutch language into page-level cookies
        try:
            self._js("""
                (function() {
                    document.cookie = "hcaptcha_language=nl; path=/; domain=.discord.com";
                    document.cookie = "hcaptcha_language=nl; path=/; domain=.hcaptcha.com";
                    document.cookie = "hcaptcha_language=nl; path=/; domain=.newassets.hcaptcha.com";
                })()
            """)
        except:
            pass
        
        from .text_solver_truedriver import TruedriverTextSolver
        ts = TruedriverTextSolver(self, worker_id)

        start_time = time.time()
        max_time = 90
        challenge_count = 0
        last_question = ""
        
        # Step 1: Find and switch to the hCaptcha iframe, then open accessibility
        Logger.STATUS = f"{MskColor.YELLOW}Looking for hCaptcha iframe..."
        Logger.queue_log(worker_id=worker_id)
        
        accessibility_opened = False
        challenge_iframe = None
        
        for attempt in range(5):
            self._check_stop()
            
            if self._check_passed():
                elapsed = time.time() - start_time
                Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s"
                Logger.queue_log(worker_id=worker_id)
                return True
            
            try:
                # Try to get the iframe object
                widget = self._get_hcap_iframe('hcaptcha')
                if not widget:
                    widget = self._get_hcap_iframe('checkbox')
                if not widget:
                    widget = self._get_hcap_iframe('anchor')
                
                if widget:
                    challenge_iframe = widget
                    Logger.STATUS = f"{MskColor.GREEN}Found hCaptcha iframe, opening accessibility..."
                    Logger.queue_log(worker_id=worker_id)
                    
                    # Try to open accessibility using the iframe object
                    success = self._open_accessibility_in_iframe(widget)
                    if success:
                        accessibility_opened = True
                        Logger.STATUS = f"{MskColor.GREEN}Accessibility menu opened!"
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                        break
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}Accessibility open attempt {attempt+1}/5 failed, retrying..."
                        Logger.queue_log(worker_id=worker_id)
                        
            except Exception as e:
                Logger.STATUS = f"{MskColor.YELLOW}Iframe access error: {str(e)[:50]}"
                Logger.queue_log(worker_id=worker_id)
            
            time.sleep(1)
        
        if not accessibility_opened:
            Logger.STATUS = f"{MskColor.RED}Failed to open accessibility menu after 5 attempts"
            Logger.queue_log(worker_id=worker_id)
            return False
        
        # Step 2: Wait for challenge question to load  
        Logger.STATUS = f"{MskColor.YELLOW}Waiting for challenge question to load..."
        Logger.queue_log(worker_id=worker_id)
        
        challenge_ready = False
        for wait_attempt in range(40):
            self._check_stop()
            
            if self._check_passed():
                elapsed = time.time() - start_time
                Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s"
                Logger.queue_log(worker_id=worker_id)
                return True
            
            # Try to get the challenge iframe (newassets or hcaptcha)
            current_iframe = self._get_hcap_iframe('newassets')
            if not current_iframe:
                current_iframe = self._get_hcap_iframe('hcaptcha')
            if not current_iframe:
                current_iframe = challenge_iframe
            
            if current_iframe:
                try:
                    # Check if question is actually loaded
                    status = self._js_in_iframe(current_iframe, """
                        (function() {
                            var input = document.querySelector('input[name="captcha"], input.response-input, input[type="text"]');
                            var prompt = document.querySelector('h2.prompt-text span, [id*="prompt-text"], .prompt-text, h2 span');
                            
                            if (input && prompt) {
                                var text = (prompt.innerText || prompt.textContent || '').trim();
                                if (text.length > 3) {
                                    return 'ready';
                                }
                            }
                            return 'loading';
                        })()
                    """)
                    
                    if status == 'ready':
                        challenge_iframe = current_iframe
                        Logger.STATUS = f"{MskColor.GREEN}Challenge question loaded and ready!"
                        Logger.queue_log(worker_id=worker_id)
                        challenge_ready = True
                        break
                except:
                    pass
            
            time.sleep(0.4)
        
        if not challenge_ready:
            Logger.STATUS = f"{MskColor.YELLOW}Question not fully loaded, attempting solve anyway..."
            Logger.queue_log(worker_id=worker_id)
            if not challenge_iframe:
                challenge_iframe = self._get_hcap_iframe('newassets') or self._get_hcap_iframe('hcaptcha')

        # Step 3: Solve loop
        while time.time() - start_time < max_time:
            self._check_stop()

            # Refresh iframe handle
            c_if = self._get_hcap_iframe('newassets') or challenge_iframe
            if c_if:
                challenge_iframe = c_if

            if self._check_passed():
                elapsed = time.time() - start_time
                Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({max(1, challenge_count)} challenges)"
                Logger.queue_log(worker_id=worker_id)
                return True

            if not self._has_hcaptcha():
                time.sleep(1.0)
                if self._check_passed():
                    elapsed = time.time() - start_time
                    Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({max(1, challenge_count)} challenges)"
                    Logger.queue_log(worker_id=worker_id)
                    return True
                time.sleep(0.5)
                continue

            # Check if input is present; if not, open accessibility
            has_input = self._js_in_iframe(challenge_iframe, """
                (function() {
                    var inp = document.querySelector('input.response-input, input[id^="response"], input[name="response"], input[type="text"]');
                    return !!inp;
                })()
            """)
            if not has_input:
                self._open_accessibility_in_iframe(challenge_iframe)
                time.sleep(0.8)
                continue

            # Read question
            raw_q = self._js_in_iframe(challenge_iframe, """
                (function() {
                    var el = document.querySelector('h2.prompt-text, [id^="prompt-text"], .prompt-text, .challenge-prompt');
                    if (el && el.innerText && el.innerText.trim().length > 3) return el.innerText.trim();
                    return document.body ? document.body.innerText : '';
                })()
            """)
            if not raw_q or len(str(raw_q).strip()) < 3:
                time.sleep(0.3)
                continue

            clean_q = TruedriverTextSolver._extract_question_from_text(str(raw_q))
            if not clean_q or len(clean_q) < 3:
                clean_q = str(raw_q).strip().lower()

            if clean_q == last_question:
                time.sleep(0.4)
                continue

            challenge_count += 1
            last_question = clean_q

            # Resolve answer: 1) KB, 2) Local Solver, 3) AI Provider
            answer = ts._kb_lookup(clean_q)
            if not answer:
                answer = ts._local_solve(clean_q)
            if not answer:
                answer = ts._fetch_answer(clean_q)
            if not answer:
                answer = "yes"

            # Fill answer into challenge iframe input
            ans_clean = str(answer).strip().replace("\\", "\\\\").replace("'", "\\'")
            self._js_in_iframe(challenge_iframe, f"""
                (function() {{
                    var inp = document.querySelector('input.response-input, input[id^="response"], input[name="response"], input[type="text"]');
                    if (!inp) return;
                    try {{
                        var proto = inp.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                        var setter = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (setter && setter.set) setter.set.call(inp, '{ans_clean}');
                        else inp.value = '{ans_clean}';
                    }} catch(_) {{ inp.value = '{ans_clean}'; }}
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                }})()
            """)

            time.sleep(0.3)

            # Click submit button
            self._js_in_iframe(challenge_iframe, """
                (function() {
                    var btn = document.querySelector('button[type="submit"], button.button-submit, [class*="submit"], button');
                    if (btn) btn.click();
                })()
            """)

            time.sleep(1.2)

        if self._check_passed() or not self._has_hcaptcha():
            elapsed = time.time() - start_time
            Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({max(1, challenge_count)} challenges)"
            Logger.queue_log(worker_id=worker_id)
            return True

        return False

    def print_stats(self, worker_id, token, elapsed_time, startup_time, hcap_wait, hcap_solve,
                    humanize_time, email_verify_time, phone_verify_time, phone_verified, humanize_status, ev_status):
        logs_cfg = self.config.get("logs") or {}
        display_token = token
        if logs_cfg.get("censor_token", False):
            display_token = self._censor_token(token)
        phone_status = f"{MskColor.GREEN}Phone Verified" if phone_verified else f"{MskColor.RED}Not Phone Verified"
        _show_data_usage = (self.config.get("proxies") or {}).get("enabled", False) or bool(self.config.get("data_saver", False))
        stats = [
            ("Token", display_token, True),
            ("Generation Time", f"{elapsed_time:.2f}s", logs_cfg.get("generation_time", True)),
            ("Browser Startup Time", f"{startup_time:.2f}s", logs_cfg.get("startup_time", False)),
            ("hCaptcha Waiting Time", f"{hcap_wait:.2f}s", logs_cfg.get("hcaptcha_waiting", False)),
            ("hCaptcha Solving Time", f"{hcap_solve:.2f}s", logs_cfg.get("hcaptcha_solving", True)),
            ("Humanize Time", f"{humanize_time:.2f}s", logs_cfg.get("humanize_time", True)),
            ("Email Verify Time", f"{email_verify_time:.2f}s", logs_cfg.get("verify_time", True)),
            ("Phone Verify Time", f"{phone_verify_time:.2f}s", logs_cfg.get("phone_verify_time", True)),
            ("Data Usage", f"{getattr(self, '_network_bytes', 0) / (1024 * 1024):.2f} MB", _show_data_usage),
            ("Total Time", f"{email_verify_time + humanize_time + elapsed_time + startup_time + phone_verify_time:.2f}s", logs_cfg.get("total_time", True)),
            ("Status", f"{humanize_status}, {ev_status}, {phone_status}", True)
        ]
        Logger.queue_stats(worker_id, stats)





    def register(self, worker_id: int, on_browser_closed=None) -> str:
        self.worker_id = worker_id
        try:
            
            # Check text solver compatibility EARLY - before browser starts
            solver_ai_cfg = self.config.get('solver_ai') or {}
            auto_solver_enabled = self.config.get('auto_solver_captcha', True)
            text_solver_requested = auto_solver_enabled and (
                solver_ai_cfg.get('ollama', False) or
                solver_ai_cfg.get('groq', False) or
                solver_ai_cfg.get('openrouter', False)
            )
            
            if text_solver_requested:
                Logger.STATUS = f"{MskColor.RED}WARNING: Chromium2 browser does not support auto text/AI solver!"
                Logger.queue_log(worker_id=worker_id)
                # Force disable for this session
                self.config['auto_solver_captcha'] = False
            
            start_time_startup = time.time()
            headless_mode = self.config.get("headless", False)

            Logger.STATUS = f"{MskColor.PRIMARY}Starting Chromium 2 Browser"
            Logger.queue_log(worker_id=worker_id)

            proxy_data = None
            if (self.config.get("proxies") or {}).get("enabled", False):
                proxy_data = self.proxy_manager.get_proxy(worker_id=worker_id)
                if not proxy_data:
                    proxy_data = self.proxy_manager.wait_for_proxies(worker_id)
                if proxy_data:
                    if (self.config.get("proxies") or {}).get("remove_after_use", False):
                        self.proxy_manager.remove_proxy(proxy_data)
                    server = proxy_data.get("server", "")
                    host_port = server.split("://")[-1]
                    username = proxy_data.get("username", "")
                    pwd = proxy_data.get("password", "")
                    full_proxy = f"{username}:{pwd}@{host_port}" if username and pwd else host_port
                    Logger.STATUS = f"{MskColor.PRIMARY}Using Proxy: {full_proxy}"
                    Logger.queue_log(worker_id=worker_id)

            self._check_stop()

            try:
                driver = self._create_browser(headless=headless_mode, proxy=proxy_data)
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Browser start failed: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

            elapsed_startup = time.time() - start_time_startup
            self._check_stop()

            # Wait for form to load -- Discord SPA needs time to hydrate
            self._sleep(4)
            start_wait = time.time()
            found_form = False
            while time.time() - start_wait < 60:
                self._check_stop()
                # Use botasaurus built-in element check first
                try:
                    present = self._driver.is_element_present('input[name="email"]', wait=2)
                    if present:
                        found_form = True
                        break
                except Exception:
                    pass
                self._sleep(1)

            if not found_form:
                raw_text = self._js("(function(){ return document.body.innerText; })()")
                page_text = str(raw_text).lower() if raw_text else ""
                if any(kw in page_text for kw in ["403", "access denied", "cloudflare"]):
                    Logger.STATUS = f"{MskColor.RED}Discord blocked this IP."
                    Logger.queue_log(worker_id=worker_id)
                    return "RateLimited"
                Logger.STATUS = f"{MskColor.RED}Registration form not found"
                Logger.queue_log(worker_id=worker_id)
                return "RateLimited"

            self._check_stop()
            start_time = time.time()
            Logger.STATUS = f"{MskColor.SECONDARY}Filling Form"
            Logger.queue_log(worker_id=worker_id)

            email_address, email_password = self._create_email(worker_id)
            if not email_address:
                return "Invalid"

            discord_username = Utils.sanitize_username(Utils.random_string())
            self._fill_form(email_address, discord_username, worker_id)

            # Wait enough for the async IIFE inside _fill_form to complete all
            # dropdown selections (year scroll can take 150 × 30 ms = ~4.5 s).
            # Previously 1.2 s was far too short on slow machines.
            self._sleep(5.0)
            self._check_stop()
            self._submit_form(worker_id=worker_id)

            # Wait for captcha or success
            _wait_hcap_start = time.time()
            hcaptcha_appeared = False
            for _ in range(30):
                self._check_stop()
                if self._has_hcaptcha():
                    hcaptcha_appeared = True
                    break
                if self._check_passed():
                    break
                url = self._js("(function(){ return window.location.href; })()") or ""
                if 'check-your-email' in url or '/verify' in url or '/channels' in url:
                    break
                self._sleep(0.5)

            # Wait for captcha to fully load (skip loading screen)
            if hcaptcha_appeared:
                # Block unwanted navigation while captcha is active
                try:
                    self._js("""
                        (function() {
                            // Set Dutch language for hCaptcha
                            document.cookie = "hcaptcha_language=nl; path=/; domain=.discord.com";
                            document.cookie = "hcaptcha_language=nl; path=/; domain=.hcaptcha.com";
                            document.cookie = "hcaptcha_language=nl; path=/; domain=.newassets.hcaptcha.com";
                            
                            // Block navigation to /login while captcha is active
                            var currentUrl = window.location.href;
                            var navigationBlocked = false;
                            
                            // Override history methods to prevent redirect
                            var originalPushState = history.pushState;
                            var originalReplaceState = history.replaceState;
                            
                            history.pushState = function() {
                                var url = arguments[2];
                                if (url && url.includes('/login')) {
                                    console.log('Blocked navigation to /login');
                                    navigationBlocked = true;
                                    return;
                                }
                                return originalPushState.apply(history, arguments);
                            };
                            
                            history.replaceState = function() {
                                var url = arguments[2];
                                if (url && url.includes('/login')) {
                                    console.log('Blocked navigation to /login');
                                    navigationBlocked = true;
                                    return;
                                }
                                return originalReplaceState.apply(history, arguments);
                            };
                            
                            // Monitor for navigation attempts
                            window._mskCaptchaActive = true;
                        })()
                    """)
                except:
                    pass
                
                loading_done = False
                for _ in range(12):  # Wait up to 6 seconds
                    try:
                        # Check if hCaptcha iframe is actually ready by checking for menu or checkbox
                        check = self._js("""
                            (function() {
                                var iframes = document.querySelectorAll('iframe[src*="hcaptcha.com"]');
                                for (var i = 0; i < iframes.length; i++) {
                                    try {
                                        var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                                        if (doc) {
                                            // Check if hCaptcha elements are present
                                            if (doc.querySelector('#checkbox, #menu-info, .check, #anchor')) {
                                                return 'ready';
                                            }
                                        }
                                    } catch(e) {
                                        // Cross-origin iframe, assume ready
                                        return 'ready';
                                    }
                                }
                                return 'loading';
                            })()
                        """)
                        if check == 'ready':
                            loading_done = True
                            break
                    except:
                        # If we can't check, assume ready after a few attempts
                        pass
                    self._sleep(0.5)
                
                # Don't skip if we can't confirm - captcha is likely ready
                if not loading_done:
                    Logger.STATUS = f"{MskColor.YELLOW}Captcha load check inconclusive, proceeding anyway..."
                    Logger.queue_log(worker_id=worker_id)
                    loading_done = True  # Proceed anyway instead of skipping

            hcap_wait_time = time.time() - _wait_hcap_start if hcaptcha_appeared else 0.0
            hcap_solve_time = 0.0

            self._check_stop()
            if hcaptcha_appeared:
                Logger.STATUS = f"{MskColor.PRIMARY}Captcha Found"
                Logger.queue_log(worker_id=worker_id)

                _solve_hcap_start = time.time()

                # do not waste ~9 seconds on 3 stub calls that always return False.

                # IMPORTANT: Chromium2 (Botasaurus driver) CANNOT auto-solve hCaptcha accessibility challenges
                # due to cross-origin iframe restrictions. The driver cannot execute JavaScript inside
                # hCaptcha iframes, making text/AI solver incompatible with this browser.
                # Text solver is DISABLED for Chromium2. Use Brave, Chromium, Clearcote, or Camoufox instead.
                solver_ai_cfg = self.config.get('solver_ai') or {}
                auto_solver_enabled = self.config.get('auto_solver_captcha', True)
                text_solver_requested = auto_solver_enabled and (
                    solver_ai_cfg.get('ollama', False) or
                    solver_ai_cfg.get('groq', False) or
                    solver_ai_cfg.get('openrouter', False)
                )
                
                # Show warning if user has text solver enabled
                if text_solver_requested:
                    Logger.STATUS = f"{MskColor.RED}WARNING: Chromium2 browser does not support auto text/AI solver!"
                    Logger.queue_log(worker_id=worker_id)
                    Logger.STATUS = f"{MskColor.YELLOW}Chromium2 uses Botasaurus driver which cannot interact with cross-origin hCaptcha iframes."
                    Logger.queue_log(worker_id=worker_id)
                    Logger.STATUS = f"{MskColor.YELLOW}Please use Brave, Chromium, Clearcote, or Camoufox for auto-solving, or solve manually."
                    Logger.queue_log(worker_id=worker_id)
                    Logger.STATUS = f"{MskColor.YELLOW}Text solver is DISABLED for this session. Waiting for manual solve..."
                    Logger.queue_log(worker_id=worker_id)
                
                # Force disable text solver for Chromium2
                text_solver_enabled = False

                # Wait for manual solve since Chromium2 cannot auto-solve
                solved = False
                for _attempt in range(3):
                    self._check_stop()
                    if not self._has_hcaptcha():
                        self._sleep(2)
                        if self._check_passed():
                            solved = True
                            break
                    # Check if captcha is solved
                    for _ in range(30):
                        self._check_stop()
                        self._sleep(0.5)
                        if self._check_passed():
                            solved = True
                            break
                        if not self._has_hcaptcha():
                            self._sleep(2)
                            if self._check_passed():
                                solved = True
                            break
                    if solved:
                        break
                    Logger.queue_log(worker_id=worker_id)
                    self._sleep(3)
                if not solved:
                    Logger.queue_log(worker_id=worker_id)
                    return "EndlessCaptcha"

            hcap_solve_time = time.time() - _solve_hcap_start

            _post_captcha_url = self._js("(function(){ return window.location.href; })()") or ""
            if 'check-your-email' in _post_captcha_url:
                try:
                    self._driver.get("https://discord.com/app")
                except Exception:
                    pass
                self._sleep(3)
            else:
                self._sleep(2)

            elapsed_time = time.time() - start_time

            # Extract token
            token = None
            if getattr(self, "_extracted_token", None):
                token = self._extracted_token

            if not token:
                for _ in range(10):
                    token = self._extract_token()
                    if token:
                        break
                    self._sleep(0.5)

            if not token:
                try:
                    self._driver.get("https://discord.com/app")
                except Exception:
                    pass
                self._sleep(3)
                for _ in range(10):
                    token = self._extract_token()
                    if token:
                        break
                    self._sleep(1)

            # Email verification
            token_verify_enabled = self.config.get("token_verify", True)
            start_time_verify = time.time()
            ev_status = False

            if token_verify_enabled and (token or hcaptcha_appeared):
                email_providers = self.config.get("email_providers") or {}
                from ..Helper.mail import suppress_output

                mail_api = None
                verify_kwargs = {"email": email_address, "timeout": 120, "poll_interval": 3}

                if email_providers.get("cybertemp", {}).get("enabled", False):
                    from ..Helper.mail import MskMailApi
                    cybertemp_key = email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", "")
                    mail_api = MskMailApi(api_key=cybertemp_key)
                elif email_providers.get("duckmail", {}).get("enabled", False):
                    from ..Helper.mail import DuckMailApi
                    duckmail_key = email_providers.get("duckmail", {}).get("api_key", "")
                    mail_api = DuckMailApi(api_key=duckmail_key)
                    verify_kwargs["password"] = email_password
                elif email_providers.get("mailcow", {}).get("enabled", False):
                    from ..Helper.mail import MailcowApi
                    mc = email_providers.get("mailcow", {})
                    mail_api = MailcowApi(host_url=mc.get("host_url", ""), api_key=mc.get("api_key", ""))
                    verify_kwargs["password"] = email_password
                elif email_providers.get("zeus", {}).get("enabled", False):
                    from ..Helper.mail import ZeusApi
                    z = email_providers.get("zeus", {})
                    mail_api = ZeusApi(api_key=z.get("api_key", ""), account_type=z.get("account_type", "HOTMAIL"))
                    verify_kwargs["password"] = email_password
                    verify_kwargs["refresh_token"] = self._zeus_refresh_token
                    verify_kwargs["client_id"] = self._zeus_client_id
                elif email_providers.get("hotmail007", {}).get("enabled", False):
                    from ..Helper.mail import Hotmail007Api
                    h = email_providers.get("hotmail007", {})
                    mail_api = Hotmail007Api(api_key=h.get("api_key", ""), mail_type=h.get("mail_type", "hotmail"))
                    verify_kwargs["password"] = email_password
                    verify_kwargs["refresh_token"] = self._zeus_refresh_token
                    verify_kwargs["client_id"] = self._zeus_client_id
                elif email_providers.get("lution", {}).get("enabled", False):
                    from ..Helper.mail import LutionApi
                    l_cfg = email_providers.get("lution", {})
                    mail_api = LutionApi(api_key=l_cfg.get("api_key", ""), category=l_cfg.get("account_type", "hotmail"))
                    verify_kwargs["password"] = email_password
                    verify_kwargs["refresh_token"] = self._zeus_refresh_token
                    verify_kwargs["client_id"] = self._zeus_client_id
                else:
                    cybertemp_key = self.config.get("cybertemp_api_key", "")
                    if cybertemp_key:
                        from ..Helper.mail import MskMailApi
                        mail_api = MskMailApi(api_key=cybertemp_key)

                if not mail_api:
                    Logger.STATUS = f"{MskColor.YELLOW}No mail API for verification, skipping..."
                    Logger.queue_log(worker_id=worker_id)
                else:
                    Logger.STATUS = f"{MskColor.PRIMARY}Verifying Email..."
                    Logger.queue_log(worker_id=worker_id)

                    try:
                        with suppress_output():
                            if hasattr(mail_api, 'get_verification_link'):
                                verification_url = mail_api.get_verification_link(**verify_kwargs)
                            elif hasattr(mail_api, 'get_verification_url'):
                                verification_url = mail_api.get_verification_url(**verify_kwargs)
                            else:
                                verification_url = None
                        if verification_url:
                            resolved_url = verification_url
                            try:
                                import requests as _req
                                is_tracking = any(d in verification_url for d in ['click.discord.com', 'links.discord.com'])
                                if is_tracking:
                                    resp = _req.get(verification_url, allow_redirects=False, timeout=10, headers={
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                    })
                                    loc = resp.headers.get('Location', '')
                                    if loc and ('discord.com' in loc):
                                        resolved_url = loc
                                        if '/verify' not in loc and 'token=' not in loc:
                                            resp2 = _req.get(loc, allow_redirects=False, timeout=10, headers={
                                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                            })
                                            loc2 = resp2.headers.get('Location', '')
                                            if loc2:
                                                resolved_url = loc2
                            except Exception:
                                pass

                            try:
                                self._driver.get(resolved_url)
                                self._sleep(3)
                                # Click verify / confirm button
                                self._js("""
                                    (() => {
                                        const kw = ['verify email', 'verify', 'confirm email', 'confirm',
                                                    'continue to discord', 'continue', 'open discord', 'launch app'];
                                        const els = document.querySelectorAll('button, a, div[role="button"]');
                                        for (const el of els) {
                                            const text = (el.innerText || '').toLowerCase();
                                            for (const k of kw) {
                                                if (text.includes(k)) { el.click(); return 'clicked'; }
                                            }
                                        }
                                        const sb = document.querySelector('button[type="submit"]');
                                        if (sb) { sb.click(); return 'submit'; }
                                        return 'none';
                                    })()
                                """)
                                self._sleep(2)

                                # --- Poll for verification success (and solve email hCaptcha) ---
                                _ok_kws = ['done', 'verified', 'email verified', "you're all set",
                                           'success', 'verification successful']
                                def _page_verified_ch2():
                                    try:
                                        txt = self._js('document.body.innerText') or ''
                                        if any(k in str(txt).lower() for k in _ok_kws):
                                            return True
                                    except Exception:
                                        pass
                                    try:
                                        url = str(self._js('window.location.href') or '').lower()
                                        if '/channels' in url or '/@me' in url:
                                            return True
                                    except Exception:
                                        pass
                                    return False

                                _auto_solve = self.config.get('auto_solver_captcha', False)
                                _solver_ai  = self.config.get('solver_ai') or {}
                                _any_solver = _auto_solve and (
                                    any(_solver_ai.get(p, False) for p in ('groq', 'openrouter'))
                                )
                                _ev_cap_tries = 0
                                _ev_deadline  = time.time() + 90

                                while time.time() < _ev_deadline:
                                    if _page_verified_ch2():
                                        ev_status = True
                                        break
                                    if self._has_hcaptcha():
                                        if _any_solver and _ev_cap_tries < 3:
                                            _ev_cap_tries += 1
                                            Logger.STATUS = f"{MskColor.YELLOW}Email verify captcha, solving..."
                                            Logger.queue_log(worker_id=worker_id)
                                            _sv = self._solve_captcha_text(worker_id)
                                            if not _sv:
                                                break
                                            self._sleep(2)
                                            continue
                                        else:
                                            # No solver -- wait up to 45s for manual/extension solve
                                            _wait_end = min(time.time() + 45, _ev_deadline)
                                            while time.time() < _wait_end:
                                                if not self._has_hcaptcha():
                                                    break
                                                self._sleep(0.5)
                                    self._sleep(0.4)

                                if ev_status:
                                    Logger.STATUS = f"{MskColor.GREEN}Email verified!"
                                    Logger.queue_log(worker_id=worker_id)
                                else:
                                    Logger.STATUS = f"{MskColor.YELLOW}Email verification timed out"
                                    Logger.queue_log(worker_id=worker_id)
                            except Exception:
                                pass
                        else:
                            Logger.STATUS = f"{MskColor.YELLOW}No verification link found"
                            Logger.queue_log(worker_id=worker_id)
                    except Exception as e:
                        Logger.STATUS = f"{MskColor.YELLOW}Email verify failed: {str(e)[:60]}"
                        Logger.queue_log(worker_id=worker_id)

            email_verify_time = time.time() - start_time_verify if token_verify_enabled else 0.0

            if not token:
                try:
                    self._driver.get("https://discord.com/app")
                except Exception:
                    pass
                self._sleep(3)
                for _ in range(15):
                    token = self._extract_token()
                    if token:
                        break
                    self._sleep(1)

            # Humanize
            humanize_time = 0.0
            humanize_cfg = self.config.get("humanizer") or {}
            humanize_status = f"{MskColor.YELLOW}Skipped"
            h_result = False
            if token and humanize_cfg.get("enabled", False):
                start_hum = time.time()
                try:
                    Logger.STATUS = f"{MskColor.LIGHTBLUE}Humanizing account..."
                    Logger.queue_log(worker_id=worker_id)
                    from ..Helper.huminazer import DiscordHuminazer
                    humanizer = DiscordHuminazer(worker_id=worker_id)
                    h_result = humanizer.humanize_account(token, proxy_data)
                    humanize_status = f"{MskColor.GREEN}Humanized" if h_result else f"{MskColor.RED}Failed"
                except Exception as e:
                    humanize_status = f"{MskColor.RED}Error"
                    Logger.STATUS = f"{MskColor.RED}Humanize failed: {str(e)[:60]}"
                    Logger.queue_log(worker_id=worker_id)
                humanize_time = time.time() - start_hum

            ev_status_str = f"{MskColor.GREEN}Email Verified" if ev_status else f"{MskColor.RED}Unclaimed"
            if ev_status:
                Logger.STATUS = f"{MskColor.GREEN}Account Created & Verified!"
            else:
                Logger.STATUS = f"{MskColor.PRIMARY}Account Created (Unverified)!"
            Logger.queue_log(worker_id=worker_id)

            if token:
                output_dir = os.path.join("data", "output")
                os.makedirs(output_dir, exist_ok=True)
                token_file = os.path.join(output_dir, "tokens.txt")
                with open(token_file, "a", encoding="utf-8") as f:
                    f.write(f"{email_address}:{email_password}:{token}\r\n")

                # Token status check
                try:
                    from .token_checker import check_token_safe
                    _tc = check_token_safe(token, proxy=proxy_data if (self.config.get("proxies") or {}).get("enabled", False) else None)
                    if not _tc.get("valid"):
                        Logger.STATUS = f"{MskColor.RED}Token Invalid"
                    elif _tc.get("locked") or _tc.get("email_required") or _tc.get("phone_required"):
                        Logger.STATUS = f"{MskColor.ORANGE}Token Locked"
                    else:
                        Logger.STATUS = f"{MskColor.GREEN}Token Valid"
                    Logger.queue_log(worker_id=worker_id)
                except Exception:
                    pass

                Logger.STATUS = f"{MskColor.GREEN}Token Generated!"
                Logger.queue_log(worker_id=worker_id)

                try:
                    import sys
                    if sys.stdout:
                        sys.stdout.write("\r\n")
                except Exception:
                    pass

                startup_time = time.time() - start_time_startup

                self.print_stats(
                    worker_id, token, elapsed_time, startup_time,
                    hcap_wait_time, hcap_solve_time, humanize_time,
                    email_verify_time, 0.0, False,
                    humanize_status, ev_status_str
                )

                self.last_result = {
                    "token": str(token) if token else "",
                    "email": str(email_address) if email_address else "",
                    "status": "Valid",
                    "humanized": bool(h_result),
                    "phone_verified": False,
                    "email_verified": bool(ev_status),
                    "gen_time": round(float(elapsed_time or 0.0), 1),
                    "hcap_time": round(float(hcap_solve_time or 0.0), 1),
                    "email_time": round(float(email_verify_time or 0.0), 1),
                    "phone_time": 0.0,
                    "humanize_time": round(float(humanize_time or 0.0), 1),
                }

                return "Valid"
            else:
                Logger.STATUS = f"{MskColor.RED}Token not found"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

        except GeneratorStoppedError:
            return "ignore"
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Chromium 2 error: {str(e)[:80]}"
            Logger.queue_log(worker_id=worker_id)
            return "Invalid"
        finally:
            self._cleanup()
            if on_browser_closed:
                try:
                    on_browser_closed(worker_id)
                except Exception:
                    pass
