"""
Discord registration using Clearcote Browser (engine-level fingerprint spoofing).

Clearcote is an open-source stealth Chromium fork that rewrites fingerprint
controls at the C++ level -- no JS injection, no detectable patches.
It returns a standard Playwright browser/context handle, giving full access
to Playwright's auto-waiting, network interception, and CDP primitives.

Advantages over Brave + zendriver / botasaurus:
  - No navigator.webdriver leak (patched at engine level)
  - No HeadlessChrome UA string (patched at engine level)
  - No CDP automation artifacts (Runtime.enable hooks suppressed)
  - Authentic canvas/WebGL fingerprints via engine-level spoofing
  - Full Playwright API -- no freezing, no bridging hacks
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


COUNTRY_CODES = {
    "1": "United States", "44": "United Kingdom", "31": "Netherlands",
    "33": "France", "49": "Germany", "34": "Spain", "39": "Italy",
    "351": "Portugal", "46": "Sweden", "47": "Norway", "45": "Denmark",
    "358": "Finland", "48": "Poland", "420": "Czech Republic",
    "43": "Austria", "41": "Switzerland", "32": "Belgium",
    "353": "Ireland", "30": "Greece", "36": "Hungary", "40": "Romania",
    "359": "Bulgaria", "380": "Ukraine", "7": "Russia",
    "55": "Brazil", "52": "Mexico", "54": "Argentina", "57": "Colombia",
    "56": "Chile", "51": "Peru", "58": "Venezuela",
    "91": "India", "62": "Indonesia", "63": "Philippines",
    "66": "Thailand", "84": "Vietnam", "60": "Malaysia",
    "65": "Singapore", "81": "Japan", "82": "South Korea",
    "86": "China", "852": "Hong Kong", "886": "Taiwan",
    "90": "Turkey", "966": "Saudi Arabia", "971": "United Arab Emirates",
    "972": "Israel", "20": "Egypt", "27": "South Africa",
    "234": "Nigeria", "254": "Kenya", "61": "Australia", "64": "New Zealand",
}


class GeneratorStoppedError(Exception):
    """Raised when the user stops generation mid-flow."""
    pass


class DiscordRegisterClearcote:
    """Discord account registration using Clearcote Browser (Playwright-backed)."""

    def __init__(self):
        self.proxy_manager = ProxyManager("data/input/proxies.txt")
        self.password = Utils.random_password()
        self._page = None          # Playwright Page
        self._browser_ctx = None   # Playwright BrowserContext (persistent ephemeral)
        self._pw_instance = None   # sync_playwright() context manager
        self._extracted_token: Optional[str] = None
        self._profile_tmp_dir: Optional[str] = None
        self._zeus_refresh_token = ""
        self._zeus_client_id = ""

    # ── Stop / sleep helpers ───────────────────────────────────────────────────

    def _check_stop(self):
        if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):
            raise GeneratorStoppedError("Stopped by user")
        if hasattr(self, '_trigger_parent') and getattr(self._trigger_parent, 'should_stop', False):
            raise GeneratorStoppedError("Stopped by user")

    def _sleep(self, seconds: float):
        remaining = seconds
        while remaining > 0:
            self._check_stop()
            chunk = min(remaining, 0.5)
            time.sleep(chunk)
            remaining -= chunk

    @property
    def config(self) -> Dict:
        return Config.config

    # ── JS helpers ─────────────────────────────────────────────────────────────

    def _js(self, script: str, timeout: int = 30_000) -> Optional[object]:
        """Execute JavaScript on the current page, suppressing noise errors."""
        if self._page is None:
            return None
        try:
            self._check_stop()
        except Exception:
            return None
        try:
            return self._page.evaluate(script)
        except Exception as e:
            err = str(e)[:120]
            noise = ['timeout', 'close', 'target', 'session', 'websocket',
                     'nonetype', 'has no attribute', 'connection', 'execution context',
                     'target closed', 'navigating']
            if not any(m in err.lower() for m in noise):
                try:
                    Logger.STATUS = f"{MskColor.GREY}JS: {err}"
                    Logger.queue_log(worker_id=0)
                except Exception:
                    pass
            return None

    def _run(self, coro, timeout: int = 15):
        """Run an awaitable - for compatibility with TruedriverTextSolver.
        Clearcote uses sync Playwright, so we run async code in a new event loop."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            finally:
                loop.close()
        except Exception:
            return None

    def _fill_field_js(self, selector_list: list, value: str) -> bool:
        """Fill an input via React-safe JS setter (works even when window is not focused)."""
        import json as _json
        safe_val = value.replace('\\', '\\\\').replace("'", "\\'")
        sels_json = _json.dumps(selector_list)
        result = self._js(f"""
            (() => {{
                const sels = {sels_json};
                let el = null;
                for (const sel of sels) {{
                    const found = document.querySelector(sel);
                    if (found && (found.offsetParent !== null || found.offsetWidth > 0)) {{ el = found; break; }}
                }}
                if (!el) {{
                    const inps = document.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"])');
                    for (const inp of inps) {{
                        const name = (inp.getAttribute('name') || '').toLowerCase();
                        const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
                        for (const sel of sels) {{
                            if (sel.includes(name) || (ph && sel.includes(ph))) {{ el = inp; break; }}
                        }}
                        if (el) break;
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
                if (tracker) tracker.setValue('');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return el.value === '{safe_val}' ? 'OK' : 'VALUE_MISMATCH';
            }})()
        """)
        return result == 'OK'

    def _fill_field(self, selector_list: list, value: str) -> bool:
        """Fill field using React-safe JS with Playwright native locator fallback."""
        ok = self._fill_field_js(selector_list, value)
        if not ok and self._page:
            for sel in selector_list:
                try:
                    loc = self._page.locator(sel).first
                    if loc.is_visible(timeout=500):
                        loc.fill(value)
                        return True
                except Exception:
                    pass
        return ok

    # ── Browser state checks ───────────────────────────────────────────────────

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

    # ── Token extraction ───────────────────────────────────────────────────────

    def _extract_token(self) -> Optional[str]:
        # 1. From network interception (most reliable)
        if getattr(self, '_extracted_token', None):
            token = self._clean_token(self._extracted_token)
            if token:
                return token

        # 2. From JS / window / localStorage / webpack
        raw = self._js("""
            (() => {
                try { if (window.__discord_token) return window.__discord_token; } catch(e) {}
                try {
                    if (window.webpackChunkdiscord_app) {
                        let token = null;
                        window.webpackChunkdiscord_app.push([[Symbol()], {}, (req) => {
                            for (const m of Object.values(req.c)) {
                                try {
                                    const exp = m?.exports;
                                    if (exp?.default?.getToken) { const t = exp.default.getToken(); if (t) { token = t; break; } }
                                    if (exp?.getToken) { const t = exp.getToken(); if (t) { token = t; break; } }
                                } catch(_) {}
                            }
                        }]);
                        if (token) return token;
                    }
                } catch(e) {}
                try { const t = window.localStorage.getItem('token'); if (t) return t; } catch(e) {}
                try {
                    for (let i = 0; i < window.localStorage.length; i++) {
                        const k = window.localStorage.key(i);
                        let v = (window.localStorage.getItem(k) || '').replace(/"/g,'').trim();
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

    # ── Browser creation ───────────────────────────────────────────────────────

    def _build_proxy_dict(self, proxy: Optional[Dict]) -> Optional[Dict]:
        """Convert MSK proxy dict to Playwright proxy dict."""
        if not proxy or not proxy.get("server"):
            return None
        server = proxy["server"]
        if "://" not in server:
            server = f"http://{server}"
        pw_proxy = {"server": server}
        username = proxy.get("username", "")
        password = proxy.get("password", "")
        if username:
            pw_proxy["username"] = username
        if password:
            pw_proxy["password"] = password
        return pw_proxy

    def _create_browser(self, headless: bool = False, proxy: Optional[Dict] = None, wm_pos: Optional[tuple] = None):
        """Launch Clearcote browser and navigate to Discord register."""
        import clearcote

        # Geo locale/timezone for the proxy exit IP
        _geo_locale = "en-US"
        _geo_tz = "America/New_York"
        if proxy and proxy.get("server"):
            try:
                from ..Utils.geo_lookup import lookup_proxy_geo
                _geo_tz, _geo_locale = lookup_proxy_geo(proxy)
            except Exception:
                pass

        _lang_short = _geo_locale.split("-")[0] if "-" in _geo_locale else _geo_locale
        _accept_lang = (
            f"{_geo_locale},{_lang_short};q=0.9,en;q=0.8"
            if _geo_locale != "en-US"
            else "en-US,en;q=0.9"
        )

        # Build Playwright proxy spec
        pw_proxy = self._build_proxy_dict(proxy)

        # Extra Playwright launch args
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
        elif wm_pos and len(wm_pos) >= 4:
            extra_args.append(f"--window-size={wm_pos[2]},{wm_pos[3]}")
            extra_args.append(f"--window-position={wm_pos[0]},{wm_pos[1]}")

        # Build clearcote launch kwargs
        launch_kwargs = {
            "headless": headless,
            "args": extra_args,
            "accept_downloads": False,
        }
        if headless:
            launch_kwargs["disable_gpu_fingerprint"] = True
        if pw_proxy:
            launch_kwargs["proxy"] = pw_proxy

        # Viewport
        if wm_pos and len(wm_pos) >= 4:
            launch_kwargs["viewport"] = {"width": wm_pos[2], "height": wm_pos[3]}
        else:
            launch_kwargs["viewport"] = {"width": 1280, "height": 800}

        # Locale / timezone
        # clearcote uses "timezone" (its own FINGERPRINT_KEY), not Playwright's "timezone_id"
        # "locale" and "accept_language" pass correctly to clearcote/Playwright
        launch_kwargs["locale"] = _geo_locale
        launch_kwargs["timezone"] = _geo_tz
        launch_kwargs["accept_language"] = _accept_lang

        # Launch — clearcote.launch() returns a Playwright BrowserContext
        ctx = clearcote.launch(**launch_kwargs)
        self._browser_ctx = ctx

        # Token capture via route interception (authorization header)
        def _handle_route(route, request):
            try:
                auth_header = request.headers.get("authorization", "")
                if auth_header and len(auth_header) > 50 and '.' in auth_header:
                    token_raw = auth_header.strip().strip('"').strip("'")
                    if '{' not in token_raw and '<' not in token_raw:
                        self._extracted_token = token_raw
            except Exception:
                pass
            try:
                route.continue_()
            except Exception:
                pass

        try:
            ctx.route("**/*", _handle_route)
        except Exception:
            pass

        # Inject token sniffer + stealth JS on every new page
        _TOKEN_HOOK_JS = r"""
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
                    const h = opts.headers;
                    if (h instanceof Headers) {
                        saveToken(h.get('Authorization') || h.get('authorization'));
                    } else if (typeof h === 'object') {
                        for (const k in h) {
                            if (k.toLowerCase() === 'authorization') saveToken(h[k]);
                        }
                    }
                }
            } catch(e) {}
            return origFetch.apply(this, args).then(res => {
                try {
                    res.clone().json().then(d => { if (d && d.token) saveToken(d.token); }).catch(() => {});
                } catch(e) {}
                return res;
            });
        };
    } catch(e) {}
    try {
        const origSH = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function(h, v) {
            try { if (h && h.toLowerCase() === 'authorization') saveToken(v); } catch(e) {}
            return origSH.apply(this, arguments);
        };
        const origOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function() {
            this.addEventListener('load', function() {
                try {
                    const d = JSON.parse(this.responseText);
                    if (d && d.token) saveToken(d.token);
                } catch(e) {}
            });
            return origOpen.apply(this, arguments);
        };
    } catch(e) {}
})();
"""
        try:
            ctx.add_init_script(_TOKEN_HOOK_JS)
        except Exception:
            pass

        # Reuse default page in persistent context, or create one
        page = ctx.pages[0] if getattr(ctx, 'pages', None) else ctx.new_page()
        self._page = page

        # Navigate with timeout guard
        try:
            page.goto("https://discord.com/register",
                      wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            try:
                page.goto("https://discord.com/register",
                          wait_until="commit", timeout=15_000)
            except Exception:
                pass

        return page

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def _cleanup(self):
        """Close browser context and clean up temp dirs."""
        try:
            if self._browser_ctx:
                self._browser_ctx.close()
        except Exception:
            pass
        self._browser_ctx = None
        self._page = None

        if self._profile_tmp_dir and os.path.exists(self._profile_tmp_dir):
            try:
                shutil.rmtree(self._profile_tmp_dir, ignore_errors=True)
            except Exception:
                pass
        self._profile_tmp_dir = None

    # ── Form filling ───────────────────────────────────────────────────────────

    def _fill_form(self, email: str, username: str, worker_id: int):
        """Fill Discord registration form fields."""
        display_name = username[:8]

        self._fill_field(
            ["input[name='email']", "input[type='email']",
             "input[autocomplete='email']", "input[placeholder*='email' i]"],
            email
        )
        self._sleep(0.15)

        self._fill_field(
            ["input[name='global_name']", "input[name='display_name']",
             "input[aria-label*='display' i]"],
            display_name
        )
        self._sleep(0.1)

        self._fill_field(
            ["input[name='username']", "input[autocomplete='username']",
             "input[aria-label*='username' i]"],
            username
        )
        self._sleep(0.1)

        self._fill_field(
            ["input[name='password']", "input[type='password']",
             "input[autocomplete='new-password']"],
            self.password
        )
        self._sleep(0.2)

        # DOB via JS dropdowns
        month_idx = random.randint(0, 11)
        day       = str(random.randint(1, 28))
        year      = str(random.randint(1995, 2007))

        self._js(f"""
        (async () => {{
            const delay = ms => new Promise(r => setTimeout(r, ms));
            const selectOption = async (regex, targetVal, isIndex = false) => {{
                const all = Array.from(document.querySelectorAll('*'));
                let btn = all.find(el => {{
                    const label = el.getAttribute('aria-label') || '';
                    return regex.test(label) && (el.getAttribute('role') === 'button' || el.hasAttribute('aria-haspopup'));
                }});
                if (!btn) {{
                    const textElem = all.find(el => regex.test(el.innerText || '') && (el.tagName === 'SPAN' || el.tagName === 'DIV'));
                    if (textElem) btn = textElem.closest('[role="button"], [aria-haspopup="listbox"], [class*="container"]');
                }}
                if (!btn) {{
                    const clickable = all.find(el => {{
                        const text = (el.innerText || '').trim();
                        return regex.test(text) && el.offsetParent !== null && (el.tagName === 'DIV' || el.tagName === 'SPAN') && el.getBoundingClientRect().width > 30;
                    }});
                    if (clickable) btn = clickable.closest('[class*="css-"]') || clickable;
                }}
                if (!btn) return false;
                btn.scrollIntoView({{behavior: 'instant', block: 'center'}});
                btn.click();
                await delay(250);
                let options = Array.from(document.querySelectorAll('[role="option"]'));
                if (!options.length) return false;
                if (isIndex) {{
                    const target = options[targetVal - 1];
                    if (target) {{ target.scrollIntoView({{block: 'nearest'}}); target.click(); return true; }}
                    return false;
                }}
                // Exact match only -- avoid partial matches (e.g. "13" matching "2013")
                let target = options.find(o => (o.innerText || '').trim() === targetVal);
                if (target) {{ target.scrollIntoView({{block: 'nearest'}}); target.click(); return true; }}
                let container = null;
                let el = options[0];
                while (el && el !== document.body) {{
                    const s = window.getComputedStyle(el);
                    if (s.overflowY === 'auto' || s.overflowY === 'scroll') {{ container = el; break; }}
                    el = el.parentElement;
                }}
                if (!container) return false;
                // Reset scroll to top then scan full list
                container.scrollTop = 0;
                await delay(80);
                for (let i = 0; i < 250; i++) {{
                    options = Array.from(document.querySelectorAll('[role="option"]'));
                    target = options.find(o => (o.innerText || '').trim() === targetVal);
                    if (target) break;
                    container.scrollTop += 120;
                    await delay(25);
                }}
                if (!target) return false;
                target.scrollIntoView({{block: 'nearest'}});
                await delay(30);
                target.click();
                return true;
            }};
            await selectOption(/month|maand|mois|mes|mês|mese|monat/i, {month_idx + 1}, true);
            await delay(150);
            await selectOption(/day|dag|jour|día|dia|giorno|tag/i, '{day}', false);
            await delay(150);
            await selectOption(/year|jaar|année|año|ano|anno|jahr/i, '{year}', false);
        }})();
        """)
        self._sleep(0.4)

    # ── hCaptcha solving ───────────────────────────────────────────────────────

    def _solve_hcaptcha_text(self, worker_id: int) -> bool:
        """Solve hCaptcha accessibility text challenge via text solver using Playwright native frame access.
        Handles multiple challenge rounds (hCaptcha may reappear up to 3 times after solving)."""
        try:
            from .text_solver_truedriver import TruedriverTextSolver
            ts = TruedriverTextSolver(
                self,
                worker_id=worker_id,
                context="register",
            )
            
            if not self._has_hcaptcha():
                return True

            # Track consecutive "no captcha" checks to confirm it's truly gone
            no_captcha_streak = 0
            max_no_captcha_streak = 3  # Need 3 consecutive checks with no captcha
            max_attempts = 50  # Increased to handle multiple challenge rounds
            
            for attempt in range(max_attempts):
                self._check_stop()
                
                has_captcha = self._has_hcaptcha()
                if not has_captcha:
                    no_captcha_streak += 1
                    if no_captcha_streak >= max_no_captcha_streak:
                        Logger.STATUS = f"{MskColor.GREEN}hCaptcha solved and confirmed gone"
                        Logger.queue_log(worker_id=worker_id)
                        return True
                    self._sleep(0.5)
                    continue
                else:
                    no_captcha_streak = 0  # Reset streak if captcha reappears
                
                # Find the newassets challenge iframe
                challenge_frame = None
                for frame in self._page.frames:
                    if 'newassets.hcaptcha.com' in (frame.url or ''):
                        challenge_frame = frame
                        break
                
                if not challenge_frame:
                    self._sleep(0.5)
                    continue
                
                # Check if accessibility input is already present
                try:
                    input_el = challenge_frame.query_selector('input[name="captcha"], input.response-input, input[type="text"]')
                    if input_el:
                        # Already in text mode, get the question
                        # Try multiple selectors to get the ACTUAL question (not instruction text)
                        prompt_selectors = [
                            'h2.prompt-text span',
                            '[id*="prompt-text"]',
                            '.prompt-text',
                            'h2 span',
                            '.challenge-prompt .prompt-text',
                            '[class*="prompt"]'
                        ]
                        question = ""
                        for sel in prompt_selectors:
                            prompt_el = challenge_frame.query_selector(sel)
                            if prompt_el:
                                text = (prompt_el.inner_text() or '').strip()
                                # Skip generic instruction text
                                if text and len(text) > 3 and not text.lower().startswith("write just") and not text.lower().startswith("type only") and not text.lower().startswith("from the following"):
                                    question = text
                                    break
                        
                        # If all selectors gave instruction text, try the last one anyway
                        if not question:
                            for sel in prompt_selectors:
                                prompt_el = challenge_frame.query_selector(sel)
                                if prompt_el:
                                    text = (prompt_el.inner_text() or '').strip()
                                    if text and len(text) > 3:
                                        question = text
                                        break
                        
                        if question and len(question) > 3:
                            # Get answer from KB/AI
                            answer = ts._local_solve(question)
                            if not answer:
                                try:
                                    answer = ts._fetch_answer(question)
                                except Exception:
                                    pass
                            
                            if answer:
                                input_el.fill(answer)
                                input_el.press("Enter")
                                self._sleep(1.5)
                                continue
                            else:
                                # AI failed to answer - log it
                                Logger.STATUS = f"{MskColor.YELLOW}AI failed to answer: {question[:50]}"
                                Logger.queue_log(worker_id=worker_id)
                except Exception:
                    pass
                
                # Try to open accessibility menu if not in text mode
                try:
                    # Click the menu button (3 dots)
                    menu_btn = challenge_frame.query_selector('button[aria-haspopup="true"], button[aria-label*="menu" i], button[aria-label*="option" i]')
                    if menu_btn:
                        menu_btn.click()
                        self._sleep(0.5)
                        
                        # Click accessibility CHALLENGE option (not cookie)
                        access_btn = challenge_frame.query_selector('a[href*="accessibility"], button:has-text("Accessibility Challenge"), [role="menuitem"]:has-text("Accessibility Challenge"), button:has-text("Text Challenge"), [role="menuitem"]:has-text("Text Challenge")')
                        if not access_btn:
                            for el in challenge_frame.query_selector_all('a, button, [role="menuitem"]'):
                                text = (el.inner_text() or '').lower()
                                if ('accessibility' in text and 'challenge' in text) or ('text' in text and 'challenge' in text):
                                    access_btn = el
                                    break
                                if 'accessibility' in text and 'cookie' not in text:
                                    access_btn = el
                                    break
                        
                        if access_btn:
                            access_btn.click()
                            self._sleep(1.5)
                            continue
                except Exception:
                    pass
                
                self._sleep(0.5)
            
            # Final check
            return not self._has_hcaptcha()
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Text solver error: {str(e)[:60]}"
            Logger.queue_log(worker_id=worker_id)
            return False

    def _solve_hcaptcha(self, worker_id: int) -> bool:
        """
        then text/AI solver fallback.
        """

        # 2. Text / AI solver
        _solver_ai = self.config.get("solver_ai") or {}
        _auto_solve = self.config.get("auto_solver_captcha", False)
        _any_solver = _auto_solve and any(
            _solver_ai.get(p, False) for p in ("cloudflare", "groq", "openrouter")
        )
        if _any_solver:
            return self._solve_hcaptcha_text(worker_id)

        # 3. No solver -- wait passively
        Logger.STATUS = f"{MskColor.YELLOW}Waiting for captcha to be solved"
        Logger.queue_log(worker_id=worker_id)
        _deadline = time.time() + 180
        while time.time() < _deadline:
            if not self._has_hcaptcha():
                return True
            self._sleep(1)
        return not self._has_hcaptcha()

    # ── Email verification ─────────────────────────────────────────────────────

    def _verify_email_browser(self, verification_url: str, worker_id: int, timeout: int = 90) -> bool:
        """Navigate to the verification link, click confirm, and solve any captcha."""
        try:
            resolved_url = verification_url

            # Follow tracking redirect if needed
            if 'click.discord.com' in verification_url or 'discord.com' not in verification_url:
                try:
                    import requests as _req
                    resp = _req.get(verification_url, allow_redirects=True, timeout=15, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    if resp.url and 'discord.com' in resp.url:
                        resolved_url = resp.url
                    else:
                        loc = resp.headers.get('Location', '')
                        if loc and 'discord.com' in loc:
                            resolved_url = loc
                except Exception:
                    pass

            try:
                self._page.goto(resolved_url, wait_until="domcontentloaded", timeout=20_000)
            except Exception:
                pass
            self._sleep(2)

            # Click verify button
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
            self._sleep(1.5)

            _ok_kws = ['done', 'verified', 'email verified', "you're all set",
                       'success', 'verification successful']

            def _page_verified() -> bool:
                try:
                    txt = str(self._js('document.body.innerText') or '').lower()
                    if any(k in txt for k in _ok_kws):
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

            _solver_ai = self.config.get("solver_ai") or {}
            _auto_solve = self.config.get("auto_solver_captcha", False)
            _any_solver = _auto_solve and (
                any(_solver_ai.get(p, False) for p in ("cloudflare", "groq", "openrouter"))
            )

            _deadline = time.time() + timeout
            _cap_retries = 0

            while time.time() < _deadline:
                if _page_verified():
                    Logger.STATUS = f"{MskColor.GREEN}Email verified!"
                    Logger.queue_log(worker_id=worker_id)
                    return True

                if self._has_hcaptcha():
                    if _any_solver and _cap_retries < 3:
                        _cap_retries += 1
                        Logger.STATUS = f"{MskColor.YELLOW}Email verify captcha, solving..."
                        Logger.queue_log(worker_id=worker_id)
                        _solved = self._solve_hcaptcha_text(worker_id)
                        if not _solved:
                            break
                        self._sleep(2)
                        continue
                    else:
                        _wait_end = min(time.time() + 45, _deadline)
                        while time.time() < _wait_end:
                            if not self._has_hcaptcha():
                                break
                            self._sleep(0.5)

                self._sleep(0.4)

            return _page_verified()

        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Email verify error: {str(e)[:60]}"
            Logger.queue_log(worker_id=worker_id)
            return False

    # ── Stats output ───────────────────────────────────────────────────────────

    def print_stats(self, worker_id, token, elapsed_time, startup_time,
                    hcap_wait, hcap_solve, humanize_time, email_verify_time,
                    phone_verify_time, phone_verified, humanize_status, ev_status_str):
        """Print generation stats tree identical to Brave / Chromium format."""
        try:
            _msk = f"{MskColor.PRIMARY}[Msk]{MskColor.RESET} "
            _R   = MskColor.RESET

            logs_cfg = (self.config.get("logs") or {})
            # Use censor_token setting (same as Brave/Chromium)
            censor = logs_cfg.get("censor_token", True)
            if censor and token and len(token) > 14:
                tok_display = f"{token[:10]}{'*' * max(0, len(token) - 14)}{token[-4:]}"
            else:
                tok_display = token

            rows = [
                ("Token",               tok_display,                                    True),
                ("Generation Time",     f"{elapsed_time:.2f}s",                        logs_cfg.get("generation_time", True)),
                ("Startup Time",        f"{startup_time:.2f}s",                        logs_cfg.get("startup_time", True)),
                ("hCaptcha Waiting Time", f"{hcap_wait:.2f}s",                         logs_cfg.get("hcaptcha_waiting", True)),
                ("hCaptcha Solving Time", f"{hcap_solve:.2f}s",                        logs_cfg.get("hcaptcha_solving", True)),
                ("Humanize Time",       f"{humanize_time:.2f}s",                       logs_cfg.get("humanize_time", True)),
                ("Email Verify Time",   f"{email_verify_time:.2f}s",                   logs_cfg.get("verify_time", True)),
                ("Phone Verify Time",   f"{phone_verify_time:.2f}s",                   logs_cfg.get("phone_verify_time", False)),
                ("Total Time",          f"{(elapsed_time + startup_time + email_verify_time + phone_verify_time):.2f}s",
                                                                                        logs_cfg.get("total_time", True)),
                ("Status",              (
                    f"{ev_status_str}{_R}, "
                    f"{'Phone Verified' if phone_verified else 'Not Phone Verified'}"
                ),                                                                      True),
            ]

            visible = [(label, val) for label, val, show in rows if show]

            for i, (label, val) in enumerate(visible):
                prefix = "└─" if i == len(visible) - 1 else "├─"
                Logger.STATUS = f"{MskColor.GREY}{prefix} {MskColor.RESET}{label}: {val}"
                Logger.queue_log(worker_id=worker_id)
        except Exception:
            pass

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

        # Fallback
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


    # ── Main register entry point ──────────────────────────────────────────────

    def register(self, worker_id: int, on_browser_closed=None) -> str:
        """
        Full Discord registration flow using Clearcote browser.
        Returns: 'Valid' | 'Locked' | 'Invalid' | 'ignore'
        """
        self.worker_id = worker_id
        _msk = f"{MskColor.PRIMARY}[Msk]{MskColor.RESET} "

        start_time_startup = time.time()
        proxy_data: Optional[Dict] = None
        email_address = ""
        email_password = ""
        hcap_wait_time = 0.0
        hcap_solve_time = 0.0

        try:
            self._check_stop()

            # ── Proxy / VPN setup ──────────────────────────────────────────────
            proxy_data = None
            proxies_cfg = self.config.get("proxies") or {}
            use_proxies = proxies_cfg.get("enabled", False)

            if use_proxies:
                proxy_data = self.proxy_manager.get_proxy(worker_id=worker_id)
                if not proxy_data:
                    proxy_data = self.proxy_manager.wait_for_proxies(worker_id)
                if proxy_data:
                    if proxies_cfg.get("remove_after_use", False):
                        self.proxy_manager.remove_proxy(proxy_data)
                    server = proxy_data.get("server", "")
                    host_port = server.split("://")[-1]
                    username = proxy_data.get("username", "")
                    pwd = proxy_data.get("password", "")
                    full_proxy = f"{username}:{pwd}@{host_port}" if username and pwd else host_port
                    Logger.STATUS = f"{MskColor.PRIMARY}Using Proxy: {full_proxy}"
                    Logger.queue_log(worker_id=worker_id)
            else:
                mullvad_cfg = self.config.get("vpn_providers", {}).get("mullvad", {})
                mullvad_enabled = mullvad_cfg.get("enabled", False) or self.config.get("mullvad", False)
                if mullvad_enabled:
                    try:
                        from ..Utils.mullvad_manager import MullvadManager
                        current_ip = MullvadManager.get_current_ip()
                        if current_ip:
                            Logger.STATUS = f"{MskColor.GREEN}Connected to Mullvad IP: {current_ip}"
                            Logger.queue_log(worker_id=worker_id)
                    except Exception:
                        pass

            # ── Email setup ────────────────────────────────────────────────────
            email_address, email_password = self._create_email(worker_id)
            if not email_address:
                return "Invalid"

            use_real_usernames = self.config.get("real_usernames", False)
            username = (
                Utils.generate_real_username(use_api=use_real_usernames)
                if use_real_usernames
                else Utils.sanitize_username(Utils.random_string())
            )

            # ── Launch browser ─────────────────────────────────────────────────
            headless = self.config.get("headless", False)
            wm = None
            slot_idx = None
            wm_pos = None
            try:
                from ..Utils.window_manager import WindowManager
                wm = WindowManager()
                slot_idx, wm_pos = wm.acquire()
            except Exception:
                pass

            Logger.STATUS = f"{MskColor.PRIMARY}Starting Clearcote Browser"
            Logger.queue_log(worker_id=worker_id)

            self._create_browser(headless=headless, proxy=proxy_data, wm_pos=wm_pos)

            startup_time = time.time() - start_time_startup

            # ── Wait for registration form to load ─────────────────────────────
            start_wait = time.time()
            found_form = False
            while time.time() - start_wait < 60:
                self._check_stop()
                try:
                    el = self._page.query_selector('input[name="email"], input[type="email"]')
                    if el and el.is_visible():
                        found_form = True
                        break
                except Exception:
                    pass
                if self._has_hcaptcha():
                    found_form = True
                    break
                self._sleep(0.5)

            if not found_form:
                raw_text = self._js("(() => document.body ? document.body.innerText : '')()")
                page_text = str(raw_text).lower() if raw_text else ""
                if any(kw in page_text for kw in ["403", "access denied", "cloudflare"]):
                    Logger.STATUS = f"{MskColor.RED}Discord blocked this IP."
                    Logger.queue_log(worker_id=worker_id)
                    return "RateLimited"
                Logger.STATUS = f"{MskColor.RED}Registration form not found"
                Logger.queue_log(worker_id=worker_id)
                return "RateLimited"

            self._check_stop()
            Logger.STATUS = f"{MskColor.PRIMARY}Filling Form"
            Logger.queue_log(worker_id=worker_id)
            self._fill_form(email_address, username, worker_id)

            # Click submit button
            self._sleep(0.8)
            self._check_stop()
            submitted = False
            try:
                btn = self._page.query_selector('button[type="submit"]')
                if btn and btn.is_visible():
                    btn.click()
                    submitted = True
            except Exception:
                pass
            if not submitted:
                self._js("""
                    (() => {
                        const btn = document.querySelector('button[type="submit"]');
                        if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return 'submitted'; }
                        const kw = ['create account', 'continue', 'register'];
                        for (const b of document.querySelectorAll('button')) {
                            const t = (b.innerText || '').toLowerCase();
                            if (kw.some(k => t.includes(k))) { b.click(); return 'clicked_text'; }
                        }
                        return 'not_found';
                    })()
                """)

            start_time = time.time()

            # ── Wait for captcha ───────────────────────────────────────────────
            _wait_hcap_start = time.time()
            hcaptcha_appeared = False
            _max_wait = 20

            for _ in range(_max_wait * 2):
                self._check_stop()
                if self._has_hcaptcha():
                    hcaptcha_appeared = True
                    break
                if self._check_passed():
                    break
                self._sleep(0.5)

            hcap_wait_time = time.time() - _wait_hcap_start if hcaptcha_appeared else 0.0
            hcap_solve_time = 0.0

            # ── Solve captcha ──────────────────────────────────────────────────
            if hcaptcha_appeared:
                Logger.STATUS = f"{MskColor.YELLOW}Captcha Found"
                Logger.queue_log(worker_id=worker_id)

                _solve_start = time.time()
                solved = self._solve_hcaptcha(worker_id)
                hcap_solve_time = time.time() - _solve_start

                if not solved:
                    Logger.STATUS = f"{MskColor.RED}Captcha not solved"
                    Logger.queue_log(worker_id=worker_id)
                else:
                    # Wait for form to process
                    for _ in range(20):
                        self._check_stop()
                        if self._check_passed():
                            break
                        self._sleep(0.5)

            elapsed_time = time.time() - start_time

            # ── Extract token ──────────────────────────────────────────────────
            token: Optional[str] = None
            for _ in range(20):
                token = self._extract_token()
                if token:
                    break
                self._sleep(1)

            if not token:
                # Navigate to app to trigger token storage
                try:
                    self._page.goto("https://discord.com/app",
                                    wait_until="domcontentloaded", timeout=20_000)
                except Exception:
                    pass
                self._sleep(3)
                for _ in range(15):
                    token = self._extract_token()
                    if token:
                        break
                    self._sleep(1)

            # ── Email verification ─────────────────────────────────────────────
            token_verify_enabled = self.config.get("token_verify", True)
            start_time_verify = time.time()
            ev_status = False

            if token_verify_enabled and (token or hcaptcha_appeared):
                email_providers = self.config.get("email_providers") or {}
                mail_api = None
                verify_kwargs: Dict = {"email": email_address, "timeout": 120, "poll_interval": 3}

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

                    _stop_fn = lambda: getattr(getattr(self, 'controller', None), 'should_stop', False)
                    verify_kwargs['stop_signal'] = _stop_fn

                try:
                    from ..Helper.mail import suppress_output
                    with suppress_output():
                        if hasattr(mail_api, 'get_verification_link'):
                            v_url = mail_api.get_verification_link(**verify_kwargs)
                        elif hasattr(mail_api, 'get_verification_url'):
                            v_url = mail_api.get_verification_url(**verify_kwargs)
                        else:
                            v_url = None

                    if v_url:
                        ev_status = self._verify_email_browser(v_url, worker_id)
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}No verification link found"
                        Logger.queue_log(worker_id=worker_id)
                except Exception as e:
                    Logger.STATUS = f"{MskColor.YELLOW}Email verify failed: {str(e)[:60]}"
                    Logger.queue_log(worker_id=worker_id)

            email_verify_time = time.time() - start_time_verify if token_verify_enabled else 0.0

            # Final token attempt after verify
            if not token:
                try:
                    self._page.goto("https://discord.com/app",
                                    wait_until="domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                self._sleep(3)
                for _ in range(15):
                    token = self._extract_token()
                    if token:
                        break
                    self._sleep(1)

            # ── Humanizer ──────────────────────────────────────────────────────
            humanize_time = 0.0
            humanize_status = f"{MskColor.GREY}Skipped"
            h_result = False
            humanize_cfg = self.config.get("humanizer") or {}
            if token and humanize_cfg.get("enabled", False):
                start_hum = time.time()
                try:
                    Logger.STATUS = f"{MskColor.LIGHTBLUE}Humanizing account..."
                    Logger.queue_log(worker_id=worker_id)
                    from ..Helper.huminazer import DiscordHuminazer
                    humanizer = DiscordHuminazer(worker_id=worker_id)
                    h_result = humanizer.humanize_account(token, proxy_data)
                    humanize_status = f"{MskColor.GREEN}Humanized" if h_result else f"{MskColor.RED}Failed"
                except Exception as he:
                    humanize_status = f"{MskColor.RED}Error"
                    Logger.STATUS = f"{MskColor.RED}Humanize error: {str(he)[:50]}"
                    Logger.queue_log(worker_id=worker_id)
                humanize_time = time.time() - start_hum

            ev_status_str = f"{MskColor.GREEN}Email Verified" if ev_status else f"{MskColor.RED}Unclaimed"

            if ev_status:
                Logger.STATUS = f"{MskColor.GREEN}Account Created & Verified!"
            else:
                Logger.STATUS = f"{MskColor.PRIMARY}Account Created (Unverified)!"
            Logger.queue_log(worker_id=worker_id)

            if not token:
                Logger.STATUS = f"{MskColor.RED}Token extraction failed"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

            # ── Save token ─────────────────────────────────────────────────────
            output_path = os.path.join(get_base_path(), "data", "output", "tokens.txt")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(f"{email_address}:{self.password}:{token}\n")

            # ── Token status check ─────────────────────────────────────────────
            generation_status = "Valid"
            try:
                from .token_checker import check_token_safe
                _tc = check_token_safe(
                    token,
                    proxy=proxy_data if use_proxies else None
                )
                if not _tc.get("valid"):
                    Logger.STATUS = f"{MskColor.RED}Token Invalid"
                    generation_status = "Invalid"
                elif _tc.get("locked") or _tc.get("email_required") or _tc.get("phone_required"):
                    Logger.STATUS = f"{MskColor.ORANGE}Token Locked"
                    generation_status = "Locked"
                else:
                    Logger.STATUS = f"{MskColor.GREEN}Token Valid"
                    generation_status = "Valid"
                Logger.queue_log(worker_id=worker_id)
            except Exception:
                pass

            Logger.STATUS = f"{MskColor.GREEN}Token Generated!"
            Logger.queue_log(worker_id=worker_id)

            try:
                if sys.stdout:
                    sys.stdout.write("\n")
            except Exception:
                pass

            total_startup = time.time() - start_time_startup
            self.print_stats(
                worker_id, token, elapsed_time, startup_time,
                hcap_wait_time, hcap_solve_time, humanize_time,
                email_verify_time, 0.0, False,
                humanize_status, ev_status_str
            )

            self.last_result = {
                "token":          str(token),
                "email":          str(email_address),
                "status":         generation_status,
                "humanized":      bool(h_result),
                "phone_verified": False,
                "email_verified": bool(ev_status),
                "gen_time":       round(float(elapsed_time or 0.0), 1),
                "hcap_time":      round(float(hcap_solve_time or 0.0), 1),
                "email_time":     round(float(email_verify_time or 0.0), 1),
                "phone_time":     0.0,
                "humanize_time":  round(float(humanize_time or 0.0), 1),
            }

            return generation_status

        except GeneratorStoppedError:
            return "ignore"
        except Exception as e:
            err = str(e)
            if "Stopped by user" in err:
                return "ignore"
            Logger.STATUS = f"{MskColor.RED}Clearcote error: {err[:80]}"
            Logger.queue_log(worker_id=worker_id)
            return "Invalid"
        finally:
            self._cleanup()
            if on_browser_closed:
                try:
                    on_browser_closed(worker_id)
                except Exception:
                    pass
            try:
                import gc
                gc.collect()
            except Exception:
                pass
