"""Text-based hCaptcha accessibility solver for Truedriver browsers.

CDP iframe access: Target.setAutoAttach on browser.connection websocket.
The browser-level CDP session receives AttachedToTarget events with a real
sessionId for every iframe target, including cross-origin hcaptcha.com frames.
Runtime.evaluate sent with that sessionId executes JS inside the iframe.
This is exactly how Chrome DevTools itself accesses cross-origin iframes.
"""

import json
import itertools
import os
import time
import random
import re
import requests
from typing import Optional, Dict, List, Tuple

from ..MskColors.color import MskColor
from ..Utils.logger import Logger
from ..Utils.utils import Config, get_base_path, _is_frozen

try:
    from groq import Groq, RateLimitError
except ImportError:
    Groq = None
    RateLimitError = Exception

# Monotonic counter for raw CDP message IDs on browser.connection websocket
_CDP_MSG_COUNTER = itertools.count(80000)

SYSTEM_PROMPT = (
    "You are an elite hCaptcha accessibility text challenge solver. "
    "CRITICAL SYSTEM RULES: "
    "1. Questions may be in ANY language -- always understand and solve correctly. "
    "2. True Yes/No question: answer ONLY 'yes'/'no' (or 'ya'/'tidak' if Indonesian). "
    "3. Provide ONLY the answer. No punctuation, no intro phrases, max 5 words. "
    "4. NUMERIC: If asked for a count/quantity, give the DIGIT (e.g. '7'). "
    "5. COMPARISONS: Output only the name of the winning object. "
    "6. HYPOTHETICALS: Resolve the logical state (e.g. 'Jika es mencair' -> 'air'). "
    "7. CATEGORIZATION: Output the category name only. "
    "8. CHAR/DIGIT MANIPULATION: Output ONLY the final modified string. "
    "9. EXTRACTION: Output ONLY the extracted item. "
    "10. IGNORE INSTRUCTION TEXT: If the input contains 'Write just your answer', 'Type only', "
    "'From the following', 'Select the', 'Choose the', 'Identify', 'Give only', or similar instructions, "
    "IGNORE them and answer the ACTUAL question that follows. "
    "EXAMPLES: "
    "Q: 'Write the country name from the following 3 words colander, sweden, microphone' -> A: 'sweden' "
    "Q: 'Give only the name of the animal that swims and lives in water. deer, wolf, cod' -> A: 'cod' "
    "Q: 'What do cars need in their tires to work properly?' -> A: 'air' "
    "Q: 'Identify the word that does not name an animal cup lion whale' -> A: 'cup' "
    "STRICT: Any filler or explanation = failure. Answer now."
)

# Injected via addScriptToEvaluateOnNewDocument into ALL new documents.
# In hCaptcha iframes this SENDS the question via postMessage.
# In the main Discord page this LISTENS and stores the message.
_HCAP_BRIDGE_JS = """
(function() {
    var isHcap = window.location.hostname.indexOf('hcaptcha') !== -1 ||
                 window.location.hostname.indexOf('newassets') !== -1;

    if (isHcap) {
        // SENDER: runs inside hCaptcha iframe, relays state to parent
        if (window.__hcapSenderActive) return;
        window.__hcapSenderActive = true;
        function _relay() {
            try {
                var question = '';
                var sels = ['h2.prompt-text', '[id^="prompt-text"]', '.prompt-text',
                            '.challenge-prompt .prompt-text', '[class*="prompt"]'];
                for (var i = 0; i < sels.length; i++) {
                    var el = document.querySelector(sels[i]);
                    if (el && el.innerText && el.innerText.trim().length > 3) {
                        question = el.innerText.trim(); break;
                    }
                }
                var hasInput = false;
                var inputSels = ['input.response-input','input[id^="response"]',
                                 'input[name="response"]','input[name="captcha"]','input[type="text"]'];
                for (var j = 0; j < inputSels.length; j++) {
                    var inp = document.querySelector(inputSels[j]);
                    if (inp && inp.offsetParent !== null) { hasInput = true; break; }
                }
                var hasMenu = !!document.querySelector(
                    '[data-testid="menu-opener"],[aria-label="hCaptcha"],#menu-info,[class*="menu-icon"]');
                parent.postMessage(JSON.stringify({
                    type: '__hcap_bridge',
                    question: question,
                    hasInput: hasInput,
                    hasMenu: hasMenu,
                    ts: Date.now()
                }), '*');
            } catch(e) {}
        }
        _relay();
        setInterval(_relay, 400);
    } else {
        // LISTENER: runs in main Discord page, stores bridge messages
        if (window.__hcapListenerActive) return;
        window.__hcapListenerActive = true;
        window.__hcap_bridge = null;
        window.addEventListener('message', function(ev) {
            try {
                var d = (typeof ev.data === 'string') ? JSON.parse(ev.data) : ev.data;
                if (d && d.type === '__hcap_bridge') window.__hcap_bridge = d;
            } catch(e) {}
        });
    }
})();
"""

_HCAP_INPUT_SELECTORS = (
    'input.response-input',
    'input[id^="response"]',
    'input[name="response"]',
    'input[autocomplete="off"][type="text"]',
    'input[name="captcha"]',
    'input[type="text"]',
)
_HCAP_INPUT_SEL_JS = json.dumps(list(_HCAP_INPUT_SELECTORS))


