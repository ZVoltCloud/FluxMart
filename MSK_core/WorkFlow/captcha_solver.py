import json
import os
import sys
import time
import random
from pathlib import Path
from typing import Optional, List, Tuple, Dict

import requests
from playwright.sync_api import Page, Frame

try:
    from groq import Groq, RateLimitError
except ImportError:
    Groq = None
    RateLimitError = Exception

from ..MskColors.color import MskColor
from ..Utils.logger import Logger
from ..Utils.utils import JsInjection, Config, _is_frozen, get_base_path



class CaptchaSolver:
    _openai_rate_limited_until: float = 0.0
    _openai_error_logged: bool = False

    def __init__(self, page: Page, worker_id: int) -> None:
        self.page: Page = page
        self.kb_path: str = "MSK_core/Assets/knowledgebase.json"
        self.knowledgebase: Dict[str, str] = self._load_knowledgebase()
        self.js: JsInjection = JsInjection()
        self.js.setup_js(page)
        self.worker_id = worker_id
    
    @property
    def config(self) -> Dict:
        """Always read fresh config from file to ensure latest values."""
        return Config.config

    def _get_kb_path(self) -> str:
        """Get the knowledgebase path, handling frozen executable."""
        if _is_frozen():
            return os.path.join(get_base_path(), "MSK_core", "Assets", "knowledgebase.json")
        return self.kb_path

    def _load_knowledgebase(self) -> Dict[str, str]:
        kb_path = self._get_kb_path()
        if os.path.exists(kb_path):
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    @staticmethod
    def _normalize_question(q: str) -> str:
        """Normalize a question for KB lookup -- strips whitespace, punctuation, articles."""
        q = q.strip().lower()
        for char in ['?', '!', '.', ',', ';', ':']:
            q = q.strip(char)
        q = ' '.join(q.split())
        return q

    def _kb_lookup(self, question: str) -> Optional[str]:
        """Look up a question in the knowledgebase with fuzzy matching."""
        normalized = self._normalize_question(question)
        if normalized in self.knowledgebase:
            return self.knowledgebase[normalized]
        if question in self.knowledgebase:
            return self.knowledgebase[question]
        stripped = normalized.replace('?', '').replace('!', '').replace('.', '').strip()
        for kb_q, kb_a in list(self.knowledgebase.items()):
            kb_stripped = self._normalize_question(kb_q).replace('?', '').replace('!', '').replace('.', '').strip()
            if stripped == kb_stripped:
                return kb_a
        return None

    def _save_knowledgebase(self, data: Dict[str, str]) -> None:
        kb_path = self._get_kb_path()
        try:
            os.makedirs(os.path.dirname(kb_path), exist_ok=True)
            with open(kb_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            pass

    def _get_js_path(self) -> Path:
        """Get the JS utilities path, handling frozen executable."""
        if _is_frozen():
            return Path(get_base_path()) / "MSK_core" / "JS" / "utils.js"
        return Path(__file__).parent.parent / "JS" / "utils.js"

    def _inject_js_to_frame(self, frame: Frame) -> None:
        """Inject the JS utilities directly into the hCaptcha iframe context."""
        js_path = self._get_js_path()
        if js_path.exists():
            js_code = js_path.read_text(encoding="utf-8")
            try:
                frame.evaluate(f"(function(){{ {js_code} }})()")
            except Exception as e:
                Logger.STATUS = f"{MskColor.YELLOW}JS injection warning: {e}"
                Logger.queue_log(worker_id=self.worker_id)

    def inject_accessibility_challenge(self, frame: Frame) -> str:
        """Open accessibility/text challenge.
        Tries fast Playwright-native locator approach first ('Display hCaptcha'),
        then falls back to JS injection ('Accessibility Challenge').
        Returns:
            'ok': accessibility challenge opened and input found
            'no_menu': menu button not found
            'no_accessibility_option': accessibility menu item not found
            'no_captcha_input': accessibility opened but input not found
            'cookie_not_set': accessibility cookie not set in browser
            'cookie_retrieval_no_input': clicked retrieve but no input appeared
            'error': exception during injection
        """
        try:
            frame.get_by_role("button", name="About hCaptcha", exact=False).click(timeout=5000)
            try:
                frame.get_by_role("menuitem", name="Display hCaptcha", exact=False).click(timeout=3000)
            except Exception:
                frame.get_by_role("menuitem", name="Accessibility Challenge", exact=False).click(timeout=3000)
            frame.wait_for_selector('input[name="captcha"]', timeout=10000)
            return "ok"
        except Exception:
            pass

        self._inject_js_to_frame(frame)
        try:
            result = self.js.open_accessibility_challenge(frame)
            if isinstance(result, dict):
                if result.get("success"):
                    return "ok"
                return result.get("reason", "error")
            return "ok"
        except Exception:
            return "error"

    def is_captcha_solved(self, page: Page) -> bool:
        """Check if the hCaptcha is already solved using multiple signals."""
        try:
            for iframe in page.query_selector_all("iframe"):
                src = iframe.get_attribute("src") or ""
                if "hcaptcha.com" not in src:
                    continue
                frame = iframe.content_frame()
                if not frame:
                    continue
                try:
                    # A detached frame means the iframe was removed from the DOM.
                    # This can happen when Discord navigates away OR when an error
                    # removes the widget without solving it -- do NOT treat this as
                    # a solved state; let the caller re-check the page URL instead.
                    if frame.is_detached():
                        return False
                    checkbox = frame.query_selector("div#checkbox")
                    if checkbox and checkbox.get_attribute("aria-checked") == "true":
                        return True
                    anchor = frame.query_selector("#anchor")
                    if anchor:
                        classes = anchor.get_attribute("class") or ""
                        if "success" in classes.lower() or "checked" in classes.lower():
                            return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def find_hcaptcha_frame(self, page: Page, timeout: int = 30) -> Optional[Frame]:
        start_time: float = time.time()

        while time.time() - start_time < timeout:
            if self.is_captcha_solved(page):
                return None

            try:
                iframes = page.query_selector_all("iframe")
            except Exception:
                return None

            for iframe in iframes:
                try:
                    src = iframe.get_attribute("src")
                except Exception:
                    continue
                if not src or "hcaptcha.com" not in src:
                    continue

                frame: Optional[Frame] = iframe.content_frame()
                if not frame:
                    continue

                try:
                    checkbox = frame.query_selector("div#checkbox")
                    if checkbox and checkbox.get_attribute("aria-checked") == "false":
                        checkbox.click()
                except Exception as e:
                    Logger.STATUS = f"{MskColor.YELLOW}Error clicking checkbox: {e}"
                    Logger.queue_log(worker_id=self.worker_id)

                try:
                    if frame.wait_for_selector("#menu-info", timeout=2000):
                        return frame
                except Exception:
                    continue

            time.sleep(0.5)

        if self.is_captcha_solved(page):
            return None

        return None

    def _is_image_captcha(self, frame: Frame) -> bool:
        """Check if the current captcha is a visual/image challenge."""
        try:
            self._inject_js_to_frame(frame)
            result = frame.evaluate("window.utils && window.utils.isImageCaptcha()")
            return bool(result)
        except Exception:
            return False

    def wait_for_captcha_solved(self, frame: Frame, timeout: int = 120) -> float:
        """Wait for the user to manually solve the captcha."""
        start_time: float = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if frame.is_detached():
                    elapsed = time.time() - start_time
                    Logger.STATUS = f"{MskColor.GREEN}Captcha Solved Manually in {elapsed:.2f}s"
                    Logger.queue_log(worker_id=self.worker_id)
                    return elapsed
                
                checkbox = frame.query_selector("div#checkbox")
                if checkbox:
                    aria_checked = checkbox.get_attribute("aria-checked")
                    if aria_checked == "true":
                        elapsed = time.time() - start_time
                        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved Manually in {elapsed:.2f}s"
                        Logger.queue_log(worker_id=self.worker_id)
                        return elapsed
                
                anchor = frame.query_selector("#anchor")
                if anchor:
                    classes = anchor.get_attribute("class") or ""
                    if "success" in classes.lower() or "checked" in classes.lower():
                        elapsed = time.time() - start_time
                        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved Manually in {elapsed:.2f}s"
                        Logger.queue_log(worker_id=self.worker_id)
                        return elapsed
            except Exception:
                pass
            
            time.sleep(0.3)
        
        Logger.STATUS = f"{MskColor.RED}Manual captcha solve timeout"
        Logger.queue_log(worker_id=self.worker_id)
        return time.time() - start_time

    def refresh_captcha(self, frame: Frame) -> None:
        """Try to close/refresh the captcha challenge so a new one loads."""
        try:
            self._inject_js_to_frame(frame)
            result = frame.evaluate("window.utils && window.utils.refreshCaptchaChallenge()")
            if isinstance(result, dict) and result.get("success"):
                time.sleep(2)
                if result.get("method") == "close_button":
                    checkbox = frame.query_selector("div#checkbox")
                    if checkbox:
                        checkbox.click()
                        time.sleep(2)
                return
        except Exception:
            pass
        
        try:
            close_btn = frame.query_selector('.refresh.button, button.refresh, [aria-label="Get a new challenge"], [aria-label="Refresh challenge"]')
            if close_btn:
                close_btn.click()
                time.sleep(2)
                return
            
            close_btn = frame.query_selector('.close-button, [aria-label="Close"]')
            if close_btn:
                close_btn.click()
                time.sleep(1)
                checkbox = frame.query_selector("div#checkbox")
                if checkbox:
                    checkbox.click()
                    time.sleep(2)
                return
        except Exception:
            pass

    def solve_accessibility_hcaptcha(self, frame: Frame) -> float:
        """Solve captcha using accessibility challenge.
        Returns:
            > 0: solve time in seconds (success)
            -1.0: auto-solve failed, should retry
            -2.0: accessibility unavailable, caller should refresh and retry
        """
        try:
            frame.wait_for_selector("#menu-info", timeout=10_000)
        except Exception:
            Logger.STATUS = f"{MskColor.YELLOW}Captcha menu not found, refreshing..."
            Logger.queue_log(worker_id=self.worker_id)
            self.refresh_captcha(frame)
            return -1.0

        acc_result = self.inject_accessibility_challenge(frame)
        if acc_result == "no_accessibility_option" or acc_result == "no_menu":
            return -2.0
        if acc_result == "cookie_not_set" or acc_result == "cookie_retrieval_no_input":
            Logger.STATUS = f"{MskColor.RED}hCaptcha accessibility cookie not set -- paste your cookie in Settings > Captcha"
            Logger.queue_log(worker_id=self.worker_id)
            return -2.0
        if acc_result != "ok":
            Logger.STATUS = f"{MskColor.YELLOW}Accessibility input not found ({acc_result}), retrying..."
            Logger.queue_log(worker_id=self.worker_id)
            self.refresh_captcha(frame)
            return -1.0

        prompt_loaded = False
        prompt_wait_start = time.time()
        while time.time() - prompt_wait_start < 15:
            try:
                prompt_el = frame.query_selector('h2.prompt-text span, [id^="prompt-text"]')
                if prompt_el:
                    text = prompt_el.inner_text().strip()
                    if len(text) > 3:
                        prompt_loaded = True
                        break
            except Exception:
                pass
            time.sleep(0.5)

        if not prompt_loaded:
            Logger.STATUS = f"{MskColor.YELLOW}Accessibility prompt not loaded, refreshing..."
            Logger.queue_log(worker_id=self.worker_id)
            self.refresh_captcha(frame)
            return -1.0

        Logger.STATUS = f"{MskColor.GREEN}Captcha Found"
        Logger.queue_log(worker_id=self.worker_id)

        start_time: float = time.time()
        Logger.STATUS = f"{MskColor.PRIMARY}Solving Captcha"
        Logger.queue_log(worker_id=self.worker_id)

        current_run: List[Tuple[str, str]] = []
        last_question: str = ""
        challenge_count: int = 0

        solve_timeout = 60
        loop_start = time.time()
        
        while True:
            if time.time() - loop_start > solve_timeout:
                Logger.STATUS = f"{MskColor.YELLOW}Auto-solve timed out, refreshing..."
                Logger.queue_log(worker_id=self.worker_id)
                self.refresh_captcha(frame)
                return -1.0

            if frame.is_detached():
                self._smart_update_knowledgebase(current_run, challenge_count)
                elapsed = time.time() - start_time
                Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({challenge_count} challenges)"
                Logger.queue_log(worker_id=self.worker_id)
                return elapsed

            try:
                checkbox = frame.query_selector("div#checkbox")
                if checkbox and checkbox.get_attribute("aria-checked") == "true":
                    self._smart_update_knowledgebase(current_run, challenge_count)
                    elapsed = time.time() - start_time
                    Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({challenge_count} challenges)"
                    Logger.queue_log(worker_id=self.worker_id)
                    return elapsed
            except Exception:
                pass

            question_elem = frame.query_selector('[id^="prompt-text"]')
            if not question_elem:
                time.sleep(0.1)
                continue

            question: str = question_elem.inner_text().strip().lower()
            
            if question == last_question:
                time.sleep(0.3)
                continue

            if len(question) < 4:
                time.sleep(0.2)
                continue

            challenge_count += 1

            kb_answer = self._kb_lookup(question)
            if kb_answer:
                answer = kb_answer
            else:
                answer = self._fetch_answer(question)
                if answer == "ERROR_GROQ_403":
                    return -3.0
            
            current_run.append((question, answer))
            last_question = question

            try:
                time.sleep(0.3)
                self.js.answer_accessibility_question(frame, answer)
                
                question_changed = self._wait_for_question_change(frame, question, timeout=8)
                
                if not question_changed:
                    if frame.is_detached():
                        continue
                    try:
                        checkbox = frame.query_selector("div#checkbox")
                        if checkbox and checkbox.get_attribute("aria-checked") == "true":
                            continue
                    except:
                        pass
                    
                    try:
                        error_el = frame.query_selector('.error-text, [class*="error"], [class*="fail"]')
                        if error_el:
                            error_text = error_el.inner_text().strip()
                            if error_text:
                                if question in self.knowledgebase:
                                    del self.knowledgebase[question]
                                current_run = [(q, a) for q, a in current_run if q != question]
                                last_question = ""
                                time.sleep(1)
                                continue
                    except:
                        pass
            
            except Exception:
                break

        self._smart_update_knowledgebase(current_run, challenge_count)
        
        if not frame.is_detached():
            try:
                checkbox = frame.query_selector("div#checkbox")
                if checkbox and checkbox.get_attribute("aria-checked") != "true":
                    Logger.STATUS = f"{MskColor.YELLOW}Captcha not solved, refreshing..."
                    Logger.queue_log(worker_id=self.worker_id)
                    self.refresh_captcha(frame)
                    return -1.0
            except Exception:
                pass
        
        elapsed: float = time.time() - start_time
        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved in {elapsed:.2f}s ({challenge_count} challenges)"
        Logger.queue_log(worker_id=self.worker_id)
        return elapsed

    def _wait_for_question_change(self, frame: Frame, old_question: str, timeout: float = 8) -> bool:
        """Wait for the question text to change after submitting an answer.
        Returns True if question changed, False if timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if frame.is_detached():
                    return True
                
                checkbox = frame.query_selector("div#checkbox")
                if checkbox and checkbox.get_attribute("aria-checked") == "true":
                    return True
                
                question_elem = frame.query_selector('[id^="prompt-text"]')
                if question_elem:
                    new_text = question_elem.inner_text().strip().lower()
                    if new_text != old_question and len(new_text) > 3:
                        return True
            except:
                pass
            time.sleep(0.3)
        return False

    def _is_yes_no_question(self, question: str) -> bool:
        """Detect if the question is a yes/no type.
        
        INVERTED LOGIC: Instead of trying to detect yes/no patterns (too many to catch),
        we detect FREE-TEXT question words. If none found, it's yes/no.
        """
        q = question.lower().strip()

        import re
        if re.search(r'\d{4,}', q):
            return False

        free_text_markers = [
            "which ", "what ", "how ", "name ",
            "who ", "where ", "when ", "why ",
            "use the ", "position ",
            "list ", "give ", "write ", "describe ",
            "how many ", "how much ",
            "change ", "replace ", "modify ", "alter ", "convert ",
            "remove ", "delete ", "add ", "insert ", "swap ",
            "ubah ", "ganti ", "hapus ", "tambah ", "tukar ",
            "saat ", "jika ", "ketika ", "apabila ", "bila ",
            "if ", "when ", "while ",
        ]
        
        for marker in free_text_markers:
            if q.startswith(marker):
                return False

        for marker in free_text_markers:
            if marker.strip() in q:
                return False

        mid_markers = [
            "what digit", "what character",
            "what word", "what name", "what country",
            "what city", "what continent", "what language",
            "how many legs", "how many wheels",
            "last character", "last digit", "last letter",
            "first character", "first digit", "first letter",
            "karakter terakhir", "digit terakhir", "angka terakhir",
        ]
        for marker in mid_markers:
            if marker in q:
                return False
        
        return True

    UNIVERSAL_SYSTEM_PROMPT = (
        "You are an elite hCaptcha accessibility text challenge solver. "
        "CRITICAL SYSTEM RULES: "
        "1. Questions may be in ANY language (English, Indonesian, Malay, etc.) -- always understand and solve them correctly. "
        "2. If the question is a true Yes/No question (e.g. 'Is a cat an animal?'), answer ONLY 'yes' or 'no'. "
        "3. Provide ONLY the answer. No punctuation, no periods, no introductory phrases, maximum 5 words. "
        "4. NUMERIC LOGIC: If the question asks for a count or quantity, provide the DIGIT (e.g., '7'). "
        "5. COMPARISONS: If asked 'Which is bigger/faster/heavier', output only the name of the winning object. "
        "6. HYPOTHETICALS: Resolve the logical state. (e.g., 'If ice melts, what is it?' -> 'water'). "
        "7. CATEGORIZATION: If asked to identify a type (e.g., 'Is a hammer a tool or food?'), output the category only. "
        "8. SPATIAL/TEMPORAL: Answer questions about days, months, or locations with the specific noun. "
        "9. MULTIPLE CHOICE: If the question provides options, reply with ONLY the number or letter of the correct option. "
        "10. CHARACTER/DIGIT MANIPULATION: If the question asks you to change, replace, or modify a specific character/digit/letter in a string or number, output ONLY the final modified string -- nothing else. "
        "EXAMPLES FOR CALIBRATION: "
        "Input: 'How many wheels on a car?' Output: '4' "
        "Input: 'Is the sun cold?' Output: 'no' "
        "Input: 'Which is larger: a grape or a house?' Output: 'house' "
        "Input: 'If you mix red and yellow, what do you get?' Output: 'orange' "
        "Input: 'What day comes after Monday?' Output: 'tuesday' "
        "Input: 'Is a cat an animal?' Output: 'yes' "
        "Input: '1. Apple 2. Car -- Which is a fruit?' Output: '1' "
        "Input: 'When the last character is 2, change only that last character to 3 in 829532' Output: '829533' "
        "Input: 'Saat karakter terakhir adalah 2, ubah hanya karakter terakhir itu menjadi 3 pada 829532' Output: '829533' "
        "Input: 'Replace the first letter with B in Apple' Output: 'bpple' "
        "STRICT ADHERENCE: Any explanation or conversational filler will result in failure. Answer now."
    )

    def _build_prompt(self, question: str) -> str:
        """Build the user prompt for the AI solver."""
        return f"Question: {question}\n\nAnswer:"

    YES_WORDS = {
        "yes", "true", "correct",
    }
    NO_WORDS = {
        "no", "false", "incorrect",
    }

    def _clean_answer(self, raw: str, question: str) -> str:
        """Clean and validate the AI response."""
        answer = (raw or "").strip().lower()
        for char in ['"', "'", '.', '!', '?', '*', '(', ')', ':', ';', ',', '`', '\\', '/']:
            answer = answer.replace(char, '')
        answer = answer.strip()

        prefixes_to_strip = [
            "answer: ", "answer:",
            "-> ", "->", "a: ", "the answer is ",
        ]
        for prefix in prefixes_to_strip:
            if answer.startswith(prefix):
                answer = answer[len(prefix):].strip()

        if self._is_yes_no_question(question):
            a = answer.split()[0] if answer.split() else answer
            if a in self.YES_WORDS:
                return "yes"
            if a in self.NO_WORDS:
                return "no"
            for yes_word in self.YES_WORDS:
                if answer.startswith(yes_word):
                    return "yes"
            for no_word in self.NO_WORDS:
                if answer.startswith(no_word):
                    return "no"

        answer = answer.split('\n')[0].strip()
        articles = [
            'the ', 'a ', 'an ',
        ]
        for article in articles:
            if answer.startswith(article):
                answer = answer[len(article):]
        words = answer.split()
        if len(words) > 4:
            answer = ' '.join(words[:3])

        return answer if answer else "no"

    def _fetch_answer(self, question: str) -> str:
        solver_ai = self.config.get("solver_ai") or {}
        use_cloudflare = solver_ai.get("cloudflare", False)
        use_groq = solver_ai.get("groq", False)
        use_openrouter = solver_ai.get("openrouter", False)

        active_count = sum([use_cloudflare, use_groq, use_openrouter])
        if active_count > 1:
            Logger.STATUS = f"{MskColor.RED}Invalid AI configuration: multiple solvers are enabled. Please enable only one solver AI."
            Logger.queue_log(worker_id=self.worker_id)
            return "no"

        prompt_text = self._build_prompt(question)

        ai_config = self.config.get("ai_api", {})

        cloudflare_config = ai_config.get("cloudflare", {})
        groq_config = ai_config.get("groq", {})
        openrouter_config = ai_config.get("openrouter", {})

        if use_cloudflare:
            account_id = cloudflare_config.get("account_id", "")
            api_key = cloudflare_config.get("api_key", "")
            model = cloudflare_config.get("model", "@cf/openai/gpt-oss-120b")
            
            if not account_id or not api_key:
                Logger.STATUS = f"{MskColor.YELLOW}No Cloudflare credentials configured, using default answer"
                Logger.queue_log(worker_id=self.worker_id)
                return "no"
            
            if time.time() < CaptchaSolver._openai_rate_limited_until:
                return "no"

            api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            
            try:
                response = requests.post(
                    url=api_url,
                    headers=headers,
                    json={
                        "messages": [
                            {"role": "system", "content": self.UNIVERSAL_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt_text}
                        ]
                    },
                    timeout=20
                )
                
                if response.status_code == 429:
                    CaptchaSolver._openai_rate_limited_until = time.time() + 60
                    if not CaptchaSolver._openai_error_logged:
                        Logger.STATUS = f"{MskColor.RED}Cloudflare Rate Limited (429). Cooling down for 60s."
                        Logger.queue_log(worker_id=self.worker_id)
                        CaptchaSolver._openai_error_logged = True
                    return "no"
                
                response.raise_for_status()
                CaptchaSolver._openai_error_logged = False
                response_data = response.json()
                
                # Cloudflare wraps OpenAI format in result object
                if "result" in response_data:
                    result = response_data["result"]
                    if "choices" in result:
                        raw_answer = result["choices"][0]["message"]["content"]
                    elif "response" in result:
                        raw_answer = result["response"]
                    else:
                        raw_answer = ""
                elif "choices" in response_data:
                    raw_answer = response_data["choices"][0]["message"]["content"]
                else:
                    raw_answer = ""
                
                return self._clean_answer(raw_answer, question)
            except Exception as e:
                if not CaptchaSolver._openai_error_logged:
                    Logger.STATUS = f"{MskColor.RED}Cloudflare Error: {str(e)[:60]}"
                    Logger.queue_log(worker_id=self.worker_id)
                    CaptchaSolver._openai_error_logged = True
                return "no"

        elif use_groq:
            api_key = groq_config.get("api_key", "")
            if not api_key:
                Logger.STATUS = f"{MskColor.YELLOW}No Groq API key configured, using default answer"
                Logger.queue_log(worker_id=self.worker_id)
                return "no"
            
            if time.time() < CaptchaSolver._openai_rate_limited_until:
                return "no"

            client = Groq(api_key=api_key)
            model = groq_config.get("model", "openai/gpt-oss-120b")
            
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": self.UNIVERSAL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt_text}
                    ],
                    model=model,
                    temperature=0,
                    max_tokens=20
                )
                CaptchaSolver._openai_error_logged = False
                raw_answer = chat_completion.choices[0].message.content
                return self._clean_answer(raw_answer, question)
            except RateLimitError:
                CaptchaSolver._openai_rate_limited_until = time.time() + 60
                if not CaptchaSolver._openai_error_logged:
                    Logger.STATUS = f"{MskColor.RED}Groq Rate Limited (429). Cooling down for 60s."
                    Logger.queue_log(worker_id=self.worker_id)
                    CaptchaSolver._openai_error_logged = True
                return "no"
            except Exception as e:
                if "403" in str(e) or "Access denied" in str(e):
                    if not CaptchaSolver._openai_error_logged:
                        Logger.STATUS = f"{MskColor.RED}Groq Error 403 (VPN Blocked)"
                        Logger.queue_log(worker_id=self.worker_id)
                        CaptchaSolver._openai_error_logged = True
                    return "ERROR_GROQ_403"
                    
                if not CaptchaSolver._openai_error_logged:
                    Logger.STATUS = f"{MskColor.RED}Groq Error: {str(e)[:60]}"
                    Logger.queue_log(worker_id=self.worker_id)
                    CaptchaSolver._openai_error_logged = True
                return "no"

        elif use_openrouter:
            api_key = openrouter_config.get("api_key", "")
            if not api_key:
                Logger.STATUS = f"{MskColor.YELLOW}No OpenRouter API key configured, using default answer"
                Logger.queue_log(worker_id=self.worker_id)
                return "no"
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            model = openrouter_config.get("model", "liquid/lfm3-1.7b:free")
        else:
            Logger.STATUS = f"{MskColor.YELLOW}No AI solver enabled, using default answer"
            Logger.queue_log(worker_id=self.worker_id)
            return "no"

        if time.time() < CaptchaSolver._openai_rate_limited_until:
            return "no"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if use_openrouter:
            headers["HTTP-Referer"] = "https://msk.software"
            headers["X-Title"] = "FluxMart"

        try:
            for attempt in range(2):
                response = requests.post(
                    url=api_url,
                    headers=headers,
                    data=json.dumps({
                        "model": model,
                        "messages": [
                            {"role": "system", "content": self.UNIVERSAL_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt_text}
                        ],
                        "temperature": 0,
                        "max_tokens": 20
                    }),
                    timeout=20
                )
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after and retry_after.isdigit() else (5 + random.random() * 5)
                    
                    if attempt == 0:
                        time.sleep(wait_time)
                        continue
                    else:
                        CaptchaSolver._openai_rate_limited_until = time.time() + 60
                        if not CaptchaSolver._openai_error_logged:
                            Logger.STATUS = f"{MskColor.RED}AI API rate limited (429). Cooling down for 60s."
                            Logger.queue_log(worker_id=self.worker_id)
                            CaptchaSolver._openai_error_logged = True
                        return "no"

                response.raise_for_status()
                CaptchaSolver._openai_error_logged = False
                raw_answer = response.json()["choices"][0]["message"]["content"]
                return self._clean_answer(raw_answer, question)
        except Exception as e:
            if not CaptchaSolver._openai_error_logged:
                Logger.STATUS = f"{MskColor.RED}AI API Error: {str(e)[:60]}"
                Logger.queue_log(worker_id=self.worker_id)
                CaptchaSolver._openai_error_logged = True
            return "no"

    def _smart_update_knowledgebase(self, run_data: List[Tuple[str, str]], challenge_count: int) -> None:
        """Only persist KB entries when we're confident the answers were correct.
        
        hCaptcha accessibility requires ~3 correct answers in a row.
        - ≤ 4 challenges: all answers were likely correct → save to KB
        - 5-6 challenges: some were wrong, don't know which → don't save, purge suspect entries
        - 7+ challenges: heavily wrong → purge all run entries from KB
        """
        if not run_data:
            return
        
        if challenge_count <= 4:
            for question, answer in run_data:
                normalized = self._normalize_question(question)
                self.knowledgebase[normalized] = answer
            self._save_knowledgebase(self.knowledgebase)
        elif challenge_count <= 6:
            changed = False
            for question, answer in run_data:
                normalized = self._normalize_question(question)
                if normalized in self.knowledgebase:
                    del self.knowledgebase[normalized]
                    changed = True
            if changed:
                self._save_knowledgebase(self.knowledgebase)
                Logger.STATUS = f"{MskColor.YELLOW}Purged {challenge_count}-challenge KB entries (possible wrong cache)"
                Logger.queue_log(worker_id=self.worker_id)
        else:
            changed = False
            for question, answer in run_data:
                normalized = self._normalize_question(question)
                if normalized in self.knowledgebase:
                    del self.knowledgebase[normalized]
                    changed = True
            if changed:
                self._save_knowledgebase(self.knowledgebase)
                Logger.STATUS = f"{MskColor.YELLOW}Purged all KB entries from {challenge_count}-challenge run"
                Logger.queue_log(worker_id=self.worker_id)
