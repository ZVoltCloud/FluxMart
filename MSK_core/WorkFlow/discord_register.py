import sys
import os
import re
import time
from typing import Optional, Dict, Tuple, Any
from contextlib import redirect_stdout, redirect_stderr
import io

# ── Use canonical environment detection ──
from ..Utils.env import is_frozen as _is_frozen_local, get_base_path as _find_base_path_local, init_browserforge_path


def init_browserforge_for_exe():
    """Initialize browserforge data path for frozen executable."""
    init_browserforge_path()


init_browserforge_for_exe()


from camoufox.sync_api import Camoufox
from browserforge.fingerprints import Screen

from ..MskColors.color import MskColor
from ..Utils.utils import Utils, JsInjection, Config, get_base_path, get_resource_path
from ..Utils.proxy_manager import ProxyManager
from .captcha_solver import CaptchaSolver
from ..Helper.mail import MskMailApi, MailVerify, BrowserMailVerify
from ..Helper.huminazer import DiscordHuminazer
from ..Utils.logger import Logger

try:
    from ..Utils.fivesim import PhoneVerifier
    FIVESIM_AVAILABLE = True
except ImportError:
    FIVESIM_AVAILABLE = False
    PhoneVerifier = None

try:
    from ..Utils.onlinesim import OnlineSimVerifier
    ONLINESIM_AVAILABLE = True
except ImportError:
    ONLINESIM_AVAILABLE = False
    OnlineSimVerifier = None


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
    "92": "Pakistan", "880": "Bangladesh", "213": "Algeria", "212": "Morocco",
    "216": "Tunisia", "218": "Libya", "249": "Sudan", "251": "Ethiopia",
    "233": "Ghana", "225": "Ivory Coast", "221": "Senegal", "250": "Rwanda",
    "256": "Uganda", "255": "Tanzania", "260": "Zambia", "263": "Zimbabwe",
    "94": "Sri Lanka", "977": "Nepal", "95": "Myanmar", "93": "Afghanistan",
    "992": "Tajikistan", "993": "Turkmenistan", "994": "Azerbaijan", "995": "Georgia",
    "996": "Kyrgyzstan", "998": "Uzbekistan", "370": "Lithuania", "371": "Latvia",
    "372": "Estonia", "373": "Moldova", "374": "Armenia", "375": "Belarus",
    "381": "Serbia", "382": "Montenegro", "385": "Croatia", "386": "Slovenia",
    "387": "Bosnia and Herzegovina", "389": "North Macedonia", "352": "Luxembourg",
    "356": "Malta", "357": "Cyprus", "354": "Iceland", "298": "Faroe Islands",
    "502": "Guatemala", "503": "El Salvador", "504": "Honduras", "505": "Nicaragua",
    "506": "Costa Rica", "507": "Panama", "53": "Cuba", "509": "Haiti",
    "1809": "Dominican Republic", "1829": "Dominican Republic", "1849": "Dominican Republic",
    "1767": "Dominica", "1473": "Grenada", "1868": "Trinidad and Tobago",
    "1876": "Jamaica", "1441": "Bermuda", "592": "Guyana", "597": "Suriname",
    "595": "Paraguay", "598": "Uruguay",    "591": "Bolivia",
    "855": "Cambodia", "856": "Laos", "974": "Qatar", "965": "Kuwait",
    "968": "Oman", "962": "Jordan", "961": "Lebanon", "964": "Iraq",
    "973": "Bahrain", "975": "Bhutan", "960": "Maldives",
}

FIVESIM_TO_DISCORD_COUNTRY = {
    "england": "United Kingdom",
    "usa": "United States",
    "czech": "Czech Republic",
    "dominicana": "Dominican Republic",
    "antiguaandbarbuda": "Antigua and Barbuda",
    "bosnia": "Bosnia and Herzegovina",
    "burkinafaso": "Burkina Faso",
    "capeverde": "Cape Verde",
    "centralafrican_republic": "Central African Republic",
    "congo": "Congo",
    "costarica": "Costa Rica",
    "easttimor": "East Timor",
    "equatorialguinea": "Equatorial Guinea",
    "frenchguiana": "French Guiana",
    "guineabissau": "Guinea-Bissau",
    "hongkong": "Hong Kong",
    "ivorycoast": "Ivory Coast",
    "newcaledonia": "New Caledonia",
    "northmacedonia": "North Macedonia",
    "papuanewguinea": "Papua New Guinea",
    "puertorico": "Puerto Rico",
    "reunion": "Reunion",
    "saintkittsandnevis": "Saint Kitts and Nevis",
    "saintlucia": "Saint Lucia",
    "saintvincentandgrenadines": "Saint Vincent and the Grenadines",
    "saudiarabia": "Saudi Arabia",
    "sierraleone": "Sierra Leone",
    "southafrica": "South Africa",
    "southkorea": "South Korea",
    "srilanka": "Sri Lanka",
    "trinidad": "Trinidad and Tobago",
    "uae": "United Arab Emirates",
    "uk": "United Kingdom",
}


def _strip_country_code(phone: str):
    clean = phone.lstrip("+").strip()
    prefixes = sorted(COUNTRY_CODES.keys(), key=len, reverse=True)
    for prefix in prefixes:
        if clean.startswith(prefix):
            local_number = clean[len(prefix):]
            return prefix, local_number, COUNTRY_CODES[prefix]
    return "", clean, ""