class TruedriverTextSolver:
    """Solve hCaptcha accessibility text challenges on truedriver browsers.

    Primary: Target.setAutoAttach on browser.connection -> sessionId for hCaptcha
             iframe -> Runtime.evaluate with sessionId -> full JS access in iframe.

    Fallback: postMessage bridge already injected via addScriptToEvaluateOnNewDocument.
              Reads question from window.__hcap_bridge on the main page,
              submits answer via CDP mouse clicks at computed screen coordinates.
    """

    _rate_limited_until: float = 0.0

    def __init__(self, register_instance, worker_id: int, context: str = 'register'):
        self._reg = register_instance
        self.worker_id = worker_id
        self.context = context  # 'register' or 'email_verify'
        self.knowledgebase = self._load_knowledgebase()
        self._hcap_session_id: Optional[str] = None  # CDP sessionId for hCaptcha iframe
        self._use_bridge: bool = False                # True when auto-attach failed

    @property
    def config(self) -> Dict:
        return Config.config

    def _get_kb_path(self) -> str:
        if _is_frozen():
            return os.path.join(get_base_path(), "MSK_core", "Assets", "knowledgebase.json")
        return "MSK_core/Assets/knowledgebase.json"

    def _load_knowledgebase(self) -> Dict[str, str]:
        path = self._get_kb_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_knowledgebase(self):
        path = self._get_kb_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.knowledgebase, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _normalize(q: str) -> str:
        q = q.strip().lower()
        for c in '?!.,;:':
            q = q.strip(c)
        return ' '.join(q.split())

    def _kb_lookup(self, question: str) -> Optional[str]:
        n = self._normalize(question)
        if n in self.knowledgebase:
            return self.knowledgebase[n]
        stripped = n.replace('?','').replace('!','').replace('.','').strip()
        for k, v in list(self.knowledgebase.items()):
            ks = self._normalize(k).replace('?','').replace('!','').replace('.','').strip()
            if stripped == ks:
                return v
        return None

    def _js(self, script: str) -> object:
        return self._reg._js(script)

    def _run(self, coro, timeout: int = 15):
        return self._reg._run(coro, timeout=timeout)

    def _cdp_click(self, x: int, y: int):
        try:
            import truedriver.cdp.input_ as input_cdp
            self._run(self._reg._tab.send(input_cdp.dispatch_mouse_event(
                type_="mousePressed", x=x, y=y, button=input_cdp.MouseButton.LEFT, click_count=1
            )))
            time.sleep(0.05)
            self._run(self._reg._tab.send(input_cdp.dispatch_mouse_event(
                type_="mouseReleased", x=x, y=y, button=input_cdp.MouseButton.LEFT, click_count=1
            )))
        except Exception:
            self._js(f"document.elementFromPoint({x},{y})?.click()")

    def _bconn_send(self, method: str, params: dict, timeout: int = 8) -> Optional[dict]:
        """Send a raw CDP command over browser.connection websocket and return result.

        browser.connection is the browser-level CDP session. Commands sent here
        can include sessionId to target specific sub-targets (iframes).
        The mapper uses (**message) call convention -- our _Fut matches that.
        """
        import asyncio

        browser = self._reg._browser
        bconn = getattr(browser, 'connection', None)
        if bconn is None:
            return None

        async def _run():
            if getattr(bconn, 'websocket', None) is None:
                try:
                    await bconn.aopen()
                except Exception:
                    return None
            ws = bconn.websocket
            if ws is None:
                return None


            class _Fut(asyncio.Future):
                def __call__(self, **msg):
                    if not self.done():
                        self.set_result(msg)

            fut = _Fut()
            msg_id = next(_CDP_MSG_COUNTER)
            bconn.mapper[msg_id] = fut

            raw = {"id": msg_id, "method": method, "params": params}
            try:
                await ws.send(json.dumps(raw))
            except Exception:
                bconn.mapper.pop(msg_id, None)
                return None

            try:
                result = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
                return result
            except asyncio.TimeoutError:
                bconn.mapper.pop(msg_id, None)
                return None

        try:
            return self._reg._run(_run(), timeout=timeout + 5)
        except Exception:
            return None

    def _bconn_send_session(self, method: str, params: dict,
                             session_id: str, timeout: int = 8) -> Optional[dict]:
        """Send CDP command to a specific session (iframe) via browser.connection."""
        import asyncio

        browser = self._reg._browser
        bconn = getattr(browser, 'connection', None)
        if bconn is None:
            return None

        async def _run():
            if getattr(bconn, 'websocket', None) is None:
                try:
                    await bconn.aopen()
                except Exception:
                    return None
            ws = bconn.websocket
            if ws is None:
                return None


            class _Fut(asyncio.Future):
                def __call__(self, **msg):
                    if not self.done():
                        self.set_result(msg)

            fut = _Fut()
            msg_id = next(_CDP_MSG_COUNTER)
            bconn.mapper[msg_id] = fut

            raw = {
                "id": msg_id,
                "method": method,
                "params": params,
                "sessionId": session_id,
            }
            try:
                await ws.send(json.dumps(raw))
            except Exception:
                bconn.mapper.pop(msg_id, None)
                return None

            try:
                result = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
                return result
            except asyncio.TimeoutError:
                bconn.mapper.pop(msg_id, None)
                return None

        try:
            return self._reg._run(_run(), timeout=timeout + 5)
        except Exception:
            return None

    def _js_in_session(self, expr: str, session_id: str, timeout: int = 6) -> Optional[str]:
        """Run JS expression in the hCaptcha iframe via its CDP sessionId."""
        result = self._bconn_send_session(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "silent": True,
                "awaitPromise": False,
            },
            session_id=session_id,
            timeout=timeout,
        )
        if not result:
            return None
        val = result.get("result", {}).get("result", {}).get("value")
        return str(val) if val is not None else None

    def _wait_for_widget_iframe(self, timeout: float = 15.0) -> bool:
        """Wait until the hCaptcha checkbox widget iframe is visible and ready.

        The widget iframe loads first (small, ~74x74 px). We must wait for it
        to be present and rendered BEFORE clicking it, otherwise the click is
        a no-op and the challenge iframe never appears.
        """
        start = time.time()
        while time.time() - start < timeout:
            wx, wy, ww, wh = self._get_widget_iframe_rect()
            if ww > 20 and wh > 20:
                return True
            # Also check if a large challenge iframe is already present
            # (may have been pre-triggered in email_verify context)
            ix, iy, iw, ih = self._get_iframe_rect()
            if iw > 200 and ih > 200:
                return True
            time.sleep(0.3)
        return False

    def _is_challenge_session(self, sid: str) -> bool:
        """Verify whether a CDP session belongs to the challenge popup (not the checkbox widget)."""
        try:
            res = self._js_in_session("""
                (() => {
                    const hash = window.location.hash || '';
                    const href = window.location.href || '';
                    if (hash.includes('frame=challenge') || href.includes('frame=challenge')) return 'yes';
                    if (document.querySelector('[data-testid="menu-opener"], [data-testid="menu-info"], #menu-info, .challenge-container, [aria-label*="Challenge"], .prompt-text, #prompt-text, input[name="captcha"], input.response-input')) return 'yes';
                    if (hash.includes('frame=checkbox') || href.includes('frame=checkbox') || document.querySelector('#checkbox, #anchor')) return 'no';
                    return 'unknown';
                })()
            """, sid, timeout=3)
            return res == 'yes'
        except Exception:
            return False

    def _find_hcap_session(self, timeout: int = 22) -> Optional[str]:
        """Find the hCaptcha challenge iframe sessionId via Target.setAutoAttach.

        Flow:
          1. browser.connection: Target.setAutoAttach(autoAttach=true, flatten=true)
             CDP replies with Target.attachedToTarget events for every existing target
             AND will notify for new targets as they appear.
          2. Poll Target.getTargets() to list all known sub-targets.
          3. For each target with type='iframe' and url containing hcaptcha.com,
             call Target.attachToTarget(targetId, flatten=true) to get a sessionId.
          4. Smoke-test: Runtime.evaluate in that session.
        """
        start = time.time()
        _widget_clicked = False
        _last_click_t = 0.0

        # For register context: wait for the widget iframe to load before starting.
        # Trying to click before it's rendered is an invisible no-op.
        if self.context != 'email_verify':
            widget_ready = self._wait_for_widget_iframe(timeout=min(timeout * 0.6, 12.0))
            if not widget_ready:
                # Widget never appeared -- may already be on a challenge iframe
                ix, iy, iw, ih = self._get_iframe_rect()
                if iw <= 200 or ih <= 200:
                    # Nothing loaded yet, still proceed (will poll in main loop)
                    pass

        # Enable auto-attach so iframe targets become visible
        auto_attach_result = self._bconn_send("Target.setAutoAttach", {
            "autoAttach": True,
            "waitForDebuggerOnStart": False,
            "flatten": True,
        }, timeout=6)

        # Track sessionIds from auto-attach events that may be delivered asynchronously.
        # After setAutoAttach, the browser sends Target.attachedToTarget events for every
        # existing target. These arrive as mapper callbacks with 'params' containing sessionId.
        _auto_attached_sessions: list = []

        # Capture any auto-attached sessions from the mapper events
        try:
            browser = self._reg._browser
            bconn = getattr(browser, 'connection', None)
            if bconn:
                # Check recently-received events in the mapper for attachedToTarget
                for key, val in list(getattr(bconn, 'mapper', {}).items()):
                    if hasattr(val, 'result') and callable(getattr(val, 'result', None)):
                        try:
                            r = val.result() if not hasattr(val, '_result') else getattr(val, '_result', None)
                            if isinstance(r, dict) and 'params' in r:
                                params = r.get('params', {})
                                ti = params.get('targetInfo', {})
                                url = (ti.get('url') or '').lower()
                                sid = params.get('sessionId', '')
                                if sid and ('hcaptcha' in url or 'newassets' in url):
                                    _auto_attached_sessions.append((sid, url))
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            while time.time() - start < timeout:
                elapsed = time.time() - start

                # For email_verify, the challenge is already open -- never click the checkbox.
                # Clicking it would DISMISS the open challenge iframe.
                # For register, only click checkbox if challenge is NOT already open.
                ix, iy, iw, ih = self._get_iframe_rect()
                _challenge_open = iw > 200 and ih > 200
                if self.context != 'email_verify' and not _challenge_open:
                    should_click = not _widget_clicked or (elapsed - _last_click_t > 8)
                    if should_click:
                        wx, wy, ww, wh = self._get_widget_iframe_rect()
                        if ww > 0:
                            self._cdp_click(int(wx + 30), int(wy + wh / 2))
                            _widget_clicked = True
                            _last_click_t = elapsed
                            # Wait longer for Discord/hCaptcha to open the challenge iframe
                            time.sleep(2.0)

                # Try any auto-attached sessions first (filtering for challenge frame)
                for item in list(_auto_attached_sessions):
                    sid = item[0] if isinstance(item, tuple) else item
                    url = item[1] if isinstance(item, tuple) else ""
                    if "frame=checkbox" in url:
                        continue
                    if self._is_challenge_session(sid):
                        return sid
                _auto_attached_sessions.clear()

                # Get all current targets
                targets_result = self._bconn_send("Target.getTargets", {}, timeout=6)
                targets = []
                if targets_result:
                    targets = targets_result.get("result", {}).get("targetInfos", [])

                # Find hCaptcha challenge target
                hcap_target_id = None
                for t in targets:
                    url = (t.get("url") or "").lower()
                    if ("hcaptcha" in url or "newassets" in url) and ("frame=challenge" in url or "challenge" in url):
                        hcap_target_id = t.get("targetId")
                        break
                if not hcap_target_id and self.context == 'email_verify':
                    for t in targets:
                        url = (t.get("url") or "").lower()
                        if ("hcaptcha" in url or "newassets" in url) and "frame=checkbox" not in url:
                            hcap_target_id = t.get("targetId")
                            break

                if hcap_target_id:
                    # Attach to get a sessionId
                    attach_result = self._bconn_send("Target.attachToTarget", {
                        "targetId": hcap_target_id,
                        "flatten": True,
                    }, timeout=6)
                    session_id = None
                    if attach_result:
                        session_id = attach_result.get("result", {}).get("sessionId")
                    if session_id and self._is_challenge_session(session_id):
                        return session_id

                # Fallback: try to discover hCaptcha sessions via the tab's targets
                # Some truedriver versions expose targets differently
                try:
                    tab = self._reg._tab
                    if tab and hasattr(tab, 'targets') and tab.targets:
                        for target in tab.targets:
                            turl = (getattr(target, 'url', '') or '').lower()
                            if 'hcaptcha' in turl or 'newassets' in turl:
                                tid = getattr(target, 'target_id', None)
                                if tid:
                                    attach_result = self._bconn_send("Target.attachToTarget", {
                                        "targetId": tid,
                                        "flatten": True,
                                    }, timeout=4)
                                    if attach_result:
                                        session_id = attach_result.get("result", {}).get("sessionId")
                                        if session_id:
                                            test = self._js_in_session("document.readyState", session_id, timeout=3)
                                            if test in ("complete", "interactive", "loading"):
                                                return session_id
                except Exception:
                    pass

                time.sleep(0.8)

        finally:
            # Clean up auto-attach
            try:
                self._bconn_send("Target.setAutoAttach", {
                    "autoAttach": False,
                    "waitForDebuggerOnStart": False,
                    "flatten": True,
                }, timeout=4)
            except Exception:
                pass

        return None

    def _get_iframe_rect(self) -> Tuple[float, float, float, float]:
        result = self._js("""
            (() => {
                for (const f of document.querySelectorAll('iframe')) {
                    const src = (f.getAttribute('src') || '').toLowerCase();
                    if (src.includes('hcaptcha')) {
                        const r = f.getBoundingClientRect();
                        if (r.width > 200 && r.height > 200)
                            return r.x + ',' + r.y + ',' + r.width + ',' + r.height;
                    }
                }
                return '';
            })()
        """)
        try:
            parts = str(result or '').split(',')
            if len(parts) == 4:
                return float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        except Exception:
            pass
        return 0.0, 0.0, 0.0, 0.0

    def _get_widget_iframe_rect(self) -> Tuple[float, float, float, float]:
        result = self._js("""
            (() => {
                for (const f of document.querySelectorAll('iframe')) {
                    const src = (f.getAttribute('src') || '').toLowerCase();
                    if (!src.includes('hcaptcha')) continue;
                    const r = f.getBoundingClientRect();
                    if (r.width > 20 && r.width < 500 && r.height > 20 && r.height < 200)
                        return r.x + ',' + r.y + ',' + r.width + ',' + r.height;
                }
                return '';
            })()
        """)
        try:
            parts = str(result or '').split(',')
            if len(parts) == 4:
                return float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        except Exception:
            pass
        return 0.0, 0.0, 0.0, 0.0

    def _wait_for_challenge_frame(self, timeout: int = 25) -> bool:
        """Find hCaptcha iframe. Try Target.setAutoAttach first, fall back to bridge."""
        session_id = self._find_hcap_session(timeout=timeout)
        if session_id:
            self._hcap_session_id = session_id
            self._use_bridge = False
            return True

        # Fallback 1: use postMessage bridge already injected into page

        # Re-inject the bridge JS -- addScriptToEvaluateOnNewDocument may not have
        # fired in the hCaptcha iframe if it was loaded before the script was added.
        # Also re-inject the sender into the hCaptcha iframe via a fallback approach:
        # click nothing, just inject the listener on the main page.
        self._js(_HCAP_BRIDGE_JS)

        # Also try to inject the bridge sender into the hCaptcha iframe via
        # Target.getTargets() → attachToTarget → Runtime.evaluate
        try:
            targets_result = self._bconn_send("Target.getTargets", {}, timeout=6)
            if targets_result:
                for t in targets_result.get("result", {}).get("targetInfos", []):
                    url = (t.get("url") or "").lower()
                    if "hcaptcha" in url or "newassets" in url:
                        try:
                            attach_result = self._bconn_send("Target.attachToTarget", {
                                "targetId": t.get("targetId"),
                                "flatten": True,
                            }, timeout=4)
                            if attach_result:
                                sid = attach_result.get("result", {}).get("sessionId")
                                if sid:
                                    # Try to use this session directly
                                    test = self._js_in_session("document.readyState", sid, timeout=3)
                                    if test in ("complete", "interactive", "loading"):
                                        # Got a working CDP session -- use direct mode
                                        self._hcap_session_id = sid
                                        self._use_bridge = False
                                        return True
                                    # Otherwise inject bridge sender into hCaptcha iframe
                                    self._js_in_session(_HCAP_BRIDGE_JS, sid, timeout=4)
                        except Exception:
                            pass
        except Exception:
            pass

        # Wait up to 8s for bridge data to arrive (increased from 5s)
        for _ in range(16):
            bridge = self._bridge_read()
            if bridge and (bridge.get('hasMenu') or bridge.get('hasInput') or bridge.get('question')):
                self._use_bridge = True
                return True
            time.sleep(0.5)

        # Fallback 2: Check if the hCaptcha iframe is at least visible on the page.
        # If so, we can still attempt to solve via CDP coordinates even without
        # direct iframe access. The bridge may fail for CORS reasons but the
        # iframe's position is known.
        ix, iy, iw, ih = self._get_iframe_rect()
        if iw > 200 and ih > 200:
            # Large hCaptcha iframe is visible — use bridge mode with position-based clicks
            self._use_bridge = True
            return True

        return False

    def _bridge_read(self) -> Optional[dict]:
        try:
            raw = self._js("JSON.stringify(window.__hcap_bridge || null)")
            if raw and str(raw) not in ('null', 'None'):
                return json.loads(str(raw))
        except Exception:
            pass
        return None

    def _eval_in_frame(self, expr: str, timeout: int = 6) -> Optional[str]:
        """Run JS inside hCaptcha iframe — auto-attach path."""
        if not self._hcap_session_id:
            return None
        return self._js_in_session(expr, self._hcap_session_id, timeout=timeout)

    def _open_accessibility(self) -> str:
        """Open hCaptcha accessibility text challenge menu."""
        if self._accessibility_input_visible():
            return "ok"

        ix, iy, iw, ih = self._get_iframe_rect()

        for attempt in range(4):
            menu_clicked = False

            if not self._use_bridge and self._hcap_session_id:
                menu_result = self._eval_in_frame("""
                    (function() {
                        // Do NOT include #menu-info / [data-testid='menu-info'] -
                        // that opens the Information popup, not the accessibility menu.
                        var sels = [
                            '[data-testid="menu-opener"]',
                            'button[class*="opener"]',
                            'button[aria-haspopup="true"]',
                            'button[aria-label*="option" i]',
                            'button[aria-label*="hcaptcha" i]',
                            'button[class*="menu"]:not([data-testid="menu-info"]):not(#menu-info)',
                            '[class*="menu-icon"]:not([data-testid="menu-info"]):not(#menu-info)'
                        ];
                        for (var i = 0; i < sels.length; i++) {
                            try {
                                var el = document.querySelector(sels[i]);
                                if (el) {
                                    el.click();
                                    return 'ok:' + (sels[i]).slice(0,30);
                                }
                            } catch(_) {}
                        }
                        return 'no_menu';
                    })()
                """, timeout=4)
                if menu_result and menu_result.startswith('ok'):
                    menu_clicked = True

                if not menu_clicked:
                    coords = self._eval_in_frame("""
                        (function() {
                            var sels = [
                                '[data-testid="menu-opener"]',
                                'button[class*="opener"]',
                                'button[aria-haspopup="true"]',
                                'button[class*="menu"]:not([data-testid="menu-info"]):not(#menu-info)'
                            ];
                            for (var i = 0; i < sels.length; i++) {
                                var el = document.querySelector(sels[i]);
                                if (el) {
                                    var r = el.getBoundingClientRect();
                                    if (r.width > 0) return r.x+','+r.y+','+r.width+','+r.height;
                                }
                            }
                            return '';
                        })()
                    """, timeout=4)
                    if coords and ',' in str(coords):
                        try:
                            p = str(coords).split(',')
                            self._cdp_click(int(float(p[0]) + float(p[2])/2 + ix),
                                            int(float(p[1]) + float(p[3])/2 + iy))
                            menu_clicked = True
                        except Exception:
                            pass

            # Fallback: click by known layout position.
            # Hamburger/menu-opener = BOTTOM-LEFT of challenge iframe (~5% x, 93% y).
            # Top-right is the info (i) button which opens the wrong dialog.
            # Bottom-left avoids the info button (top-right) and the checkbox (top-left).
            if not menu_clicked and iw > 0:
                self._cdp_click(int(ix + iw * 0.05), int(iy + ih * 0.93))
                menu_clicked = True

            if not menu_clicked:
                time.sleep(0.5)
                continue

            # ── Wait for menu items to appear (poll up to 1.5s) ──────────────
            # The menu has a CSS transition -- items are not in the DOM instantly.
            # We MUST wait until [role="menuitem"] elements are visible before
            # trying to click them, otherwise we find nothing and loop forever.
            _menu_ready = False
            for _mw in range(15):
                _has_items = self._eval_in_frame("""
                    (function() {
                        var items = document.querySelectorAll('[role="menuitem"]');
                        for (var i = 0; i < items.length; i++) {
                            var r = items[i].getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) return 'yes';
                        }
                        return 'no';
                    })()
                """, timeout=3)
                if _has_items == 'yes':
                    _menu_ready = True
                    break
                time.sleep(0.1)

            if not _menu_ready:
                # Menu didn't open -- try again
                time.sleep(0.3)
                continue

            # ── Click the Accessibility / Display hCaptcha menu item ──────────
            acc_clicked = False
            if not self._use_bridge and self._hcap_session_id:
                acc_result = self._eval_in_frame("""
                    (function() {
                        var exclude = ['what is hcaptcha', 'cookie','kuki','koekje','galleta','biscuit'];
                        var include = ['display hcaptcha', 'accessibility','accessible',
                                       'text challenge', 'tantangan','herausforderung',
                                       'desafio', 'switch to accessible'];
                        var els = document.querySelectorAll('[role="menuitem"],li[role="option"]');
                        for (var i = 0; i < els.length; i++) {
                            var el = els[i];
                            var r = el.getBoundingClientRect();
                            if (r.width <= 0 || r.height <= 0) continue;
                            if (el.tagName === 'A' && el.href && el.href.indexOf('what-is-hcaptcha') !== -1) continue;
                            var t = (el.textContent || '').toLowerCase().trim();
                            if (exclude.some(function(k){return t.indexOf(k)!==-1;})) continue;
                            if (include.some(function(k){return t.indexOf(k)!==-1;})) {
                                el.click(); return 'ok:'+t.slice(0,20);
                            }
                        }
                        // Fallback: click last visible menuitem that is not excluded
                        var menuitems = Array.from(
                            document.querySelectorAll('[role="menuitem"]')
                        ).filter(function(e){
                            var r=e.getBoundingClientRect();
                            if (r.width<=0 || r.height<=0) return false;
                            if (e.tagName === 'A' && e.href && e.href.indexOf('what-is-hcaptcha') !== -1) return false;
                            var t = (e.textContent||'').toLowerCase();
                            if (exclude.some(function(k){return t.indexOf(k)!==-1;})) return false;
                            return true;
                        });
                        if (menuitems.length > 0) {
                            menuitems[menuitems.length-1].click(); return 'ok_pos';
                        }
                        return 'no_acc';
                    })()
                """, timeout=4)
                if acc_result and acc_result.startswith('ok'):
                    acc_clicked = True

                if not acc_clicked:
                    # Get coords of the accessibility item and CDP-click it
                    acc_coords = self._eval_in_frame("""
                        (function() {
                            var exc=['what is hcaptcha', 'cookie','kuki','koekje'];
                            var inc=['display hcaptcha','accessibility','accessible',
                                     'challenge','text','switch to'];
                            var els=Array.from(document.querySelectorAll('[role="menuitem"],li'));
                            for(var i=0;i<els.length;i++){
                                if (els[i].tagName === 'A' && els[i].href && els[i].href.indexOf('what-is-hcaptcha') !== -1) continue;
                                var t=(els[i].textContent||'').toLowerCase();
                                if(exc.some(function(k){return t.indexOf(k)!==-1;})) continue;
                                if(inc.some(function(k){return t.indexOf(k)!==-1;})){
                                    var r=els[i].getBoundingClientRect();
                                    if(r.width>0&&r.height>0)
                                        return r.x+','+r.y+','+r.width+','+r.height;
                                }
                            }
                            return '';
                        })()
                    """, timeout=4)
                    if acc_coords and ',' in str(acc_coords):
                        try:
                            p = str(acc_coords).split(',')
                            self._cdp_click(int(float(p[0]) + float(p[2])/2 + ix),
                                            int(float(p[1]) + float(p[3])/2 + iy))
                            acc_clicked = True
                        except Exception:
                            pass

            if not acc_clicked:
                # Nothing worked -- skip this attempt, reopen menu next iteration
                time.sleep(0.3)
                continue

            # ── Wait for the accessibility text input to appear ───────────────
            time.sleep(0.3)
            for _w in range(40):
                if self._accessibility_input_visible():
                    return "ok"
                time.sleep(0.2)

            time.sleep(0.3)

        return "no_captcha_input"

    def _accessibility_input_visible(self) -> bool:
        if not self._use_bridge and self._hcap_session_id:
            sel_js = _HCAP_INPUT_SEL_JS
            result = self._eval_in_frame(f"""
                (function() {{
                    var sels = {sel_js};
                    for (var i = 0; i < sels.length; i++) {{
                        var inp = document.querySelector(sels[i]);
                        if (inp && inp.offsetParent !== null) return 'yes';
                    }}
                    return 'no';
                }})()
            """, timeout=4)
            if result is not None:
                return result == 'yes'
        bridge = self._bridge_read()
        if bridge:
            return bool(bridge.get('hasInput'))
        return False

    def _wait_for_prompt(self, timeout: int = 15) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            q = self._read_question()
            if q and len(q) > 3:
                return True
            time.sleep(0.5)
        return False

    def _read_question(self) -> str:
        if not self._use_bridge and self._hcap_session_id:
            raw_text = self._eval_in_frame("""
                (function() {
                    // Get ALL text from the challenge body, not just the prompt element
                    var fullText = document.body ? document.body.innerText : '';
                    return fullText.trim();
                })()
            """, timeout=4)
            if raw_text:
                q = self._extract_question_from_text(str(raw_text))
                if q:
                    return q

        bridge = self._bridge_read()
        if bridge and bridge.get('question'):
            return str(bridge['question']).strip().lower()

        # Fallback: if bridge mode active but no bridge data yet (CORS blocking
        # postMessage), try to re-acquire a CDP session for the hCaptcha iframe
        # and read the question directly
        if self._use_bridge and not self._hcap_session_id:
            try:
                targets_result = self._bconn_send("Target.getTargets", {}, timeout=4)
                if targets_result:
                    for t in targets_result.get("result", {}).get("targetInfos", []):
                        url = (t.get("url") or "").lower()
                        if "hcaptcha" not in url and "newassets" not in url:
                            continue
                        try:
                            attach_result = self._bconn_send("Target.attachToTarget", {
                                "targetId": t.get("targetId"),
                                "flatten": True,
                            }, timeout=4)
                            if attach_result:
                                sid = attach_result.get("result", {}).get("sessionId")
                                if sid:
                                    raw = self._js_in_session(
                                        "document.body ? document.body.innerText : ''",
                                        sid, timeout=4)
                                    q = self._extract_question_from_text(str(raw or ''))
                                    if q:
                                        # Successfully connected -- switch to direct mode
                                        self._hcap_session_id = sid
                                        self._use_bridge = False
                                        return q
                        except Exception:
                            pass
            except Exception:
                pass

        return ""

    @staticmethod
    def _extract_question_from_text(raw: str) -> str:
        """Extract the real question from hCaptcha body.innerText.

        body.innerText looks like:
          "Answer the following question with a single word, number, or phrase.What liquid fills most canned vegetables?   Please try again."

        The instruction is always the first sentence ending with a period.
        The actual question follows immediately after it.
        Noise at the end: "Please try again", "Skip", "EN", emoji, whitespace.
        """
        if not raw or len(raw.strip()) < 5:
            return ""

        text = raw.strip()

        # Strip known instruction prefixes (the blue banner sentence)
        INSTRUCTION_RE = re.compile(
            r'^(?:'
            r'answer the following question[^.]*\.'
            r'|please respond to the following question[^.]*\.'
            r'|please use[^.]*answer[^.]*\.'
            r'|please answer the following question[^.]*\.'
            r'|use a single word[^.]*\.'
            r'|respond with[^.]*\.'
            r'|type[^.]*answer[^.]*\.'
            r'|answer with[^.]*\.'
            r'|from the \d+ words? below[^,\n]*,?\s*'
            r')',
            re.IGNORECASE
        )
        m = INSTRUCTION_RE.match(text)
        if m:
            text = text[m.end():].strip()

        # Strip trailing noise — "Please try again", emoji, button labels, truncated "plea..."
        # Also strip standalone "Please" or "plea" at end (from line-wrapped DOM text)
        TAIL_RE = re.compile(
            r'\s+(plea\w*\s+try\s+again\.?'  # "please try again"
            r'|plea\w*\s+try\.?'             # "please try"
            r'|try\s+again\.?'              # "try again"
            r'|plea\w*$'                    # truncated "please" / "plea" at very end
            r'|\bskip\b|\bnext\b|\bverify\b'
            r'|\bEN\b|\bNL\b|\bDE\b|\bFR\b'
            r'|[\u26a0\u26a1\u2620\u2757\u2755\u203c\ufe0f\u20e3]'
            r').*$',
            re.IGNORECASE | re.UNICODE
        )
        text = TAIL_RE.sub('', text).strip()

        # Remove stray newlines and collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > 3:
            return text.lower()
        return ""

    def _is_solved(self) -> bool:
        # For email_verify: check h-captcha-response filled OR success text on page.
        # Do NOT check URL (/verify is always in the URL on this page).
        # Do NOT check if iframes are gone -- they stay visible even after solve sometimes.
        if self.context == 'email_verify':
            result = self._js("""
                (() => {
                    // Signal 1: captcha response textarea filled (explicit solve token)
                    const ta = document.querySelector('textarea[name="h-captcha-response"]');
                    if (ta && ta.value && ta.value.length > 20) return true;
                    // Signal 2: success text appeared on the verify page
                    const body = (document.body && document.body.innerText || '').toLowerCase();
                    const ok = ['verified', 'email verified', 'you\'re all set', 'success',
                                'verification successful', 'email has been verified'];
                    for (var i = 0; i < ok.length; i++) {
                        if (body.indexOf(ok[i]) !== -1) return true;
                    }
                    // Signal 3: hcaptcha challenge iframe is gone / shrunk (challenge closed)
                    const frames = document.querySelectorAll('iframe[src*="hcaptcha"]');
                    let hasChallenge = false;
                    for (const f of frames) {
                        const r = f.getBoundingClientRect();
                        if (r.height > 200) { hasChallenge = true; break; }
                    }
                    return !hasChallenge && frames.length > 0;
                })()
            """)
            return bool(result)

        result = self._js("""
            (() => {
                const url = window.location.href || '';
                if (url.includes('/channels') || url.includes('/@me') ||
                    url.includes('check-your-email')) return true;
                const ta = document.querySelector('textarea[name="h-captcha-response"]');
                if (ta && ta.value && ta.value.length > 20) return true;
                return false;
            })()
        """)
        return bool(result)

    def _submit_answer(self, answer: str):
        safe = answer.replace("\\", "\\\\").replace("'", "\\'")
        sel_js = _HCAP_INPUT_SEL_JS

        _input_filled = False
        _verify_clicked = False

        # Primary: inject via CDP session
        if not self._use_bridge and self._hcap_session_id:
            fill_result = self._eval_in_frame(f"""
                (function() {{
                    var sels = {sel_js};
                    var inp = null;
                    for (var i = 0; i < sels.length; i++) {{
                        var el = document.querySelector(sels[i]);
                        if (el && el.offsetParent !== null) {{ inp = el; break; }}
                    }}
                    if (!inp) return 'no_input';
                    inp.focus();
                    try {{
                        var ns = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        ns.call(inp, '{safe}');
                    }} catch(e) {{ inp.value = '{safe}'; }}
                    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                    return inp.value === '{safe}' ? 'ok' : 'mismatch';
                }})()
            """, timeout=5)

            if fill_result == 'ok':
                _input_filled = True
            elif fill_result == 'mismatch':
                # Try clearing and re-filling
                self._eval_in_frame(f"""
                    (function() {{
                        var sels = {sel_js};
                        for (var i = 0; i < sels.length; i++) {{
                            var el = document.querySelector(sels[i]);
                            if (el && el.offsetParent !== null) {{
                                el.focus();
                                el.value = '';
                                el.value = '{safe}';
                                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                                return 'ok';
                            }}
                        }}
                        return 'no_input';
                    }})()
                """, timeout=5)
                _input_filled = True

            if _input_filled:
                time.sleep(0.05)
                # Click verify button via CDP offset by iframe position
                btn = self._eval_in_frame("""
                    (function() {
                        var btns = document.querySelectorAll('button,[role="button"]');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').trim().toLowerCase();
                            var r = btns[i].getBoundingClientRect();
                            if (r.width <= 0 || r.height <= 0) continue;
                            if (t.indexOf('verify') !== -1 || t.indexOf('submit') !== -1 ||
                                t.indexOf('check') !== -1 || t.indexOf('next') !== -1) {
                                return r.x+','+r.y+','+r.width+','+r.height;
                            }
                        }
                        return '';
                    })()
                """, timeout=4)
                if btn and ',' in str(btn):
                    ix, iy, _, _ = self._get_iframe_rect()
                    try:
                        p = str(btn).split(',')
                        self._cdp_click(int(float(p[0]) + float(p[2])/2 + ix),
                                        int(float(p[1]) + float(p[3])/2 + iy))
                        _verify_clicked = True
                    except Exception:
                        pass

                # If button click via coords failed, try JS click
                if not _verify_clicked:
                    click_result = self._eval_in_frame("""
                        (function() {
                            var btns = document.querySelectorAll('button,[role="button"]');
                            for (var i = 0; i < btns.length; i++) {
                                var t = (btns[i].innerText || '').trim().toLowerCase();
                                var r = btns[i].getBoundingClientRect();
                                if (r.width <= 0 || r.height <= 0) continue;
                                if (t.indexOf('verify') !== -1 || t.indexOf('submit') !== -1 ||
                                    t.indexOf('check') !== -1 || t.indexOf('next') !== -1) {
                                    btns[i].click();
                                    return 'clicked';
                                }
                            }
                            return 'no_btn';
                        })()
                    """, timeout=4)
                    if click_result == 'clicked':
                        _verify_clicked = True

                if _verify_clicked:
                    return

        # Fallback: type answer via CDP keyboard at the input position,
        # then click verify at approximate position
        ix, iy, iw, ih = self._get_iframe_rect()
        if iw > 0 and not _input_filled:
            # Find the input field position inside the iframe and type via CDP keyboard
            input_coords = None
            if not self._use_bridge and self._hcap_session_id:
                input_coords = self._eval_in_frame(f"""
                    (function() {{
                        var sels = {sel_js};
                        for (var i = 0; i < sels.length; i++) {{
                            var el = document.querySelector(sels[i]);
                            if (el && el.offsetParent !== null) {{
                                var r = el.getBoundingClientRect();
                                return r.x+','+r.y+','+r.width+','+r.height;
                            }}
                        }}
                        return '';
                    }})()
                """, timeout=4)

            if input_coords and ',' in str(input_coords):
                try:
                    p = str(input_coords).split(',')
                    inp_x = int(float(p[0]) + float(p[2])/2 + ix)
                    inp_y = int(float(p[1]) + float(p[3])/2 + iy)
                    # Click inside the input field
                    self._cdp_click(inp_x, inp_y)
                    time.sleep(0.1)
                    # Select all existing text and type new answer
                    try:
                        import truedriver.cdp.input_ as input_cdp
                        # Select all (Ctrl+A)
                        self._run(self._reg._tab.send(input_cdp.dispatch_key_event(
                            type_="keyDown", modifiers=2, key="a", code="KeyA",
                            windows_virtual_key_code=65, native_virtual_key_code=65
                        )))
                        time.sleep(0.02)
                        self._run(self._reg._tab.send(input_cdp.dispatch_key_event(
                            type_="keyUp", modifiers=2, key="a", code="KeyA",
                            windows_virtual_key_code=65, native_virtual_key_code=65
                        )))
                        time.sleep(0.02)
                        # Type the answer character by character
                        for ch in answer:
                            self._run(self._reg._tab.send(input_cdp.dispatch_key_event(
                                type_="keyDown", key=ch, text=ch
                            )))
                            time.sleep(0.02)
                            self._run(self._reg._tab.send(input_cdp.dispatch_key_event(
                                type_="keyUp", key=ch
                            )))
                            time.sleep(0.02)
                        _input_filled = True
                    except Exception:
                        pass
                except Exception:
                    pass

        # Click verify at approximate position (bottom-center of iframe)
        if iw > 0 and not _verify_clicked:
            self._cdp_click(int(ix + iw * 0.5), int(iy + ih * 0.85))

    def _wait_for_change(self, old_question: str, timeout: float = 8) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self._is_solved():
                return True
            q = self._read_question()
            if q and q != old_question and len(q) > 3:
                return True
            time.sleep(0.3)
        return False

    def _has_error(self) -> bool:
        if not self._use_bridge and self._hcap_session_id:
            result = self._eval_in_frame("""
                (function() {
                    var el = document.querySelector(
                        '.error-text,[class*="error"],[class*="fail"],[class*="wrong"]');
                    return (el && (el.innerText||'').trim().length > 0) ? 'yes' : 'no';
                })()
            """, timeout=4)
            if result is not None:
                return result == 'yes'
        return False

    def solve(self) -> float:
        try:
            return self._solve_internal()
        finally:
            if self._hcap_session_id:
                try:
                    self._bconn_send("Target.detachFromTarget", {"sessionId": self._hcap_session_id}, timeout=3)
                except Exception:
                    pass
                self._hcap_session_id = None

    def _solve_internal(self) -> float:
        # For email_verify the challenge frame is already open — use shorter timeout
        _frame_timeout = 10 if self.context == 'email_verify' else 22

        if not self._wait_for_challenge_frame(timeout=_frame_timeout):
            return -2.0

        acc_result = self._open_accessibility()
        if acc_result != "ok":
            return -2.0

        if not self._wait_for_prompt(timeout=15):
            return -1.0

        start_time = time.time()
        last_question = ""
        challenge_count = 0
        run_data: List[Tuple[str, str]] = []
        solve_timeout = 60
        _no_change_streak = 0

        while time.time() - start_time < solve_timeout:
            if self._is_solved():
                # Discord gives exactly 3 challenges
                if challenge_count >= 3:
                    elapsed = time.time() - start_time
                    self._update_kb(run_data, challenge_count, success=True)
                    Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({challenge_count} challenges)"
                    Logger.queue_log(worker_id=self.worker_id)
                    return elapsed
                else:
                    time.sleep(0.5)
                    continue

            question = self._read_question()
            if not question or len(question) < 4:
                if challenge_count > 0:
                    time.sleep(0.5)
                    if self._is_solved():
                        if challenge_count >= 3:
                            elapsed = time.time() - start_time
                            self._update_kb(run_data, challenge_count, success=True)
                            Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s"
                            Logger.queue_log(worker_id=self.worker_id)
                            return elapsed
                time.sleep(0.3)
                continue

            if question == last_question:
                _no_change_streak += 1
                if _no_change_streak > 8:
                    last_question = ""
                    _no_change_streak = 0
                time.sleep(0.2)
                continue

            _no_change_streak = 0
            challenge_count += 1

            kb_answer = self._kb_lookup(question)
            if kb_answer:
                answer = kb_answer
                src = "KB"
            else:
                local_answer = self._local_solve(question)
                if local_answer is not None:
                    answer = local_answer
                    src = "LOCAL"
                else:
                    answer = self._fetch_answer(question)
                    if answer == "ERROR_GROQ_403":
                        return -3.0
                    src = "AI"

            if not answer or answer.strip() == "":
                answer = "no"
                src = "DEFAULT"

            run_data.append((question, answer))
            last_question = question

            self._submit_answer(answer)
            time.sleep(0.3)

            changed = self._wait_for_change(question, timeout=10)
            if not changed:
                if self._is_solved():
                    continue
                if self._has_error():
                    n = self._normalize(question)
                    if n in self.knowledgebase:
                        del self.knowledgebase[n]
                    run_data = [(q, a) for q, a in run_data if q != question]
                    last_question = ""
                    _no_change_streak = 0
                    time.sleep(1)
                else:
                    last_question = ""
                    _no_change_streak = 0

        return -1.0

    def _local_solve(self, question: str) -> Optional[str]:
        q = question.lower().strip()
        m = re.search(r'if it ends with (\d)[,.]?\s+replace that final \d with (\d) in (\d+)', q)
        if m:
            cond, repl, num = m.group(1), m.group(2), m.group(3)
            return (num[:-1] + repl) if num.endswith(cond) else num
        m = re.search(r'replace the last (\d) with (\d) in (\d+)', q)
        if m:
            old, new, num = m.group(1), m.group(2), m.group(3)
            idx = num.rfind(old)
            return (num[:idx] + new + num[idx+1:]) if idx != -1 else num
        m = re.search(r'what is (\d+)\s*([+\-*x×])\s*(\d+)', q)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            if op == '+': return str(a + b)
            if op == '-': return str(a - b)
            if op in ('*', 'x', '×'): return str(a * b)
        m = re.search(r'(\d+)\s*\+\s*(\d+)', q)
        if m: return str(int(m.group(1)) + int(m.group(2)))
        m = re.search(r'(\d+)\s*-\s*(\d+)', q)
        if m: return str(int(m.group(1)) - int(m.group(2)))
        return None

    def _fetch_answer(self, question: str) -> str:
        solver_ai = self.config.get("solver_ai") or {}
        use_cloudflare = solver_ai.get("cloudflare", False)
        use_groq = solver_ai.get("groq", False)
        use_openrouter = solver_ai.get("openrouter", False)

        if not any([use_cloudflare, use_groq, use_openrouter]):
            return "no"

        prompt_text = f"Question: {question}\n\nAnswer ONLY the answer (max 5 words, no punctuation, no explanation):"

        ai_config = self.config.get("ai_api", {})

        if use_cloudflare:
            cf_cfg = ai_config.get("cloudflare", {})
            account_id = cf_cfg.get("account_id", "")
            api_key = cf_cfg.get("api_key", "")
            model = cf_cfg.get("model", "@cf/openai/gpt-oss-120b")
            if account_id and api_key and time.time() >= TruedriverTextSolver._rate_limited_until:
                try:
                    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    resp = requests.post(
                        url=url,
                        headers=headers,
                        json={
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt_text}
                            ]
                        },
                        timeout=20
                    )
                    if resp.status_code == 429:
                        TruedriverTextSolver._rate_limited_until = time.time() + 60
                        Logger.STATUS = f"{MskColor.RED}Cloudflare Rate Limited. Cooling 60s."
                        Logger.queue_log(worker_id=self.worker_id)
                    else:
                        resp.raise_for_status()
                        response_data = resp.json()
                        
                        # Cloudflare wraps OpenAI format in result object
                        if "result" in response_data:
                            result = response_data["result"]
                            if "choices" in result:
                                raw_content = result["choices"][0]["message"]["content"]
                            elif "response" in result:
                                raw_content = result["response"]
                            else:
                                raw_content = ""
                        elif "choices" in response_data:
                            raw_content = response_data["choices"][0]["message"]["content"]
                        else:
                            raw_content = ""
                        
                        if raw_content and raw_content.strip():
                            answer = self._clean_answer(raw_content, question)
                            if answer == "no" and not self._is_yes_no(question):
                                raw_lower = raw_content.lower().strip()
                                for prefix in ["answer: ", "answer:", "-> ", "->", "a: ", "the answer is "]:
                                    if raw_lower.startswith(prefix):
                                        raw_lower = raw_lower[len(prefix):].strip()
                                words = raw_lower.split()
                                if words:
                                    candidate = words[0]
                                    if candidate not in ("no", "yes", "the", "a", "an", "answer", "is", "it"):
                                        answer = candidate
                            if answer and answer != "no":
                                return answer
                except Exception as e:
                    Logger.STATUS = f"{MskColor.RED}Cloudflare Error: {str(e)[:50]}"
                    Logger.queue_log(worker_id=self.worker_id)

        if use_groq:
            if Groq is None:
                pass
            else:
                groq_cfg = ai_config.get("groq", {})
                api_key = groq_cfg.get("api_key", "")
                if api_key and time.time() >= TruedriverTextSolver._rate_limited_until:
                    try:
                        client = Groq(api_key=api_key)
                        model = groq_cfg.get("model", "llama-3.3-70b-versatile")
                        resp = client.chat.completions.create(
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt_text}
                            ],
                            model=model, temperature=0, max_tokens=100,
                            timeout=15
                        )
                        if resp.choices and len(resp.choices) > 0:
                            raw_content = resp.choices[0].message.content
                            if raw_content and raw_content.strip():
                                answer = self._clean_answer(raw_content, question)
                                if answer == "no" and not self._is_yes_no(question):
                                    raw_lower = raw_content.lower().strip()
                                    for prefix in ["answer: ", "answer:", "-> ", "->", "a: ", "the answer is "]:
                                        if raw_lower.startswith(prefix):
                                            raw_lower = raw_lower[len(prefix):].strip()
                                    words = raw_lower.split()
                                    if words:
                                        candidate = words[0]
                                        if candidate not in ("no", "yes", "the", "a", "an", "answer", "is", "it"):
                                            answer = candidate
                                if answer and answer != "no":
                                    return answer
                    except RateLimitError:
                        TruedriverTextSolver._rate_limited_until = time.time() + 60
                        Logger.STATUS = f"{MskColor.RED}Groq Rate Limited. Cooling 60s."
                        Logger.queue_log(worker_id=self.worker_id)
                    except Exception as e:
                        if "403" in str(e):
                            return "ERROR_GROQ_403"
                        Logger.STATUS = f"{MskColor.RED}Groq Error: {str(e)[:50]}"
                        Logger.queue_log(worker_id=self.worker_id)

        if use_openrouter:
            or_cfg = ai_config.get("openrouter", {})
            api_key = or_cfg.get("api_key", "")
            if api_key and time.time() >= TruedriverTextSolver._rate_limited_until:
                model = or_cfg.get("model", "nvidia/nemotron-3-super-120b-a12b:free")
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://msk.software",
                    "X-Title": "FluxMart",
                }
                try:
                    for attempt in range(2):
                        resp = requests.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json={"model": model, "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt_text}
                            ], "temperature": 0, "max_tokens": 100},
                            timeout=15
                        )
                        if resp.status_code == 429:
                            if attempt == 0:
                                ra = resp.headers.get("Retry-After")
                                time.sleep(int(ra) if ra and ra.isdigit() else 5 + random.random() * 5)
                                continue
                            TruedriverTextSolver._rate_limited_until = time.time() + 60
                            Logger.STATUS = f"{MskColor.RED}OpenRouter Rate Limited"
                            Logger.queue_log(worker_id=self.worker_id)
                            break
                        resp.raise_for_status()
                        resp_json = resp.json()
                        if resp_json.get("choices") and len(resp_json["choices"]) > 0:
                            raw_content = resp_json["choices"][0]["message"]["content"]
                            if raw_content and raw_content.strip():
                                answer = self._clean_answer(raw_content, question)
                                if answer == "no" and not self._is_yes_no(question):
                                    raw_lower = raw_content.lower().strip()
                                    for prefix in ["answer: ", "answer:", "-> ", "->", "a: ", "the answer is "]:
                                        if raw_lower.startswith(prefix):
                                            raw_lower = raw_lower[len(prefix):].strip()
                                    words = raw_lower.split()
                                    if words:
                                        candidate = words[0]
                                        if candidate not in ("no", "yes", "the", "a", "an", "answer", "is", "it"):
                                            answer = candidate
                                if answer and answer != "no":
                                    return answer
                        break
                except Exception as e:
                    Logger.STATUS = f"{MskColor.RED}OpenRouter Error: {str(e)[:50]}"
                    Logger.queue_log(worker_id=self.worker_id)

        return "no"


    def _clean_answer(self, raw: str, question: str) -> str:
        answer = (raw or "").strip()
        for c in '"\'.!?*():;,`\\/':
            answer = answer.replace(c, '')
        answer = answer.strip()
        for prefix in ["answer: ", "answer:", "-> ", "->", "a: ", "the answer is "]:
            if answer.lower().startswith(prefix):
                answer = answer[len(prefix):].strip()
        answer = answer.split('\n')[0].strip()
        words = answer.split()
        if len(words) > 5:
            answer = ' '.join(words[:4])
        answer = answer.lower()
        if self._is_yes_no(question):
            first = answer.split()[0] if answer.split() else answer
            if first in ("yes", "true", "correct"): return "yes"
            if first in ("no", "false", "incorrect", "nope"): return "no"
            # For yes/no where answer doesn't match, return empty so we try next provider
            return ""
        return answer or ""

    def _is_yes_no(self, question: str) -> bool:
        q = question.lower().strip()
        if re.search(r'\d{4,}', q):
            return False
        free = ["which ","what ","how ","name ","who ","where ","when ","why ",
                "use the ","position ","list ","give ","write ","describe ",
                "how many ","how much ","change ","replace ","modify ","remove ",
                "delete ","add ","insert ","swap ","if ","while "]
        for m in free:
            if m.strip() in q:
                return False
        return True

    def _update_kb(self, run_data: List[Tuple[str, str]], count: int, success: bool = False):
        if not run_data or not success:
            return
        if count <= 4:
            for q, a in run_data:
                self.knowledgebase[self._normalize(q)] = a
            self._save_knowledgebase()
        elif count <= 6:
            changed = False
            for q, _ in run_data:
                n = self._normalize(q)
                if n in self.knowledgebase:
                    del self.knowledgebase[n]
                    changed = True
            if changed:
                self._save_knowledgebase()