class DiscordRegister:
    def __init__(self) -> None:
        self.proxy_manager: ProxyManager = ProxyManager("data/input/proxies.txt")
        self.password: str = Utils.random_password()
        self.day, self.month, self.year = Utils.random_birthday()
        self.status: str = ""
        self.js_injector: JsInjection = JsInjection()
        self.last_result: dict = {"token": "", "email": "", "status": "", "humanized": False, "phone_verified": False, "email_verified": False}

    def _create_email(self, worker_id: int) -> tuple[Optional[str], str]:
        """Generate email based on selected provider.
        
        Supports: CyberTemp, Mailcow, Zeus, Hotmail007, Lution.
        Features: Fast Mails (pre-buying pool), Wait for Restock (infinite retry), Multi Buy (provider fallback).
        """
        email_providers = self.config.get("email_providers", {})
        email = None
        email_address = ""
        email_password = self.password

        fast_mails = self.config.get("fast_mails", {})
        if fast_mails.get("enabled", False):
            try:
                from .email_pool import EmailPool
                pool = EmailPool.instance()
                account = pool.get_email(worker_id=worker_id, timeout=120)
                if account:
                    self._zeus_refresh_token = account.get('refresh_token', '')
                    self._zeus_client_id = account.get('client_id', '')
                    return account['email'], account['password']
                else:
                    Logger.STATUS = f"{MskColor.RED}Email pool exhausted"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Email pool error: {str(e)[:60]}"
                Logger.queue_log(worker_id=worker_id)

        restock_wait = self.config.get("restock_wait", False)
        
        if email_providers.get("cybertemp", {}).get("enabled", False):
            cybertemp_key = email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", "")
            domain = email_providers.get("cybertemp", {}).get("domain", "random")
            if not domain or domain == "random":
                try:
                    from ..Helper.mail import MskMailApi as _MailApi
                    _api_tmp = _MailApi(api_key=cybertemp_key)
                    _domains = _api_tmp.get_domains(domain_type="discord")
                    domain = random.choice(_domains) if _domains else Utils.get_domain()
                except Exception:
                    domain = Utils.get_domain()
            username = Utils.sanitize_email_local(Utils.random_string())
            email_address = f"{username}@{domain}"
            try:
                from ..Helper.mail import MskMailApi
                email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)
                Logger.STATUS = f"{MskColor.PRIMARY}CyberTemp email created: {email}"
                Logger.queue_log(worker_id=worker_id)
            except Exception as mail_err:
                Logger.STATUS = f"{MskColor.RED}CyberTemp email creation failed: {str(mail_err)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                email = email_address
        
        elif email_providers.get("mailcow", {}).get("enabled", False):
            mc = email_providers.get("mailcow", {})
            host_url = mc.get("host_url", "")
            if host_url and not host_url.startswith("http"): host_url = f"https://{host_url}"
            api_key = mc.get("api_key", "")
            domain = mc.get("domain", "").strip()
            
            if not domain:
                Logger.STATUS = f"{MskColor.RED}Mailcow domain not configured."
                Logger.queue_log(worker_id=worker_id)
                return None, email_password
            
            try:
                from ..Helper.mail import MailcowApi
                mailcow_api = MailcowApi(host_url=host_url, api_key=api_key)
                username = Utils.sanitize_email_local(Utils.random_string())
                email_address = f"{username}@{domain}"
                email = mailcow_api.create_account(email=email_address, password=email_password)
                if email:
                    Logger.STATUS = f"{MskColor.PRIMARY}Mailcow email created: {email}"
                    Logger.queue_log(worker_id=worker_id)
                else:
                    email = email_address
            except Exception as mail_err:
                Logger.STATUS = f"{MskColor.RED}Mailcow error: {str(mail_err)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                email = email_address
        
        elif email_providers.get("duckmail", {}).get("enabled", False):
            dm = email_providers.get("duckmail", {})
            dm_key = dm.get("api_key", "")
            domain = dm.get("domain", "").strip()
            try:
                from ..Helper.mail import DuckMailApi
                import random as _random
                duck_api = DuckMailApi(api_key=dm_key)
                if not domain:
                    domains = duck_api.get_domains() or []
                    domain = _random.choice(domains) if domains else ""
                if not domain:
                    Logger.STATUS = f"{MskColor.RED}DuckMail: no domain available"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password
                username = Utils.sanitize_email_local(Utils.random_string())
                email_address = f"{username}@{domain}"
                email = duck_api.create_account(email=email_address, password=email_password)
                Logger.STATUS = f"{MskColor.PRIMARY}DuckMail email created: {email}"
                Logger.queue_log(worker_id=worker_id)
            except Exception as mail_err:
                Logger.STATUS = f"{MskColor.RED}DuckMail error: {str(mail_err)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                email = email_address

        elif email_providers.get("zeus", {}).get("enabled", False):
            zeus_config = email_providers.get("zeus", {})
            from ..Helper.mail import ZeusApi
            zeus_api = ZeusApi(api_key=zeus_config.get("api_key", ""), account_type=zeus_config.get("account_type", "HOTMAIL"))
            while True:
                if getattr(getattr(self, 'controller', None), 'should_stop', False):
                    return None, email_password
                try:
                    account_data = zeus_api.create_account()
                    if account_data:
                        email = account_data['email']
                        email_password = account_data['password']
                        Logger.STATUS = f"{MskColor.PRIMARY}Zeus account purchased: {email}"
                        Logger.queue_log(worker_id=worker_id)
                        self._zeus_refresh_token = account_data.get('refresh_token', '')
                        self._zeus_client_id = account_data.get('client_id', '')
                        break
                    elif not restock_wait:
                        return None, email_password
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}Zeus no stock, waiting for restock..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                except Exception as mail_err:
                    err_str = str(mail_err).lower()
                    is_stock = any(kw in err_str for kw in ['insufficient', 'stock', 'quantity'])
                    if is_stock and restock_wait:
                        Logger.STATUS = f"{MskColor.YELLOW}Zeus no stock, retrying..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                        continue
                    elif is_stock:
                        Logger.STATUS = f"{MskColor.RED}Zeus no stock"
                    else:
                        Logger.STATUS = f"{MskColor.RED}Zeus error: {str(mail_err)[:60]}"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password
        
        elif email_providers.get("hotmail007", {}).get("enabled", False):
            h007_config = email_providers.get("hotmail007", {})
            from ..Helper.mail import Hotmail007Api
            h007_api = Hotmail007Api(api_key=h007_config.get("api_key", ""), mail_type=h007_config.get("mail_type", "hotmail"))
            while True:
                if getattr(getattr(self, 'controller', None), 'should_stop', False):
                    return None, email_password
                try:
                    account_data = h007_api.create_account()
                    if account_data:
                        email = account_data['email']
                        email_password = account_data['password']
                        self._zeus_refresh_token = account_data.get('refresh_token', '')
                        self._zeus_client_id = account_data.get('client_id', '')
                        Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007 account purchased: {email}"
                        Logger.queue_log(worker_id=worker_id)
                        break
                    elif not restock_wait:
                        return None, email_password
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}Hotmail007 no stock, waiting for restock..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                except Exception as mail_err:
                    err_str = str(mail_err).lower()
                    is_stock = any(kw in err_str for kw in ['insufficient', 'stock', 'quantity'])
                    if is_stock and restock_wait:
                        Logger.STATUS = f"{MskColor.YELLOW}Hotmail007 no stock, retrying..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                        continue
                    elif is_stock:
                        Logger.STATUS = f"{MskColor.RED}Hotmail007 no stock"
                    else:
                        Logger.STATUS = f"{MskColor.RED}Hotmail007 error: {str(mail_err)[:60]}"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password
        
        elif email_providers.get("lution", {}).get("enabled", False):
            lution_config = email_providers.get("lution", {})
            from ..Helper.mail import LutionApi
            lution_api = LutionApi(api_key=lution_config.get("api_key", ""), category=lution_config.get("account_type", "hotmail"))
            while True:
                if getattr(getattr(self, 'controller', None), 'should_stop', False):
                    return None, email_password
                try:
                    account_data = lution_api.create_account()
                    if account_data:
                        email = account_data['email']
                        email_password = account_data['password']
                        self._zeus_refresh_token = account_data.get('refresh_token', '')
                        self._zeus_client_id = account_data.get('client_id', '')
                        Logger.STATUS = f"{MskColor.PRIMARY}Lution account purchased: {email}"
                        Logger.queue_log(worker_id=worker_id)
                        break
                    elif not restock_wait:
                        return None, email_password
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}Lution no stock, waiting for restock..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                except Exception as mail_err:
                    err_str = str(mail_err).lower()
                    is_stock = any(kw in err_str for kw in ['stock', 'quantity'])
                    if is_stock and restock_wait:
                        Logger.STATUS = f"{MskColor.YELLOW}Lution no stock, retrying..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(2)
                        continue
                    elif is_stock:
                        Logger.STATUS = f"{MskColor.RED}Lution no stock"
                    else:
                        Logger.STATUS = f"{MskColor.RED}Lution error: {str(mail_err)[:60]}"
                    Logger.queue_log(worker_id=worker_id)
                    return None, email_password

        else:
            cybertemp_key = self.config.get("cybertemp_api_key", "")
            domain = self.config.get("email_providers", {}).get("cybertemp", {}).get("domain", "random")
            if not domain or domain == "random":
                try:
                    from ..Helper.mail import MskMailApi as _MailApi2
                    _api_tmp2 = _MailApi2(api_key=cybertemp_key)
                    _domains2 = _api_tmp2.get_domains(domain_type="discord")
                    domain = random.choice(_domains2) if _domains2 else Utils.get_domain()
                except Exception:
                    domain = Utils.get_domain()
            username = Utils.sanitize_email_local(Utils.random_string())
            email_address = f"{username}@{domain}"
            try:
                from ..Helper.mail import MskMailApi
                email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)
            except Exception as e:
                Logger.STATUS = f"{MskColor.YELLOW}CyberTemp fallback error: {str(e)[:60]}"
                Logger.queue_log(worker_id=worker_id)
                email = email_address

        if not email:
            email = email_address if email_address else f"{Utils.random_string()}@{Utils.get_domain()}"
        
        return email, email_password

    def _select_country_and_enter_phone(self, page, phone_input, phone_formatted: str, worker_id: int, manual_country_name: Optional[str] = None):
        country_code, local_number, country_name = _strip_country_code(phone_formatted)
        
        if manual_country_name:
            country_name = manual_country_name

        if country_name:
            opened = False
            Logger.STATUS = f"{MskColor.PRIMARY}Filling country: {country_name}"
            Logger.queue_log(worker_id=worker_id)

            try:
                opened = page.evaluate('''() => {
                    // Find the country selector trigger -- it has a chevron/arrow SVG
                    const triggers = document.querySelectorAll('div, button');
                    for (const el of triggers) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 50 || rect.height < 20 || rect.width > 300) continue;
                        if (!el.offsetParent) continue;
                        const hasSvg = el.querySelector('svg');
                        if (!hasSvg) continue;
                        
                        // Check for common trigger attributes or structure
                        if (el.getAttribute('role') === 'button' || el.getAttribute('aria-haspopup') === 'listbox' || el.innerText.includes('+')) {
                            el.click();
                            return true;
                        }
                    }
                    // Fallback: click any element that looks like a country prefix display
                    const prefixes = document.querySelectorAll('[class*="countryCode" i], [class*="prefix" i]');
                    for (const el of prefixes) {
                        if (el.offsetParent) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if opened:
                    time.sleep(0.8)
            except:
                pass

            try:
                page.evaluate('''(targetCountry) => {
                    // Start from the end of the DOM to hit the modal portals first, avoiding global search bars
                    const inputs = Array.from(document.querySelectorAll('input')).reverse();
                    for (const inp of inputs) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width > 30 && rect.width < 300 && inp.offsetParent) {
                            const name = (inp.getAttribute('name') || '').toLowerCase();
                            const placeholder = (inp.getAttribute('placeholder') || '').toLowerCase();
                            if (name === 'phone' || placeholder.includes('phone')) continue;
                            
                            inp.focus();
                            inp.value = targetCountry;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                }''', country_name)
                time.sleep(1.0)

                selected = page.evaluate('''(targetCountry) => {
                    const candidates = document.querySelectorAll('[role="option"], [class*="option" i], [class*="item" i], [class*="result" i]');
                    for (const opt of candidates) {
                        const text = opt.innerText.trim().toLowerCase();
                        if (text.includes(targetCountry.toLowerCase())) {
                            opt.scrollIntoView({ block: "center" });
                            opt.click();
                            return true;
                        }
                    }
                    // Fallback: search all visible elements for exact country name match
                    const allEls = document.querySelectorAll('div, span, li');
                    for (const el of allEls) {
                        if (el.children.length > 5) continue;
                        const text = el.innerText.trim().toLowerCase();
                        if (text === targetCountry.toLowerCase()) {
                            el.scrollIntoView({ block: "center" });
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }''', country_name)

                if opened and not selected:
                    try:
                        page.click('body', position={'x': 10, 'y': 10}, force=True)
                        time.sleep(0.3)
                    except:
                        pass
            except:
                pass

            if not selected:
                try:
                    page.fill('div[class*="layer" i] input, div[role="dialog"] input', country_name)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(0.5)
                except:
                    pass

            time.sleep(0.3)
        
        if not local_number:
            local_number = phone_formatted.lstrip("+").strip()

        try:
            phone_input.click()
            time.sleep(0.2)
            phone_input.fill("")
            time.sleep(0.2)
            phone_input.type(local_number, delay=30)
        except:
            phone_input.fill(local_number)

    def _solve_hcaptcha_if_present(self, page, worker_id: int, timeout: int = 5) -> bool:
        solver = CaptchaSolver(page, worker_id)
        # If captcha is already solved before we even start, return True immediately
        if solver.is_captcha_solved(page):
            return True
        hcaptcha_frame = solver.find_hcaptcha_frame(page, timeout=timeout)
        if hcaptcha_frame is None:
            # find_hcaptcha_frame returns None for both 'already solved' and 'timed out (not found)'
            return solver.is_captcha_solved(page)
        if hcaptcha_frame:
            auto_solve = self.config.get("auto_solver_captcha", True)
            if auto_solve:
                return self._solve_text_based(solver, hcaptcha_frame, page, worker_id, timeout)
            else:
                return self._solve_manual(solver, hcaptcha_frame, worker_id)
        return False

    def _solve_text_based(self, solver, hcaptcha_frame, page, worker_id: int, timeout: int = 5) -> bool:
        """Solve captcha using text-based accessibility challenge."""
        Logger.STATUS = f"{MskColor.YELLOW}hCaptcha detected, solving..."
        Logger.queue_log(worker_id=worker_id)
        max_retries = 3
        solved = False
        for attempt in range(max_retries):
            try:
                result = solver.solve_accessibility_hcaptcha(hcaptcha_frame)
                if result > 0:
                    solved = True
                    break
                elif result == -3.0:
                    raise ConnectionError("VPN_BLOCKED_GROQ")
                elif result == -2.0:
                    # Accessibility challenge unavailable; refresh and re-check
                    solver.refresh_captcha(hcaptcha_frame)
                    time.sleep(2)
                    # Check if captcha was solved during refresh
                    if solver.is_captcha_solved(page):
                        solved = True
                        break
                    hcaptcha_frame = solver.find_hcaptcha_frame(page, timeout=timeout)
                    if not hcaptcha_frame:
                        # Frame gone -- captcha either solved or navigated away
                        solved = solver.is_captcha_solved(page)
                        break
                elif result < 0:
                    time.sleep(2)
                    if solver.is_captcha_solved(page):
                        solved = True
                        break
                    hcaptcha_frame = solver.find_hcaptcha_frame(page, timeout=timeout)
                    if not hcaptcha_frame:
                        solved = solver.is_captcha_solved(page)
                        break
            except Exception as e:
                if "VPN_BLOCKED" in str(e):
                    raise e
                Logger.STATUS = f"{MskColor.RED}Captcha solve failed: {str(e)[:40]}"
                Logger.queue_log(worker_id=worker_id)
                return False
        if solved:
            time.sleep(2)
        return solved

    def _solve_manual(self, solver, hcaptcha_frame, worker_id: int) -> bool:
        """Wait for user to manually solve captcha."""
        Logger.STATUS = f"{MskColor.YELLOW}hCaptcha detected, waiting for manual solve..."
        Logger.queue_log(worker_id=worker_id)
        solver.wait_for_captcha_solved(hcaptcha_frame, timeout=120)
        time.sleep(2)
        return True

    def _check_phone_verification_screen(self, page, worker_id: int) -> bool:
        try:
            page_text = ""
            try:
                body = page.query_selector("body")
                if body:
                    page_text = body.inner_text().lower()
            except:
                pass

            must_verify_indicators = [
                "verification required",
                "verify your account to continue",
                "confirm your identity",
                "we need to confirm your identity",
            ]
            if any(ind in page_text for ind in must_verify_indicators) and "verify by phone" in page_text:
                return True

            text_indicators = [
                "enter a phone number",
                "verify your phone",
                "phone verification",
                "verify by phone",
                "verify with phone",
                "sms verification",
            ]
            text_match = any(indicator in page_text for indicator in text_indicators)

            phone_button_selectors = [
                'button:has-text("Verify by Phone")',
                'a:has-text("Verify by Phone")',
                'div[role="button"]:has-text("Verify by Phone")',
                'button:has-text("Verify with Phone")',
                'a:has-text("Verify with Phone")',
                'button:has-text("Verify by SMS")',
                'a:has-text("Verify by SMS")',
                '[class*="button" i]:has-text("Verify by Phone")',
                'button[aria-label*="phone" i]',
                'a[aria-label*="phone" i]',
            ]

            for selector in phone_button_selectors:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        return True
                except:
                    continue

            element_selectors = [
                'input[type="tel"]',
                '[class*="phoneVerification" i]',
                '[class*="phone-verification" i]',
                '[class*="phoneCollect" i]',
                'h3:has-text("Enter a Phone Number")',
                'h2:has-text("Enter a Phone Number")',
                'h1:has-text("Verification Required")',
                'h2:has-text("Verification Required")',
                'h3:has-text("Verification Required")',
                '[class*="phoneModal" i]',
                '[class*="verifyPhone" i]',
                '[class*="verificationRequired" i]',
            ]

            for selector in element_selectors:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        return True
                except:
                    continue

            if text_match:
                return True

            return False
        except:
            return False

    def _find_phone_button(self, page):
        button_selectors = [
            'button:has-text("Verify by Phone")',
            'a:has-text("Verify by Phone")',
            'div[role="button"]:has-text("Verify by Phone")',
            '[class*="button" i]:has-text("Verify by Phone")',
            'button:has-text("Verify with Phone")',
            'a:has-text("Verify with Phone")',
            'button:has-text("Verify by SMS")',
            'a:has-text("Verify by SMS")',
            'button:has-text("Phone")',
            'a:has-text("Phone")',
            'div[role="button"]:has-text("Phone")',
            'button[aria-label*="phone" i]',
            'a[aria-label*="phone" i]',
        ]

        for selector in button_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    return el
            except:
                continue

        try:
            all_links = page.query_selector_all('a')
            for link in all_links:
                try:
                    link_text = link.inner_text().lower()
                    if "verify by phone" in link_text or "verify with phone" in link_text:
                        if link.is_visible():
                            return link
                except:
                    continue
        except:
            pass

        return None

    def _find_phone_input(self, page):
        input_selectors = [
            'input[type="tel"]',
            'input[name="phone"]',
            'input[placeholder*="phone" i]',
            'input[placeholder*="number" i]',
            'input[aria-label*="phone" i]',
            'input[class*="phone" i]',
            'input[autocomplete="tel"]',
        ]

        for selector in input_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    return el
            except:
                continue
        return None

    def _find_submit_button(self, page, *texts):
        for text in texts:
            try:
                el = page.query_selector(f'button:has-text("{text}")')
                if el and el.is_visible():
                    return el
            except:
                continue

        fallback_selectors = [
            'button[type="submit"]',
            'div[role="button"][class*="submit" i]',
            'button[class*="submit" i]',
        ]
        for selector in fallback_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    return el
            except:
                continue
        return None

    def _find_code_input(self, page):
        code_selectors = [
            'input[name="code"]',
            'input[placeholder*="code" i]',
            'input[placeholder*="verification" i]',
            'input[aria-label*="code" i]',
            'input[autocomplete="one-time-code"]',
        ]

        for selector in code_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    return el
            except:
                continue

        try:
            inputs = page.query_selector_all('input[type="text"], input[type="number"], input[type="tel"]')
            for inp in inputs:
                try:
                    if inp.is_visible():
                        placeholder = inp.get_attribute("placeholder") or ""
                        name = inp.get_attribute("name") or ""
                        if any(kw in (placeholder + name).lower() for kw in ["code", "verif", "otp", "sms"]):
                            return inp
                except:
                    continue
        except:
            pass
        return None

    def _find_code_inputs_multi(self, page):
        """Find Discord's 6 individual digit input boxes for phone verification code.
        Returns a list of input elements (one per digit), or empty list if not found."""
        try:
            inputs = page.evaluate('''() => {
                // Look for small single-character inputs grouped together
                const allInputs = document.querySelectorAll('input');
                const candidates = [];
                for (const inp of allInputs) {
                    const rect = inp.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (!inp.offsetParent) continue;
                    const maxLen = inp.getAttribute('maxlength');
                    const inputMode = inp.getAttribute('inputmode');
                    const ariaLabel = (inp.getAttribute('aria-label') || '').toLowerCase();
                    // Discord code inputs: maxlength=1, inputmode=numeric, or small width inputs
                    if (maxLen === '1' || inputMode === 'numeric' || ariaLabel.includes('digit')) {
                        candidates.push({
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            left: rect.left
                        });
                    }
                }
                return candidates.length;
            }''')

            if inputs and inputs >= 4:
                digit_inputs = page.query_selector_all('input[maxlength="1"], input[inputmode="numeric"]')
                visible = []
                for inp in digit_inputs:
                    try:
                        if inp.is_visible():
                            visible.append(inp)
                    except:
                        continue
                if len(visible) >= 4:
                    return visible

            all_inputs = page.query_selector_all('input')
            small_inputs = []
            for inp in all_inputs:
                try:
                    if not inp.is_visible():
                        continue
                    box = inp.bounding_box()
                    if not box:
                        continue
                    if 15 <= box['width'] <= 80 and 20 <= box['height'] <= 80:
                        small_inputs.append((inp, box))
                except:
                    continue

            if len(small_inputs) >= 4:
                avg_top = sum(b['y'] for _, b in small_inputs) / len(small_inputs)
                same_row = [(inp, b) for inp, b in small_inputs if abs(b['y'] - avg_top) < 30]
                if len(same_row) >= 4:
                    same_row.sort(key=lambda x: x[1]['x'])
                    return [inp for inp, _ in same_row]
        except:
            pass
        return []

    def _fill_code_digit_by_digit(self, page, code_inputs, code, worker_id):
        """Fill verification code digit by digit into individual input boxes.
        Discord auto-advances focus and auto-submits when all digits are filled."""
        try:
            code_inputs[0].click()
            time.sleep(0.3)

            for i, digit in enumerate(code):
                if i >= len(code_inputs):
                    break
                page.keyboard.type(digit, delay=40)
                time.sleep(0.15)

            time.sleep(2)
            return True
        except Exception:
            try:
                for i, digit in enumerate(code):
                    if i >= len(code_inputs):
                        break
                    code_inputs[i].click()
                    time.sleep(0.1)
                    page.keyboard.type(digit, delay=50)
                    time.sleep(0.1)
                time.sleep(2)
                return True
            except:
                return False

    def _handle_phone_verification_browser(self, page, worker_id: int, email: str, proxy: Optional[Dict]) -> Tuple[bool, str]:
        fivesim_config = self.config.get("fivesim", {})
        onlinesim_config = self.config.get("onlinesim", {})
        
        provider_name = ""
        phone_verifier = None
        country = "any"
        operator = "any"
        
        if fivesim_config.get("enabled", False):
            if not FIVESIM_AVAILABLE or not PhoneVerifier:
                return False, "5sim wrapper not available"
            provider_name = "5sim"
            api_key = fivesim_config.get("api_key", "")
            if not api_key:
                Logger.STATUS = f"{MskColor.YELLOW}5sim API key missing. Skipping."
                Logger.queue_log(worker_id=worker_id)
                return False, "Missing 5sim info"
            number_limit = fivesim_config.get("number_limit", 10)
            country = fivesim_config.get("country", "any")
            operator = fivesim_config.get("operator", "any")
            phone_verifier = PhoneVerifier(api_key, number_limit, country, operator)
        elif onlinesim_config.get("enabled", False):
            if not ONLINESIM_AVAILABLE or not OnlineSimVerifier:
                return False, "OnlineSim wrapper not available"
            provider_name = "OnlineSim"
            api_key = onlinesim_config.get("api_key", "")
            if not api_key:
                Logger.STATUS = f"{MskColor.YELLOW}OnlineSim API key missing. Skipping."
                Logger.queue_log(worker_id=worker_id)
                return False, "Missing OnlineSim info"
            number_limit = onlinesim_config.get("number_limit", 10)
            country = onlinesim_config.get("country", "7")
            operator = "any"
            phone_verifier = OnlineSimVerifier(api_key, number_limit, country, operator)
        else:
            return False, "User did not select an option"

        try:
            if not phone_verifier.can_use_number():
                Logger.STATUS = f"{MskColor.YELLOW}{provider_name} balance low or limit reached. Skipping."
                Logger.queue_log(worker_id=worker_id)
                return False, "Balance limit reached"
        except Exception:
            return False, "API checks failed"

        Logger.STATUS = f"{MskColor.PRIMARY}Verifying phone number..."
        Logger.queue_log(worker_id=worker_id)

        button_clicked = page.evaluate('''() => {
            // Helper to check if element text matches phone verification patterns
            const isPhoneButton = (el) => {
                const text = el.innerText ? el.innerText.trim().toLowerCase() : "";
                if (!text) return false;
                
                // Specific phrases
                if (text === "verify by phone" || text === "verify with phone") return true;
                
                // General match: must contain "verify" and "phone" or "sms"
                if (text.includes("verify") && (text.includes("phone") || text.includes("sms"))) return true;
                
                // Single word match
                if (text === "phone" || text === "sms") return true;
                
                return false;
            };

            // 1. Check logical elements
            const candidates = document.querySelectorAll('button, a, div[role="button"]');
            for (const el of candidates) {
                if (isPhoneButton(el)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        el.scrollIntoView({ block: "center" });
                        el.click();
                        return true;
                    }
                }
            }
            
            // 2. Search for any visible element with specific text if step 1 failed
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.children.length === 0 && isPhoneButton(el)) {
                    el.click();
                    return true;
                }
            }

            return false;
        }''')

        if not button_clicked:
            verify_btn = self._find_phone_button(page)
            if verify_btn:
                try:
                    verify_btn.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    verify_btn.click()
                    time.sleep(3)
                except Exception:
                    try:
                        verify_btn.evaluate("el => el.click()")
                        time.sleep(3)
                    except:
                        pass
        else:
            time.sleep(3)
        for attempt in range(5):
            phone_input = self._find_phone_input(page)
            if phone_input:
                break
            time.sleep(1)

        if not phone_input:
            return False, "Form inputs not found"

        number_data = phone_verifier.api.buy_number(country=country, operator=operator)
        if not number_data:
            return False, "Could not acquire number"

        order_id = number_data["id"]
        phone = number_data["phone"]

        phone_formatted = phone if phone.startswith("+") else f"+{phone}"
        Logger.STATUS = f"{MskColor.PRIMARY}Phone number received: {phone_formatted[:7]}***"
        Logger.queue_log(worker_id=worker_id)

        try:
            target_country_name = None
            if country and country != "any":
                target_country_name = FIVESIM_TO_DISCORD_COUNTRY.get(country.lower())
                if not target_country_name:
                    target_country_name = country.capitalize()

            self._select_country_and_enter_phone(page, phone_input, phone_formatted, worker_id, manual_country_name=target_country_name)
            time.sleep(0.5)

            page.evaluate('''() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    const btnText = btn.innerText.trim();
                    if (btnText === 'Send') {
                        btn.scrollIntoView({ block: "center" });
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            time.sleep(2)

            for _hcap_retry in range(3):
                if self._solve_hcaptcha_if_present(page, worker_id, timeout=5):
                    break
                time.sleep(2)

            page_text = ""
            try:
                body = page.query_selector("body")
                if body:
                    page_text = body.inner_text().lower()
            except:
                pass

            error_indicators = [
                "invalid phone",
                "phone number is invalid",
                "unable to send",
                "try again",
                "this phone number",
                "already been used",
                "cannot use this",
            ]
            if any(err in page_text for err in error_indicators):
                phone_verifier.api.cancel_order(order_id)
                return False, "Carrier disabled/banned"

            code = phone_verifier.api.get_sms(order_id, timeout=600)
            if not code:
                phone_verifier.api.cancel_order(order_id)
                return False, "Timeout waiting for SMS"


            if len(code) == 6 and code.isdigit():
                verification_code = code
            else:
                match = re.search(r'\b(\d{6})\b', code)
                if match:
                    verification_code = match.group(1)
                else:
                    match = re.search(r'(\d{4,8})', code)
                    if match:
                        verification_code = match.group(1)
                    else:
                        phone_verifier.api.cancel_order(order_id)
                        return False, "Could not parse SMS"

            Logger.STATUS = f"{MskColor.PRIMARY}Code: {verification_code}"
            Logger.queue_log(worker_id=worker_id)

            code_filled = False
            for attempt in range(8):
                code_inputs_multi = self._find_code_inputs_multi(page)
                if code_inputs_multi:
                    code_filled = self._fill_code_digit_by_digit(page, code_inputs_multi, verification_code, worker_id)
                    break
                code_input = self._find_code_input(page)
                if code_input:
                    try:
                        code_input.click()
                        time.sleep(0.3)
                        code_input.fill("")
                        time.sleep(0.3)
                        code_input.type(verification_code, delay=50)
                    except:
                        code_input.fill(verification_code)
                    code_filled = True
                    time.sleep(1)

                    submit_btn = self._find_submit_button(page, "Verify", "Submit", "Confirm")
                    if submit_btn:
                        try:
                            submit_btn.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            submit_btn.click()
                        except:
                            try:
                                submit_btn.evaluate("el => el.click()")
                            except:
                                pass
                    else:
                        try:
                            code_input.press("Enter")
                        except:
                            pass
                    time.sleep(2)
                    break
                time.sleep(1)

            if code_filled:

                time.sleep(2)
                page.evaluate('''(password) => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    for (const inp of inputs) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        inp.focus();
                        inp.value = password;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }''', self.password)
                time.sleep(0.5)

                page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        const btnText = btn.innerText.trim();
                        if (btnText === 'Confirm') {
                            btn.scrollIntoView({ block: "center" });
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                time.sleep(3)

                if self._check_phone_verification_screen(page, worker_id):
                    phone_verifier.api.cancel_order(order_id)
                    return False, "Failed at password confirmation"

                phone_verifier._save_number(phone, email, "browser_verify")
                phone_verifier.api.finish_order(order_id)

                Logger.STATUS = f"{MskColor.GREEN}Phone verified"
                Logger.queue_log(worker_id=worker_id)
                return True, ""
            else:
                _login_t_retries = 0
                while _login_t_retries < 15:
                    try:
                        token = self.js_injector.wait_for_discord_token(page=page)
                        if token: break
                    except Exception as e:
                        if "Function not found" in str(e) or "context was destroyed" in str(e).lower() or "target closed" in str(e).lower():
                            self.js_injector._injected_context_ids.discard(id(page))
                            try:
                                self.js_injector.setup_js(page)
                            except:
                                pass
                    _login_t_retries += 1
                    if not token: time.sleep(2)
                
                if token:
                    api_success = self._verify_phone_via_api(token, phone_formatted, verification_code, proxy)
                    if api_success:
                        phone_verifier._save_number(phone, email, "api_verify")
                        phone_verifier.api.finish_order(order_id)
                        Logger.STATUS = f"{MskColor.GREEN}Phone verified"
                        Logger.queue_log(worker_id=worker_id)
                        return True, ""
                    else:
                        phone_verifier.api.cancel_order(order_id)
                        return False, "API fallback failed"

            phone_verifier.api.cancel_order(order_id)
            return False, "Input fields hidden"

        except Exception as e:
            try:
                phone_verifier.api.cancel_order(order_id)
            except:
                pass
            return False, "Exception occurred"

    def _dismiss_discord_modals(self, page):
        """Close any blocking Discord modals (e.g. 'Create Your First Discord Server')."""
        modal_close_selectors = [
            'div[aria-label="Close"]',
            'button[aria-label="Close"]',
            'div[class*="closeButton"]',
            'button[class*="closeButton"]',
            'div[class*="modal"] div[aria-label="Close"]',
            'div[class*="modal"] button[aria-label="Close"]',
        ]
        for sel in modal_close_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(2)
                    return True
            except:
                continue
        try:
            page.keyboard.press("Escape")
            time.sleep(2)
            return True
        except:
            pass
        return False

    def _handle_proactive_phone_browser(self, page, worker_id: int, token: str, email: str, proxy: Optional[Dict]) -> bool:
        phone_verifier = None
        country = "any"
        operator = "any"
        if FIVESIM_AVAILABLE and self.config.get("fivesim", {}).get("enabled", False):
            fivesim_config = self.config.get("fivesim", {})
            country = fivesim_config.get("country", "any")
            operator = fivesim_config.get("operator", "any")
            phone_verifier = PhoneVerifier(
                api_key=fivesim_config.get("api_key", ""),
                number_limit=fivesim_config.get("number_limit", 10),
                country=country,
                operator=operator
            )
        elif ONLINESIM_AVAILABLE and self.config.get("onlinesim", {}).get("enabled", False):
            onlinesim_config = self.config.get("onlinesim", {})
            country = onlinesim_config.get("country", "7")
            operator = "any"
            phone_verifier = OnlineSimVerifier(
                api_key=onlinesim_config.get("api_key", ""),
                number_limit=onlinesim_config.get("number_limit", 10),
                country=country
            )

        if not phone_verifier or not phone_verifier.is_enabled():
            Logger.STATUS = f"{MskColor.YELLOW}Phone verify skipped: No provider enabled"
            Logger.queue_log(worker_id=worker_id)
            return False

        if not phone_verifier.can_use_number():
            Logger.STATUS = f"{MskColor.YELLOW}Phone verify skipped: Number limit reached"
            Logger.queue_log(worker_id=worker_id)
            return False

        order_id = None
        try:
            Logger.STATUS = f"{MskColor.PRIMARY}Verifying phone number..."
            Logger.queue_log(worker_id=worker_id)

            solver = CaptchaSolver(page, worker_id)

            try:
                page.goto("https://discord.com/channels/@me", timeout=15_000, wait_until="domcontentloaded")
                time.sleep(3)
            except:
                pass

            for _modal_try in range(3):
                dismissed = self._dismiss_discord_modals(page)
                if dismissed:
                    break
                time.sleep(1)

            settings_opened = False
            settings_selectors = [
                'button[aria-label="User Settings"]',
                'div[aria-label="User Settings"]',
                'button[class*="button"][aria-label*="Settings"]',
                '[class*="panels"] button[aria-label*="Settings"]',
            ]
            for sel in settings_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        settings_opened = True
                        time.sleep(2)
                        break
                except:
                    continue

            if not settings_opened:
                try:
                    page.keyboard.press("Escape")
                    time.sleep(1)
                except:
                    pass
                for sel in settings_selectors:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            btn.click()
                            settings_opened = True
                            time.sleep(2)
                            break
                    except:
                        continue

            if not settings_opened:
                try:
                    page.keyboard.press("Control+,")
                    time.sleep(2)
                    settings_opened = True
                except:
                    pass

            if not settings_opened:
                return False

            phone_add_found = False
            try:
                phone_text = page.query_selector('text="Phone Number"')
                if phone_text:
                    phone_text.scroll_into_view_if_needed()
                    time.sleep(1)
            except:
                pass

            phone_selectors = [
                'div:has-text("Phone Number") button:has-text("Add")',
                'button:has-text("Add")',
                'div[class*="phone"] button',
                'button:has-text("Phone Number")',
            ]
            for sel in phone_selectors:
                try:
                    elements = page.query_selector_all(sel)
                    for el in elements:
                        try:
                            if el.is_visible():
                                el_text = el.inner_text().strip().lower()
                                if 'add' in el_text or 'phone' in el_text:
                                    el.click()
                                    phone_add_found = True
                                    time.sleep(2)
                                    break
                        except:
                            continue
                    if phone_add_found:
                        break
                except:
                    continue

            phone_input = None
            for attempt in range(15):
                phone_input = self._find_phone_input(page)
                if phone_input:
                    break
                if self._check_phone_verification_screen(page, worker_id):
                    verify_btn = self._find_phone_button(page)
                    if verify_btn:
                        try:
                            verify_btn.click()
                            time.sleep(2)
                        except:
                            try:
                                verify_btn.evaluate("el => el.click()")
                                time.sleep(2)
                            except:
                                pass
                    phone_input = self._find_phone_input(page)
                    if phone_input:
                        break
                time.sleep(1)

            if not phone_input:
                return False

            number_data = phone_verifier.api.buy_number(country=country, operator=operator)
            if not number_data:
                return False

            order_id = number_data["id"]
            phone = number_data["phone"]
            phone_formatted = phone if phone.startswith("+") else f"+{phone}"

            Logger.STATUS = f"{MskColor.PRIMARY}Phone: {phone_formatted[:7]}***"
            Logger.queue_log(worker_id=worker_id)

            self._select_country_and_enter_phone(page, phone_input, phone_formatted, worker_id)
            time.sleep(0.5)

            page.evaluate('''() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    const btnText = btn.innerText.trim();
                    if (btnText === 'Send') {
                        btn.scrollIntoView({ block: "center" });
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            time.sleep(3)

            for _hcap_retry in range(3):
                if self._solve_hcaptcha_if_present(page, worker_id, timeout=5):
                    break
                time.sleep(2)

            page_text = ""
            try:
                body = page.query_selector("body")
                if body:
                    page_text = body.inner_text().lower()
            except:
                pass

            error_indicators = [
                "invalid phone", "phone number is invalid", "unable to send",
                "this phone number", "already been used", "cannot use this",
            ]
            if any(err in page_text for err in error_indicators):
                phone_verifier.api.cancel_order(order_id)
                return False

            if self._check_phone_verification_screen(page, worker_id):
                phone_must_btn = self._find_phone_button(page)
                if phone_must_btn:
                    try:
                        phone_must_btn.click()
                    except:
                        try:
                            phone_must_btn.evaluate("el => el.click()")
                        except:
                            pass
                    time.sleep(2)

                phone_input_retry = None
                for retry_attempt in range(8):
                    phone_input_retry = self._find_phone_input(page)
                    if phone_input_retry:
                        break
                    code_early = self._find_code_input(page)
                    if code_early:
                        break
                    time.sleep(1)

                if phone_input_retry:
                    self._select_country_and_enter_phone(page, phone_input_retry, phone_formatted, worker_id)
                    time.sleep(0.5)

                    resend_btn = self._find_submit_button(page, "Send", "Next", "Submit", "Verify")
                    if resend_btn:
                        try:
                            resend_btn.click()
                        except:
                            try:
                                resend_btn.evaluate("el => el.click()")
                            except:
                                pass
                        time.sleep(3)
                    else:
                        try:
                            phone_input_retry.press("Enter")
                            time.sleep(3)
                        except:
                            pass

            code = phone_verifier.api.get_sms(order_id, timeout=600)
            if not code:
                phone_verifier.api.cancel_order(order_id)
                return False

            import re as re_mod
            if len(code) == 6 and code.isdigit():
                verification_code = code
            else:
                match = re_mod.search(r'\b(\d{6})\b', code)
                if match:
                    verification_code = match.group(1)
                else:
                    match = re_mod.search(r'(\d{4,8})', code)
                    if match:
                        verification_code = match.group(1)
                    else:
                        phone_verifier.api.cancel_order(order_id)
                        return False

            Logger.STATUS = f"{MskColor.PRIMARY}Code: {verification_code}"
            Logger.queue_log(worker_id=worker_id)

            code_filled = False
            for attempt in range(8):
                code_inputs_multi = self._find_code_inputs_multi(page)
                if code_inputs_multi:
                    code_filled = self._fill_code_digit_by_digit(page, code_inputs_multi, verification_code, worker_id)
                    break
                code_input = self._find_code_input(page)
                if code_input:
                    try:
                        code_input.click()
                        time.sleep(0.2)
                        code_input.fill("")
                        time.sleep(0.2)
                        code_input.type(verification_code, delay=30)
                    except:
                        code_input.fill(verification_code)
                    code_filled = True
                    time.sleep(0.5)

                    submit_btn = self._find_submit_button(page, "Verify", "Submit", "Confirm")
                    if submit_btn:
                        try:
                            submit_btn.click()
                        except:
                            try:
                                submit_btn.evaluate("el => el.click()")
                            except:
                                pass
                    else:
                        try:
                            code_input.press("Enter")
                        except:
                            pass
                    time.sleep(3)
                    break
                time.sleep(1)

            if code_filled:
                time.sleep(2)
                page.evaluate('''(password) => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    for (const inp of inputs) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        inp.focus();
                        inp.value = password;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }''', self.password)
                time.sleep(0.5)

                page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        const btnText = btn.innerText.trim();
                        if (btnText === 'Confirm') {
                            btn.scrollIntoView({ block: "center" });
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                time.sleep(3)

                for _hcap_retry in range(3):
                    if solver.is_captcha_solved(page):
                        break
                    hcaptcha_frame2 = None
                    try:
                        for iframe in page.query_selector_all("iframe"):
                            src = iframe.get_attribute("src") or ""
                            if "hcaptcha.com" in src:
                                frame_candidate = iframe.content_frame()
                                if frame_candidate:
                                    try:
                                        if frame_candidate.wait_for_selector("#menu-info", timeout=3000):
                                            hcaptcha_frame2 = frame_candidate
                                            break
                                    except Exception:
                                        continue
                    except Exception:
                        pass
                    if hcaptcha_frame2:
                        Logger.queue_log(worker_id=worker_id)
                        auto_solve = self.config.get("auto_solver_captcha", True)
                        if auto_solve:
                            try:
                                solve_result = solver.solve_accessibility_hcaptcha(hcaptcha_frame2)
                                if solve_result < 0:
                                    solver.refresh_captcha(hcaptcha_frame2)
                                time.sleep(2)
                            except:
                                pass
                        else:
                            solver.wait_for_captcha_solved(hcaptcha_frame2, timeout=120)
                            time.sleep(2)
                        break
                    time.sleep(2)

                phone_verifier._save_number(phone, email, "browser_proactive")
                phone_verifier.api.finish_order(order_id)
                Logger.STATUS = f"{MskColor.GREEN}Phone verified"
                Logger.queue_log(worker_id=worker_id)
            else:
                api_success = self._verify_phone_via_api(token, phone_formatted, verification_code, proxy)
                if api_success:
                    phone_verifier._save_number(phone, email, "api_proactive")
                    phone_verifier.api.finish_order(order_id)
                    Logger.STATUS = f"{MskColor.GREEN}Phone verified"
                    Logger.queue_log(worker_id=worker_id)
                    return True
                else:
                    phone_verifier.api.cancel_order(order_id)
                    return False
            return True

        except Exception as e:
            try:
                if order_id:
                    phone_verifier.api.cancel_order(order_id)
            except:
                pass
            return False

    def _verify_phone_via_api(self, token: str, phone: str, code: str, proxy: Optional[Dict] = None) -> bool:
        try:
            import tls_client
            session = tls_client.Session(client_identifier="chrome_120")

            if proxy:
                proxy_url = Utils.proxy_dict_to_url(proxy_dict=proxy)
                session.proxies = {'http': proxy_url, 'https': proxy_url}

            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Discord-Locale": "en-US",
            }

            response = session.post(
                "https://discord.com/api/v9/users/@me/phone",
                headers=headers,
                json={"phone": phone}
            )
            if response.status_code not in [200, 204]:
                return False

            time.sleep(1)

            verify_response = session.post(
                "https://discord.com/api/v9/users/@me/phone/verify",
                headers=headers,
                json={"phone": phone, "code": code}
            )
            return verify_response.status_code in [200, 204]
        except:
            return False
    
    @property
    def config(self) -> Dict:
        """Always read fresh config from file to ensure latest values."""
        return Config.config

    @staticmethod
    def _censor_token(token: str, visible_start: int = 6, visible_end: int = 6) -> str:
        if len(token) <= visible_start + visible_end:
            return "***"
        return f"{token[:visible_start]}***{token[-visible_end:]}"
    
    def _fill_birthday_and_checkboxes(self, page: Any, worker_id: int) -> dict:
        """Fill DOB dropdowns + checkboxes via fully self-contained inline JS.
        No window.utils dependency -- works even if JS injection failed.
        Month selected by 1-based index (language-agnostic).
        Day/Year selected by text content (numbers are universal).
        """
        _MONTH_NAMES = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        try:
            month_idx = _MONTH_NAMES.index(self.month) + 1
        except ValueError:
            month_idx = 1

        day_val  = str(self.day).replace("'", "\\'")
        year_val = str(self.year).replace("'", "\\'")

        js = f"""
        async () => {{
            const M = ['month','mois','mes','monat','mese','mês','måned','maand',
                       'kuukausi','měsíc','miesiąc','hónap','lună','месяц','月',
                       'maand','mois','mois'];
            const D = ['day','jour','día','tag','giorno','dia','dag','päivä',
                       'den','dzień','nap','zi','день','日','gün','dia'];
            const Y = ['year','année','año','jahr','anno','ano','år','jaar',
                       'vuosi','rok','év','an','год','年','yıl','ano'];

            function fire(el) {{
                ['mousedown','mouseup','click'].forEach(t =>
                    el.dispatchEvent(new MouseEvent(t,{{bubbles:true,cancelable:true,view:window}}))
                );
            }}
            const wait = ms => new Promise(r => setTimeout(r, ms));
            function waitFor(fn, ms) {{
                return new Promise(r => {{
                    const s = Date.now();
                    const c = () => {{ const v=fn(); if(v) r(v); else if(Date.now()-s>ms) r(null); else setTimeout(c,50); }};
                    c();
                }});
            }}

            function findBtn(variants) {{
                for (const b of document.querySelectorAll('[role="button"], [role="combobox"], div[class*="control"], div[class*="css-1hwfws3"]')) {{
                    const al = (b.getAttribute('aria-label')||'').toLowerCase();
                    let tx = (b.innerText||b.textContent||'').trim().toLowerCase();
                    if (!tx) {{
                        const ph = b.querySelector('[class*="placeholder"]');
                        if (ph) tx = (ph.innerText||'').trim().toLowerCase();
                    }}
                    if (variants.some(v => al.includes(v) || tx === v)) return b;
                }}
                return null;
            }}

            function birthday3() {{
                const btns = [...document.querySelectorAll('[role="button"], [role="combobox"], div[class*="control"]')]
                    .filter(b => b.querySelector('svg') || b.querySelector('[class*="indicator"]'));
                for (let i = 0; i <= btns.length-3; i++) {{
                    const a=btns[i], b2=btns[i+1], c2=btns[i+2];
                    const pa=a.parentElement, pb=b2.parentElement, pc=c2.parentElement;
                    if (pa && pa===pb && pb===pc) return [a,b2,c2];
                    if (pa && pb && pa.parentElement===pb.parentElement && pb.parentElement===pc.parentElement)
                        return [a,b2,c2];
                }}
                return btns.slice(0,3);
            }}

            async function pick(variants, posIdx, val, byIndex) {{
                let btn = findBtn(variants);
                if (!btn) {{
                    const t3 = birthday3();
                    if (t3.length > posIdx) btn = t3[posIdx];
                }}
                if (!btn) return 'no_btn';

                fire(btn);
                await wait(450);

                const lb = await waitFor(() => document.querySelector('[role="listbox"]'), 6000);
                if (!lb) return 'no_listbox';

                const opts = await waitFor(() => {{
                    const o = [...document.querySelectorAll('[role="option"]')];
                    return o.length ? o : null;
                }}, 6000);
                if (!opts) return 'no_opts';

                await wait(200);

                let tgt = byIndex
                    ? (opts[val-1] || null)
                    : opts.find(o => o.textContent.trim() === String(val));

                if (!tgt && !byIndex) {{
                    let cont = opts[0].parentElement;
                    while (cont && cont !== document.body) {{
                        const st = window.getComputedStyle(cont);
                        if (st.overflowY==='auto'||st.overflowY==='scroll') break;
                        cont = cont.parentElement;
                    }}
                    for (let i=0; i<80 && !tgt; i++) {{
                        if (cont && cont!==document.body) cont.scrollTop += 200;
                        await wait(50);
                        tgt = [...document.querySelectorAll('[role="option"]')]
                              .find(o => o.textContent.trim() === String(val));
                    }}
                }}

                if (!tgt) return 'no_match';
                tgt.scrollIntoView({{block:'nearest'}});
                await wait(100);
                fire(tgt);
                await wait(350);
                return true;
            }}

            function checkAll() {{
                let n=0;
                [...document.querySelectorAll('input[type="checkbox"]')]
                    .filter(c=>!c.checked).forEach(c=>{{try{{c.click();n++;}}catch(e){{}}}});
                [...document.querySelectorAll('[role="checkbox"]')]
                    .filter(c=>c.getAttribute('aria-checked')!=='true')
                    .forEach(c=>{{try{{fire(c);n++;}}catch(e){{}}}});
                [...document.querySelectorAll('label')]
                    .filter(l=>{{const i=l.querySelector('input[type="checkbox"]');return i&&!i.checked;}})
                    .forEach(l=>{{try{{l.click();n++;}}catch(e){{}}}});
                return n;
            }}

            const rm = await pick(M, 0, {month_idx}, true);
            await wait(300);
            const rd = await pick(D, 1, '{day_val}', false);
            await wait(300);
            const ry = await pick(Y, 2, '{year_val}', false);
            await wait(200);
            const rc = checkAll();
            return {{month:rm, day:rd, year:ry, checkboxes:rc}};
        }}
        """
        try:
            result = page.evaluate(js)
            if result:
                failed = [k for k in ("month", "day", "year") if result.get(k) is not True]
                if failed:
                    Logger.STATUS = f"{MskColor.YELLOW}DOB partial: {result}"
                    Logger.queue_log(worker_id=worker_id)
            return result or {}
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}DOB fill error: {str(e)[:100]}"
            Logger.queue_log(worker_id=worker_id)
            return {}

    def register(self, worker_id: int, on_browser_closed=None) -> str:
        browser_method = self.config.get("browser_method", "brave")

        if browser_method == "brave":
            try:
                from .discord_register_brave import DiscordRegisterBrave
                brave_register = DiscordRegisterBrave()
                if hasattr(self, 'controller'):
                    brave_register.controller = self.controller
                brave_register._trigger_parent = self
                self._active_sub_register = brave_register  # expose for stop button
                result = brave_register.register(worker_id=worker_id, on_browser_closed=on_browser_closed)
                if hasattr(brave_register, 'last_result'):
                    self.last_result = brave_register.last_result
                return result
            except ImportError as e:
                Logger.STATUS = f"{MskColor.RED}Brave import error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except FileNotFoundError:
                Logger.STATUS = f"{MskColor.RED}Brave browser not found! Install Brave from https://brave.com"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Brave method error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

        if browser_method == "chromium":
            try:
                from .discord_register_chromium import DiscordRegisterChromium
                chromium_register = DiscordRegisterChromium()
                if hasattr(self, 'controller'):
                    chromium_register.controller = self.controller
                chromium_register._trigger_parent = self
                self._active_sub_register = chromium_register  # expose for stop button
                result = chromium_register.register(worker_id=worker_id, on_browser_closed=on_browser_closed)
                if hasattr(chromium_register, 'last_result'):
                    self.last_result = chromium_register.last_result
                return result
            except ImportError as e:
                Logger.STATUS = f"{MskColor.RED}Chromium import error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except FileNotFoundError:
                Logger.STATUS = f"{MskColor.RED}Chrome/Chromium not found! Install Chrome from https://google.com/chrome"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Chromium method error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

        if browser_method == "chromium2":
            try:
                from .discord_register_chromium2 import DiscordRegisterChromium2
                chromium2_register = DiscordRegisterChromium2()
                if hasattr(self, 'controller'):
                    chromium2_register.controller = self.controller
                chromium2_register._trigger_parent = self
                self._active_sub_register = chromium2_register
                result = chromium2_register.register(worker_id=worker_id, on_browser_closed=on_browser_closed)
                if hasattr(chromium2_register, 'last_result'):
                    self.last_result = chromium2_register.last_result
                return result
            except ImportError as e:
                Logger.STATUS = f"{MskColor.RED}Chromium 2 import error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Chromium 2 error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"

        if browser_method == "clearcote":
            try:
                from .discord_register_clearcote import DiscordRegisterClearcote
                clearcote_register = DiscordRegisterClearcote()
                if hasattr(self, 'controller'):
                    clearcote_register.controller = self.controller
                clearcote_register._trigger_parent = self
                self._active_sub_register = clearcote_register
                result = clearcote_register.register(worker_id=worker_id, on_browser_closed=on_browser_closed)
                if hasattr(clearcote_register, 'last_result'):
                    self.last_result = clearcote_register.last_result
                return result
            except ImportError as e:
                Logger.STATUS = f"{MskColor.RED}Clearcote import error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"
            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Clearcote error: {str(e)[:80]}"
                Logger.queue_log(worker_id=worker_id)
                return "Invalid"


        proxy: Optional[Dict[str, str]] = None
        if self.config.get("proxies", {}).get("enabled", False):
            proxy = self.proxy_manager.get_proxy(worker_id=worker_id)
            if not proxy:
                proxy = self.proxy_manager.wait_for_proxies(worker_id)
            if proxy:
                server = proxy.get("server", "")
                host_port = server.split("://")[-1]
                username = proxy.get("username", "")
                password = proxy.get("password", "")
                full_proxy = f"{username}:{password}@{host_port}" if username and password else host_port
                Logger.STATUS = f"{MskColor.PRIMARY}Using Proxy: {full_proxy} for thread {worker_id}"
                Logger.queue_log(worker_id=worker_id)


        start_time_startup: float = time.time()
        Logger.STATUS = f"{MskColor.PRIMARY}Starting Browser"
        Logger.queue_log(worker_id=worker_id)

        headless_mode = self.config.get("headless", False)

        _text_solver = self.config.get("auto_solver_captcha", False)

        if headless_mode and not _text_solver:
            Logger.STATUS = f"{MskColor.RED}You have to turn on any auto solver to use headless or turn it off"
            Logger.queue_log(worker_id=worker_id)
            return "HeadlessNoSolverSelected"

        # Camoufox is now stable, no warning needed
        
        wm = getattr(self.controller, '_wm', None) if hasattr(self, 'controller') and self.controller else None
        slot_idx, pos = None, None
        launch_lock_acquired = False

        if wm:
            slot_idx, pos = wm.acquire_slot()
            wm.launch_lock.acquire()
            launch_lock_acquired = True

        browser_ctx = None
        from ..Helper.mail import _devnull
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = _devnull
        sys.stderr = _devnull
        try:
            camoufox_proxy = None
            if proxy:
                camoufox_proxy = {"server": proxy.get("server")}
                if proxy.get("username"):
                    camoufox_proxy["username"] = proxy.get("username")
                if proxy.get("password"):
                    camoufox_proxy["password"] = proxy.get("password")

            kwargs = {
                'proxy': camoufox_proxy,
                'headless': headless_mode,
                'screen': Screen(max_width=1280, max_height=720),
                'geoip': True,
                'locale': ["en-US", "en"],
                'humanize': True,
            }
            if wm and pos:
                kwargs['window'] = (pos[2], pos[3])
            
            browser_ctx = Camoufox(**kwargs)
            browser = browser_ctx.__enter__()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        self._browser_ctx = browser_ctx
        
        try:

            try:
                page = browser.new_page(no_viewport=True)
            except Exception as e:
                err_msg = str(e).lower()
                if "target" in err_msg and "closed" in err_msg:
                    return "ignore"
                raise
            
            if wm:
                import uuid
                uid = str(uuid.uuid4())
                try:
                    page.goto("about:blank")
                    page.evaluate(f"document.title = '{uid}';")
                    wm.find_and_register_by_title(uid, slot_idx, pos)
                except:
                    pass
            
            if wm and launch_lock_acquired:
                try:
                    wm.launch_lock.release()
                    launch_lock_acquired = False
                except:
                    pass

            _auto_solve_on = self.config.get("auto_solver_captcha", True)
            if _auto_solve_on:
                Logger.queue_log(worker_id=worker_id)

                try:
                    _tok = _client.solve_hcaptcha(sitekey, host, timeout=90)
                    return _tok or ""
                except Exception:
                    return ""
            else:
                try:
                    page.add_init_script("""
                    (() => {
                        var _msk_solving = false;
                        var _msk_last_sitekey = '';
                        function _msk_try_solve() {
                            try {
                                if (_msk_solving) return;
                                var iframes = document.querySelectorAll('iframe[src*="hcaptcha"]');
                                if (!iframes.length) return;
                                var src = iframes[0].src || '';
                                var qi = src.indexOf('?');
                                var params = new URLSearchParams(qi >= 0 ? src.slice(qi + 1) : '');
                                var sitekey = params.get('sitekey') || '';
                                var host = params.get('host') || location.hostname;
                                if (!sitekey || sitekey === _msk_last_sitekey) return;
                                _msk_solving = true;
                                _msk_last_sitekey = sitekey;
                                    _msk_solving = false;
                                    if (!token) return;
                                    try {
                                        var fields = document.querySelectorAll(
                                            '[name="h-captcha-response"],[name="g-recaptcha-response"]'
                                        );
                                        for (var i = 0; i < fields.length; i++) {
                                            try {
                                                Object.getOwnPropertyDescriptor(
                                                    window.HTMLTextAreaElement.prototype, 'value'
                                                ).set.call(fields[i], token);
                                                fields[i].dispatchEvent(new Event('input', {bubbles: true}));
                                                fields[i].dispatchEvent(new Event('change', {bubbles: true}));
                                            } catch(e2) {
                                                fields[i].value = token;
                                            }
                                        }
                                        try {
                                            if (window.hcaptcha && typeof window.hcaptcha.execute === 'function') {
                                                window.hcaptcha.execute();
                                            }
                                        } catch(e) {}
                                        var submitBtns = document.querySelectorAll(
                                            '[type="submit"],[data-hcaptcha-response],.hcaptcha-submit'
                                        );
                                        if (submitBtns.length) {
                                            try { submitBtns[0].click(); } catch(e) {}
                                        }
                                    } catch(e) {}
                                }).catch(function() { _msk_solving = false; });
                            } catch(e) {}
                        }
                        setInterval(_msk_try_solve, 2500);
                    })();
                    """)
                except Exception:
                    pass

            if self.config.get("data_saver_enabled"):
                Logger.STATUS = f"{MskColor.PRIMARY}Data Saver Enabled: Cleaning Discord Data & Blocking Media..."
                Logger.queue_log(worker_id=worker_id)
                
                try:
                    browser.clear_cookies()
                except:
                    pass

                page.add_init_script("""
                    try { localStorage.clear(); } catch(e) {}
                    try { sessionStorage.clear(); } catch(e) {}
                    try {
                        if (window.indexedDB) {
                            indexedDB.databases().then(dbs => {
                                dbs.forEach(db => { try { indexedDB.deleteDatabase(db.name); } catch(e) {} });
                            }).catch(() => {});
                        }
                    } catch(e) {}
                """)

                def block_media_and_trackers(route):
                    try:
                        url = route.request.url.lower()
                        if "hcaptcha" in url:
                            route.fallback()
                            return
                        blocked = False
                        if any(p in url for p in [
                            "api/science", "sentry.io", "sentry-cdn",
                            "/api/v9/track", "/api/v10/track",
                            "/api/v9/experiments", "/api/v10/experiments",
                            "/api/v9/activities", "/api/v10/activities",
                        ]):
                            blocked = True
                        elif any(ext in url for ext in [".mp4", ".webm", ".mov", ".avi"]):
                            blocked = True
                        elif ("discord.com/assets/" in url or "cdn.discordapp.com/" in url) and \
                             any(ext in url for ext in [".png", ".jpg", ".webp", ".svg", ".gif"]):
                            blocked = True
                        elif any(p in url for p in [
                            "/api/v9/tutorial", "/api/v10/tutorial",
                            "/api/v9/guild-discovery", "/api/v10/guild-discovery",
                            "/api/v9/sticker", "/api/v10/sticker",
                            "/api/v9/promotions", "/api/v10/promotions",
                            "/api/v9/outbound-promotions", "/api/v10/outbound-promotions",
                            "/api/v9/remote-auth", "/api/v10/remote-auth",
                            "/api/v9/connections", "/api/v10/connections",
                        ]):
                            blocked = True
                        elif any(p in url for p in [
                            "fonts.googleapis.com", "fonts.gstatic.com",
                        ]):
                            blocked = True
                        elif "discord.com/assets/" in url and any(ext in url for ext in [".woff", ".ttf"]):
                            blocked = True

                        if blocked:
                            route.abort()
                        else:
                            route.fallback()
                    except:
                        try:
                            route.fallback()
                        except:
                            pass
                try:
                    page.route("**/*", block_media_and_trackers)
                except:
                    pass

            try:
                page.goto("https://discord.com/register", timeout=30_000, wait_until="networkidle")
            except Exception as nav_err:
                err_str = str(nav_err).lower()
                if "target" in err_str and "closed" in err_str:
                    return "ignore"
                short_err = str(nav_err).split('\\n')[0]
                Logger.STATUS = f"{MskColor.RED}Failed to load Discord register page: {short_err[:100]}"
                Logger.queue_log(worker_id=worker_id)
                return "ignore"

            self.js_injector.setup_js(page)

            elapsed_time_startup: float = time.time() - start_time_startup
            Logger.STATUS = f"{MskColor.PRIMARY}Loading Page"
            Logger.queue_log(worker_id=worker_id)

            page_url = page.url.lower()
            page_title = ""
            try:
                page_title = page.title().lower()
            except:
                pass

            try:
                body_el = page.query_selector("body")
                page_body_text = body_el.inner_text().lower() if body_el else ""
            except:
                page_body_text = ""

            email_input = page.query_selector('input[name="email"]')
            if not email_input:
                Logger.STATUS = f"{MskColor.PRIMARY}Waiting for registration form to load..."
                Logger.queue_log(worker_id=worker_id)
                try:
                    page.wait_for_selector('input[name="email"]', timeout=15_000)
                except:
                    try:
                        page.reload(wait_until="networkidle", timeout=30_000)
                        page.wait_for_selector('input[name="email"]', timeout=15_000)
                    except:
                        pass
                email_input = page.query_selector('input[name="email"]')

            if not email_input:
                if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):
                    return None
                snippet = page_body_text[:100].replace('\n', ' ').strip()
                Logger.STATUS = f"{MskColor.RED}Registration form not found. Page: {snippet[:60] if snippet else page_url[:60]}"
                Logger.queue_log(worker_id=worker_id)
                time.sleep(2)
                return None

            email_providers = self.config.get("email_providers", {})
            self._zeus_refresh_token = ""
            self._zeus_client_id = ""
            email, email_password = self._create_email(worker_id)
            use_real_usernames = self.config.get("real_usernames", False)
            username = Utils.generate_real_username(use_api=use_real_usernames)
            
            start_time: float = time.time()
            Logger.STATUS = f"{MskColor.PRIMARY}Filling Inputs"
            Logger.queue_log(worker_id=worker_id)

            page.wait_for_selector('input[name="email"]', timeout=10_000)
            self.js_injector.set_input(page, 'input[name="email"]', email)
            self.js_injector.set_input(page, 'input[name="username"]', username)
            self.js_injector.set_input(page, 'input[name="password"]', self.password)

            self._fill_birthday_and_checkboxes(page, worker_id)

            page.wait_for_selector('button[type="submit"]', timeout=3_000)
            self.js_injector.click_element(page, 'button[type="submit"]')

            hcap_start: float = time.time()
            solver: CaptchaSolver = CaptchaSolver(page, worker_id)
            Logger.STATUS = f"{MskColor.PRIMARY}Waiting For Captcha"
            Logger.queue_log(worker_id=worker_id)

            max_captcha_retries = 3
            captcha_attempts = 0
            _early_inbox_done = None
            _early_inbox_result = [None]
            _early_mail_api = None
            _early_verify_kwargs = None

            while captcha_attempts < max_captcha_retries:
                frame = solver.find_hcaptcha_frame(page=page, timeout=self.config.get("captcha_timeout", 30))
                if not frame:
                    if solver.is_captcha_solved(page):
                        break
                    break

                hcap_time: float = time.time() - hcap_start
                hcap_time_solve: float = 0.0

                if solver.is_captcha_solved(page):
                    Logger.queue_log(worker_id=worker_id)
                    break
                else:
                    Logger.queue_log(worker_id=worker_id)
                    time.sleep(2)
                    Logger.queue_log(worker_id=worker_id)
                    hcap_time_solve = -1.0

                auto_solve = self.config.get("auto_solver_captcha", True)

                if auto_solve:
                    hcap_time_solve = solver.solve_accessibility_hcaptcha(frame=frame)
                else:
                    Logger.queue_log(worker_id=worker_id)
                    solver.wait_for_captcha_solved(frame=frame, timeout=120)
                    hcap_time_solve = 1.0

                if hcap_time_solve == -2.0:
                    captcha_attempts += 1
                    if captcha_attempts >= max_captcha_retries:
                        Logger.STATUS = f"{MskColor.RED}Auto-solve failed after {max_captcha_retries} attempts (unavailable). Try changing proxies or VPN."
                        Logger.queue_log(worker_id=worker_id)
                        return "EndlessCaptcha"
                    solver.refresh_captcha(frame)
                    time.sleep(2)
                    continue
                elif hcap_time_solve < 0:
                    captcha_attempts += 1
                    if captcha_attempts >= max_captcha_retries:
                        Logger.STATUS = f"{MskColor.RED}Auto-solve failed after {max_captcha_retries} attempts. Try changing proxies or VPN."
                        Logger.queue_log(worker_id=worker_id)
                        return "EndlessCaptcha"
                    solver.refresh_captcha(frame)
                    time.sleep(2)
                    continue

                time.sleep(1)

                if _early_inbox_done is None:
                    import threading as _threading
                    _early_inbox_done = _threading.Event()
                    _early_email_timeout = self.config.get("email_verification_timeout", 0)
                    if not _early_email_timeout or _early_email_timeout <= 0:
                        _early_email_timeout = 120
                    _early_verify_kwargs = {"email": email, "timeout": _early_email_timeout, "poll_interval": 2}
                    if email_providers.get("cybertemp", {}).get("enabled", False):
                        from ..Helper.mail import MskMailApi
                        _early_mail_api = MskMailApi(api_key=email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", ""))
                    elif email_providers.get("duckmail", {}).get("enabled", False):
                        from ..Helper.mail import DuckMailApi
                        _early_mail_api = DuckMailApi(api_key=email_providers.get("duckmail", {}).get("api_key", ""))
                        _early_verify_kwargs["password"] = email_password
                    elif email_providers.get("mailcow", {}).get("enabled", False):
                        from ..Helper.mail import MailcowApi
                        _mc = email_providers.get("mailcow", {})
                        _early_mail_api = MailcowApi(host_url=_mc.get("host_url", ""), api_key=_mc.get("api_key", ""))
                        _early_verify_kwargs["password"] = email_password
                    elif email_providers.get("zeus", {}).get("enabled", False):
                        from ..Helper.mail import ZeusApi
                        _zc = email_providers.get("zeus", {})
                        _early_mail_api = ZeusApi(api_key=_zc.get("api_key", ""), account_type=_zc.get("account_type", "HOTMAIL"))
                        _early_verify_kwargs["password"] = email_password
                        _early_verify_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _early_verify_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    elif email_providers.get("hotmail007", {}).get("enabled", False):
                        from ..Helper.mail import Hotmail007Api
                        _hc = email_providers.get("hotmail007", {})
                        _early_mail_api = Hotmail007Api(api_key=_hc.get("api_key", ""), mail_type=_hc.get("mail_type", "hotmail"))
                        _early_verify_kwargs["password"] = email_password
                        _early_verify_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _early_verify_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    elif email_providers.get("lution", {}).get("enabled", False):
                        from ..Helper.mail import LutionApi
                        _lc = email_providers.get("lution", {})
                        _early_mail_api = LutionApi(api_key=_lc.get("api_key", ""), category=_lc.get("account_type", "hotmail"))
                        _early_verify_kwargs["password"] = email_password
                        _early_verify_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _early_verify_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    else:
                        from ..Helper.mail import MskMailApi
                        _early_mail_api = MskMailApi(api_key=self.config.get("cybertemp_api_key", ""))

                    def _run_early_poll(_m=_early_mail_api, _k=_early_verify_kwargs, _r=_early_inbox_result, _d=_early_inbox_done):
                        try:
                            _stop = lambda: getattr(getattr(self, 'controller', None), 'should_stop', False)
                            _k = dict(_k)
                            _k['stop_signal'] = _stop
                            _r[0] = _m.get_verification_url(**_k) if _m else None
                        except Exception:
                            _r[0] = None
                        _d.set()

                    _threading.Thread(target=_run_early_poll, daemon=True).start()
                    if hcap_time_solve > 0:
                        pass # Captcha solve log is already handled by the solver.
                    Logger.STATUS = f"{MskColor.PRIMARY}Email Verifying"
                    Logger.queue_log(worker_id=worker_id)

                _t_retries = 0
                while _t_retries < 15:
                    try:
                        token = self.js_injector.wait_for_discord_token(page=page)
                        if token: break
                    except Exception as e:
                        if "Function not found" in str(e) or "context was destroyed" in str(e).lower() or "target closed" in str(e).lower():
                            self.js_injector._injected_context_ids.discard(id(page))
                            try:
                                self.js_injector.setup_js(page)
                            except:
                                pass
                    _t_retries += 1
                    if not token: time.sleep(2)
                
                if token:
                    break
                
                new_frame = solver.find_hcaptcha_frame(page=page, timeout=8)
                if new_frame:
                    captcha_attempts += 1
                    Logger.STATUS = f"{MskColor.YELLOW}hCaptcha reappeared, attempt {captcha_attempts}/{max_captcha_retries}"
                    Logger.queue_log(worker_id=worker_id)
                    if captcha_attempts >= max_captcha_retries:
                        Logger.STATUS = f"{MskColor.RED}Endless hCaptcha detected. Try changing proxies or turning on a VPN."
                        Logger.queue_log(worker_id=worker_id)
                        return "EndlessCaptcha"
                    # Re-solve the reappeared captcha
                    if solver.is_captcha_solved(page):
                        break
                    time.sleep(2)
                    if self.config.get("auto_solver_captcha", True):
                        hcap_time_solve = solver.solve_accessibility_hcaptcha(frame=new_frame)
                        if hcap_time_solve < 0:
                            time.sleep(2)
                    else:
                        solver.wait_for_captcha_solved(frame=new_frame, timeout=120)
                    time.sleep(1)
                    continue  # retry token extraction after re-solve
                else:
                    break

            time.sleep(2)
            
            phone_verified = False
            phone_verify_start = time.time()
            
            if self._check_phone_verification_screen(page, worker_id):
                fivesim_config = self.config.get("fivesim", {})
                onlinesim_config = self.config.get("onlinesim", {})
                
                if fivesim_config.get("enabled", False) and fivesim_config.get("api_key"):
                    success, reason = self._handle_phone_verification_browser(page, worker_id, email, proxy)
                    if success:
                        phone_verified = True
                        time.sleep(2)
                    else:
                        Logger.STATUS = f"{MskColor.RED}Phone verification failed: {reason}"
                        Logger.queue_log(worker_id=worker_id)
                elif onlinesim_config.get("enabled", False) and onlinesim_config.get("api_key"):
                    success, reason = self._handle_phone_verification_browser(page, worker_id, email, proxy)
                    if success:
                        phone_verified = True
                        time.sleep(2)
                    else:
                        Logger.STATUS = f"{MskColor.RED}OnlineSim phone verification failed: {reason}"
                        Logger.queue_log(worker_id=worker_id)
                elif (fivesim_config.get("enabled") and not fivesim_config.get("api_key")) or (onlinesim_config.get("enabled") and not onlinesim_config.get("api_key")):
                    Logger.STATUS = f"{MskColor.YELLOW}Phone verification required but API key is missing."
                    Logger.queue_log(worker_id=worker_id)

            _t_retries2 = 0
            while _t_retries2 < 15:
                try:
                    token = self.js_injector.wait_for_discord_token(page=page)
                    if token: break
                except Exception as e:
                    if "Function not found" in str(e) or "context was destroyed" in str(e).lower() or "target closed" in str(e).lower():
                        self.js_injector._injected_context_ids.discard(id(page))
                        try:
                            self.js_injector.setup_js(page)
                        except:
                            pass
                _t_retries2 += 1
                if not token: time.sleep(2)
                
            if not token:
                return "ignore"

            time.sleep(1)
            if not phone_verified and self._check_phone_verification_screen(page, worker_id):
                fivesim_config = self.config.get("fivesim", {})
                onlinesim_config = self.config.get("onlinesim", {})
                
                if (fivesim_config.get("enabled", False) and fivesim_config.get("api_key")) or \
                   (onlinesim_config.get("enabled", False) and onlinesim_config.get("api_key")):
                    success, reason = self._handle_phone_verification_browser(page, worker_id, email, proxy)
                    if success:
                        phone_verified = True
                        time.sleep(2)
                    else:
                        Logger.STATUS = f"{MskColor.RED}Phone verification failed (checkpoint 2): {reason}"
                        Logger.queue_log(worker_id=worker_id)


            humanized: bool = False
            humanize_time: float = 0.0


            try:
                token_status: Dict[str, str] = Utils.check_discord_token(token=token, proxy=proxy)
            except Exception as e:
                token_status = {"status": "Invalid"}

            elapsed_time: float = time.time() - start_time

            fivesim_config = self.config.get("fivesim", {})
            
            time.sleep(1)
            if not phone_verified and self._check_phone_verification_screen(page, worker_id):
                fivesim_config = self.config.get("fivesim", {})
                fivesim_enabled = fivesim_config.get("enabled", False)
                fivesim_key = fivesim_config.get("api_key", "")
                
                if fivesim_enabled and fivesim_key:
                    success, reason = self._handle_phone_verification_browser(page, worker_id, email, proxy)
                    if success:
                        phone_verified = True
                        time.sleep(2)
                    else:
                        Logger.STATUS = f"{MskColor.RED}Phone verification failed (checkpoint 3): {reason}"
                        Logger.queue_log(worker_id=worker_id)
                elif fivesim_enabled and not fivesim_key:
                    pass
            
            
            if token_status["status"] == "Valid" or token_status["status"] == "EmailVerify":
                delay_config = self.config.get("email_verification_delay", "0s")
                delay_seconds = 0
                
                if delay_config and isinstance(delay_config, str):
                    delay_config = delay_config.strip().lower()
                    try:
                        if delay_config.endswith('s'):
                            delay_seconds = int(delay_config[:-1])
                        elif delay_config.endswith('m'):
                            delay_seconds = int(delay_config[:-1]) * 60
                        else:
                            delay_seconds = int(delay_config)
                    except ValueError:
                        Logger.STATUS = f"{MskColor.YELLOW}Invalid email_verification_delay format: {delay_config}, using 0s"
                        Logger.queue_log(worker_id=worker_id)
                        delay_seconds = 0
                
                if delay_seconds > 0:
                    Logger.STATUS = f"{MskColor.PRIMARY}Waiting {delay_config} before email verification..."
                    Logger.queue_log(worker_id=worker_id)
                    time.sleep(delay_seconds)
                
                start_time_verify: float = time.time()

                mail_api = _early_mail_api
                verify_kwargs = _early_verify_kwargs or {}

                if _early_inbox_done is not None:
                    _inbox_elapsed = 0
                    while not _early_inbox_done.wait(timeout=3):
                        _inbox_elapsed += 3
                        Logger.STATUS = f"{MskColor.YELLOW}Waiting for verification email... ({_inbox_elapsed}s)"
                        Logger.queue_log(worker_id=worker_id)
                    verification_url = _early_inbox_result[0]
                else:
                    Logger.STATUS = f"{MskColor.PRIMARY}Checking inbox for verification email..."
                    Logger.queue_log(worker_id=worker_id)
                    import threading as _threading
                    _fb_done = _threading.Event()
                    _fb_result = [None]
                    _fb_timeout = self.config.get("email_verification_timeout", 0)
                    if not _fb_timeout or _fb_timeout <= 0:
                        _fb_timeout = 120
                    _fb_kwargs = {"email": email, "timeout": _fb_timeout, "poll_interval": 2}
                    if email_providers.get("duckmail", {}).get("enabled", False):
                        _fb_kwargs["password"] = email_password
                    elif email_providers.get("mailcow", {}).get("enabled", False):
                        _fb_kwargs["password"] = email_password
                    elif email_providers.get("zeus", {}).get("enabled", False):
                        _fb_kwargs["password"] = email_password
                        _fb_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _fb_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    elif email_providers.get("hotmail007", {}).get("enabled", False):
                        _fb_kwargs["password"] = email_password
                        _fb_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _fb_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    elif email_providers.get("lution", {}).get("enabled", False):
                        _fb_kwargs["password"] = email_password
                        _fb_kwargs["refresh_token"] = getattr(self, '_zeus_refresh_token', '')
                        _fb_kwargs["client_id"] = getattr(self, '_zeus_client_id', '')
                    if not mail_api:
                        from ..Helper.mail import MskMailApi
                        mail_api = MskMailApi(api_key=self.config.get("cybertemp_api_key", ""))

                    def _poll_fallback(_m=mail_api, _k=_fb_kwargs, _r=_fb_result, _d=_fb_done):
                        try:
                            _r[0] = _m.get_verification_url(**_k)
                        except Exception:
                            _r[0] = None
                        _d.set()

                    _threading.Thread(target=_poll_fallback, daemon=True).start()
                    _inbox_elapsed = 0
                    while not _fb_done.wait(timeout=3):
                        _inbox_elapsed += 3
                        Logger.STATUS = f"{MskColor.YELLOW}Checking inbox... ({_inbox_elapsed}s)"
                        Logger.queue_log(worker_id=worker_id)
                    verification_url = _fb_result[0]
                ev: bool = False
                ev_token: Optional[str] = None
                
                if verification_url:
                    pass

                    linkverify_path = get_resource_path("data/output/linkverify.txt")
                    os.makedirs(os.path.dirname(linkverify_path), exist_ok=True)
                    with open(linkverify_path, "a", encoding="utf-8") as f:
                        f.write(f"{email}: {verification_url}\n")
                    
                    browser_verifier = BrowserMailVerify(page=page, worker_id=worker_id)
                    ev = browser_verifier.verify_email_with_browser(verification_url=verification_url, timeout=60)
                    
                    if not ev:
                        if hasattr(mail_api, 'get_inbox'):
                            upn = mail_api.get_inbox(email=email, password=email_password, timeout=_early_email_timeout)
                            if upn:
                                api_verify = MailVerify(proxy_dict=proxy)
                                ev_token, ev = api_verify.verify_token(token=token, upn=upn)
                                if ev and ev_token:
                                    token = ev_token
                else:
                    Logger.STATUS = f"{MskColor.RED}Failed to get verification link (timed out)"
                    Logger.queue_log(worker_id=worker_id)
                    if hasattr(mail_api, 'get_inbox'):
                        upn = mail_api.get_inbox(email=email, password=email_password, timeout=_early_email_timeout)
                        if upn:
                            api_verify = MailVerify(proxy_dict=proxy)
                            ev_token, ev = api_verify.verify_token(token=token, upn=upn)
                            if ev and ev_token:
                                token = ev_token
                
                elapsed_time_verify: float = time.time() - start_time_verify

                if ev:
                    Logger.STATUS = f"{MskColor.GREEN}Token Verified!"
                    Logger.queue_log(worker_id=worker_id)
                    token_status["status"] = "Valid"
                    
                    verify_without_must = fivesim_config.get("verify_without_must", False)
                    if verify_without_must and not phone_verified:
                        time.sleep(2)
                        if self._check_phone_verification_screen(page, worker_id):
                            success, _ = self._handle_phone_verification_browser(page, worker_id, email, proxy)
                            if success:
                                phone_verified = True
                                time.sleep(2)
                        else:
                            if self._handle_proactive_phone_browser(page, worker_id, token, email, proxy):
                                phone_verified = True

                phone_verify_time = time.time() - phone_verify_start if phone_verified else 0.0


                tokens_path = get_resource_path("data/output/tokens.txt")
                os.makedirs(os.path.dirname(tokens_path), exist_ok=True)
                with open(tokens_path, "a", encoding="utf-8") as f:
                    f.write(f"{email}:{self.password}:{token}\n")

                if self.config["humanizer"]["enabled"] and ev:
                    Logger.STATUS = f"{MskColor.PRIMARY}Humanizing Token..."
                    Logger.queue_log(worker_id=worker_id)

                    humanizer = DiscordHuminazer(worker_id=worker_id)
                    humanize_start: float = time.time()
                    humanized = humanizer.humanize_account(token, proxy)
                    humanize_time = time.time() - humanize_start
                    if humanized:
                        Logger.STATUS = f"{MskColor.GREEN}Token Humanized!"
                        Logger.queue_log(worker_id=worker_id)

                humanize_status: str = f"{MskColor.GREEN}Humanized" if humanized else f"{MskColor.RED}Not Humanized"
                ev_status: str = f"{MskColor.GREEN}Email Verified" if ev else f"{MskColor.RED}Unclaimed"

                checker_status = "Valid"
                try:
                    from .token_checker import check_token_safe
                    # Pass proxy so the check uses the same IP as registration.
                    # Without this, datacenter/proxy IPs cause Discord's /settings
                    # endpoint to 403 from a different IP, producing false "Locked".
                    _tc = check_token_safe(token, proxy=proxy if (self.config.get("proxies") or {}).get("enabled", False) else None)
                    if not _tc.get("valid"):
                        Logger.STATUS = f"{MskColor.RED}Token Invalid"
                        checker_status = "Invalid"
                    elif _tc.get("locked") or _tc.get("email_required") or _tc.get("phone_required"):
                        Logger.STATUS = f"{MskColor.ORANGE}Token Locked"
                        checker_status = "Locked"
                    else:
                        Logger.STATUS = f"{MskColor.GREEN}Token Valid"
                        checker_status = "Valid"
                    Logger.queue_log(worker_id=worker_id)
                except Exception:
                    Logger.STATUS = f"{MskColor.RED}Token Check Failed"
                    checker_status = "Invalid"
                    Logger.queue_log(worker_id=worker_id)
                
                token_status["status"] = checker_status

                Logger.STATUS = f"{MskColor.GREEN}Token Generated!"
                Logger.queue_log(worker_id=worker_id)

                try:
                    if sys.stdout:
                        sys.stdout.write("\n")
                except Exception:
                    pass

                self.print_stats(
                    worker_id, token, elapsed_time, elapsed_time_startup,
                    hcap_time, hcap_time_solve, humanize_time,
                    elapsed_time_verify, phone_verify_time, phone_verified,
                    humanize_status, ev_status
                )

                try:
                    _lv = locals()
                    def _f(k, default=0.0):
                        v = _lv.get(k)
                        try:
                            return round(float(v or default), 1)
                        except Exception:
                            return default
                    self.last_result = {
                        "token": str(_lv.get("token") or ""),
                        "email": str(_lv.get("email") or ""),
                        "status": checker_status,
                        "humanized": bool(_lv.get("humanized") or False),
                        "phone_verified": bool(_lv.get("phone_verified") or False),
                        "email_verified": bool(_lv.get("ev") or False),
                        "gen_time": _f("elapsed_time"),
                        "hcap_time": _f("hcap_time_solve"),
                        "email_time": _f("elapsed_time_verify"),
                        "phone_time": _f("phone_verify_time"),
                        "humanize_time": _f("humanize_time"),
                    }
                except Exception:
                    pass

            else:
                status_file = get_resource_path(f"data/output/{token_status['status'].lower()}.txt")
                os.makedirs(os.path.dirname(status_file), exist_ok=True)
                with open(status_file, "a", encoding="utf-8") as f:
                    f.write(f"{email}:{self.password}:{token}\n")

                checker_status = token_status["status"]
                try:
                    from .token_checker import check_token_safe
                    _tc = check_token_safe(token, proxy=proxy if (self.config.get("proxies") or {}).get("enabled", False) else None)
                    if not _tc.get("valid"):
                        Logger.STATUS = f"{MskColor.RED}Token Invalid"
                        checker_status = "Invalid"
                    elif _tc.get("locked") or _tc.get("email_required") or _tc.get("phone_required"):
                        Logger.STATUS = f"{MskColor.ORANGE}Token Locked"
                        checker_status = "Locked"
                    else:
                        Logger.STATUS = f"{MskColor.GREEN}Token Valid"
                        checker_status = "Valid"
                    Logger.queue_log(worker_id=worker_id)
                except Exception:
                    Logger.STATUS = f"{MskColor.RED}Token Check Failed"
                    checker_status = "Invalid"
                    Logger.queue_log(worker_id=worker_id)
                token_status["status"] = checker_status

                Logger.STATUS = f"{MskColor.GREEN}Token Generated!"
                Logger.queue_log(worker_id=worker_id)

                logs_cfg: Dict = self.config.get("logs", {})

                display_token = token
                if logs_cfg.get("censor_token", False):
                    display_token = self._censor_token(token)

                stats: list[tuple[str, str, bool]] = [
                    ("Token", display_token, True),
                    ("Status", f"{token_status['status']}", True)
                ]

                Logger.queue_stats(worker_id, stats)

                try:
                    self.last_result = {
                        "token": str(token) if token else "",
                        "email": str(email) if email else "",
                        "status": token_status["status"],
                        "humanized": bool(humanized) if 'humanized' in locals() else False,
                        "phone_verified": bool(phone_verified) if 'phone_verified' in locals() else False,
                        "email_verified": False,
                        "gen_time": round(float(elapsed_time), 1) if 'elapsed_time' in locals() else 0.0,
                        "hcap_time": round(float(hcap_time_solve) if hcap_time_solve > 0 else 0.0, 1) if 'hcap_time_solve' in locals() else 0.0,
                        "email_time": 0.0,
                        "phone_time": 0.0,
                        "humanize_time": 0.0,
                    }
                except Exception:
                    pass

        finally:
            if wm and launch_lock_acquired:
                try:
                    wm.launch_lock.release()
                except:
                    pass

            try:
                if browser_ctx is not None:
                    browser_ctx.__exit__(None, None, None)
                    time.sleep(0.1)
            except Exception:
                pass
            if on_browser_closed:
                try:
                    on_browser_closed(worker_id)
                except Exception:
                    pass
            
            if wm and slot_idx is not None:
                try:
                    wm.release(slot_idx)
                except Exception:
                    pass
            
            try:
                import gc
                gc.collect()
            except:
                pass

        return token_status["status"]

    def print_stats(
        self,
        worker_id: int,  
        token: str,
        elapsed_time: float,
        startup_time: float,
        hcap_wait: float,
        hcap_solve: float,
        humanize_time: float,
        email_verify_time: float,
        phone_verify_time: float,
        phone_verified: bool,
        humanize_status: str,
        ev_status: str
    ) -> None:
        logs_cfg: Dict = self.config.get("logs", {})

        display_token = token
        if logs_cfg.get("censor_token", False):
            display_token = self._censor_token(token)

        phone_status: str = f"{MskColor.GREEN}Phone Verified" if phone_verified else f"{MskColor.RED}Not Phone Verified"

        stats: list[tuple[str, str, bool]] = [
            ("Token", display_token, True),
            ("Generation Time", f"{elapsed_time:.2f}s", logs_cfg.get("generation_time", True)),
            ("Browser Startup Time", f"{startup_time:.2f}s", logs_cfg.get("startup_time", False)),
            ("hCaptcha Waiting Time", f"{hcap_wait:.2f}s", logs_cfg.get("hcaptcha_waiting", False)),
            ("hCaptcha Solving Time", f"{hcap_solve:.2f}s", logs_cfg.get("hcaptcha_solving", True)),
            ("Humanize Time", f"{humanize_time:.2f}s", logs_cfg.get("humanize_time", True)),
            ("Email Verify Time", f"{email_verify_time:.2f}s", logs_cfg.get("verify_time", True)),
            ("Phone Verify Time", f"{phone_verify_time:.2f}s", logs_cfg.get("phone_verify_time", True)),
            ("Total Time", f"{email_verify_time + humanize_time + elapsed_time + startup_time + phone_verify_time:.2f}s", logs_cfg.get("total_time", True)),
            ("Status", f"{humanize_status}, {ev_status}, {phone_status}", True)
        ]

        Logger.queue_stats(worker_id, stats)
