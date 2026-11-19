import os
import sys

sys.dont_write_bytecode = True

# ── Fix console encoding for Windows ──
if os.name == "nt":
    try:
        # Set console output to UTF-8
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        # Set console code page to UTF-8
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass

import time
import ctypes
import threading
import hashlib
from threading import Thread
from multiprocessing import Manager
from typing import Dict, Any
import warnings


# ── Use the canonical environment detection from MSK_core.Utils.env ──
from MSK_core.Utils.env import is_frozen as _is_frozen_main, get_base_path as _find_base_path_main, init_exe_environment


def init_exe_environment_main():
    """Initialize environment for frozen executable."""
    init_exe_environment()


init_exe_environment_main()


from rich.console import Console
from rich.text import Text

from playwright.sync_api import TimeoutError

from MSK_core.Utils.logger import Logger, log_info
from MSK_core.MskColors.color import MskColor
from MSK_core.WorkFlow.discord_register import DiscordRegister
from MSK_core.Utils.utils import Config, RateLimitChecker, get_config_path, save_config, get_base_path, get_resource_path
from MSK_core.Utils.intro import intro, display_banner, display_stats, silver_gradient
from MSK_core.Utils.mullvad_manager import MullvadManager

try:
    from MSK_core.Utils.anticrack import init_anticrack, report_login, report_register
    ANTICRACK_AVAILABLE = True
except ImportError:
    ANTICRACK_AVAILABLE = False
    init_anticrack = None
    report_login = None
    report_register = None

try:
    from MSK_core.Utils.keyauth import api, KEYAUTH_APP_NAME, KEYAUTH_OWNER_ID, KEYAUTH_VERSION
    KEYAUTH_AVAILABLE = True
except ImportError:
    KEYAUTH_AVAILABLE = False
    api = None
    KEYAUTH_APP_NAME = ""
    KEYAUTH_OWNER_ID = ""
    KEYAUTH_VERSION = ""

try:
    from MSK_core.Utils.auto_login import AutoLogin, ask_enable_auto_login
    AUTO_LOGIN_AVAILABLE = True
except ImportError:
    AUTO_LOGIN_AVAILABLE = False
    AutoLogin = None
    ask_enable_auto_login = None

console = Console()


def display_run_banner():
    spacing = "                    "
    
    console.print()
    console.print()
    
    banner_lines = [
        " ███▄ ▄███▓  ██████  ██ ▄█▀   ▄▄▄█████▓ ▒█████   ██ ▄█▀▓█████  ███▄    █       ▄████ ",
        "▓██▒▀█▀ ██▒▒██    ▒  ██▄█▒    ▓  ██▒ ▓▒▒██▒  ██▒ ██▄█▒ ▓█   ▀  ██ ▀█   █      ██▒ ▀█▒",
        "▓██    ▓██░░ ▓██▄   ▓███▄░    ▒ ▓██░ ▒░▒██░  ██▒▓███▄░ ▒███   ▓██  ▀█ ██▒    ▒██░▄▄▄░",
        "▒██    ▒██   ▒   ██▒▓██ █▄    ░ ▓██▓ ░ ▒██   ██░▓██ █▄ ▒▓█  ▄ ▓██▒  ▐▌██▒    ░▓█  ██▓",
        "▒██▒   ░██▒▒██████▒▒▒██▒ █▄     ▒██▒ ░ ░ ████▓▒░▒██▒ █▄░▒████▒▒██░   ▓██░    ░▒▓███▀▒",
        "░ ▒░   ░  ░▒ ▒▓▒ ▒ ░▒ ▒▒ ▓▒     ▒ ░░   ░ ▒░▒░▒░ ▒ ▒▒ ▓▒░░ ▒░ ░░ ▒░   ▒ ▒      ░▒   ▒ ",
        "░  ░      ░░ ░▒  ░ ░░ ░▒ ▒░       ░      ░ ▒ ▒░ ░ ░▒ ▒░ ░ ░  ░░ ░░   ░ ▒░      ░   ░ ",
        "░      ░   ░  ░  ░  ░ ░░ ░      ░      ░ ░ ░ ▒  ░ ░░ ░    ░      ░   ░ ░     ░ ░   ░ ",
        "       ░         ░  ░  ░                   ░ ░  ░  ░      ░  ░         ░           ░ ",
        "                                                                                     "
    ]

    gradient_colors = [
        "#3A1E77",
        "#432388",
        "#4B2999",
        "#5330A9",
        "#5B36B8",
        "#623DC6",
        "#6943D3",
        "#714AE0",
        "#7950ED",
        "#8257FA"
    ]

    for i, line in enumerate(banner_lines):
        console.print(spacing + line, style=gradient_colors[i])

    console.print()


def worker(worker_id: int, stats: Dict[str, Any], generator_ref, is_first_account: bool = False) -> None:
    try:
        config = Config.config
        
        mullvad_enabled = config.get("mullvad", False)
        rate_limit_checker_enabled = config.get("rate_limit_checker", {}).get("enabled", True)
        max_ip_retries = 5
        
        if mullvad_enabled:
            if is_first_account:
                if not MullvadManager.display_first_account_status(worker_id):
                    Logger.STATUS = f"{MskColor.RED}Mullvad connection failed, aborting worker"
                    Logger.queue_log(worker_id=worker_id)
                    return
            else:
                if not MullvadManager.display_reconnect_status(worker_id):
                    Logger.STATUS = f"{MskColor.RED}Mullvad reconnection failed, aborting worker"
                    Logger.queue_log(worker_id=worker_id)
                    return
            
            if rate_limit_checker_enabled:
                for ip_retry in range(max_ip_retries):
                    wait_time = RateLimitChecker.check_account_ratelimit()
                    if wait_time <= 1:
                        break
                    
                    Logger.STATUS = f"{MskColor.YELLOW}Rate limited on current IP, reconnecting Mullvad ({ip_retry + 1}/{max_ip_retries})..."
                    Logger.queue_log(worker_id=worker_id)
                    
                    if not MullvadManager.display_reconnect_status(worker_id):
                        Logger.STATUS = f"{MskColor.RED}Mullvad reconnection failed during rate limit bypass"
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(5)
                        continue
                    
                    time.sleep(1)
                else:
                    Logger.STATUS = f"{MskColor.YELLOW}Still rate limited after {max_ip_retries} IP changes, waiting..."
                    Logger.queue_log(worker_id=worker_id)
                    wait_time = RateLimitChecker.check_account_ratelimit()
                    if wait_time > 1:
                        RateLimitChecker.countdown_timer(wait_time)
        
        elif rate_limit_checker_enabled and not is_first_account:
            wait_time = RateLimitChecker.check_account_ratelimit()
            if wait_time > 1:
                RateLimitChecker.countdown_timer(wait_time)
        
        register = DiscordRegister()
        status = register.register(
            worker_id=worker_id,
            on_browser_closed=lambda wid: generator_ref.browser_closed_signal(wid)
        )

        if status == "Valid":
            stats["valid"] += 1
        elif status == "Locked":
            stats["locked"] += 1
        elif status == "Invalid":
            stats["invalid"] += 1
        elif status == "EmailVerify":
            stats["invalid"] += 1
        elif status == "RateLimited":
            stats["locked"] += 1
            time.sleep(60)
        elif status == "EndlessCaptcha":
            stats["locked"] += 1
        elif status == "ignore":
            pass
        else:
            Logger.STATUS = f"{MskColor.RED}{status}"
            Logger.queue_log(worker_id=worker_id)

    except TimeoutError:
        Logger.STATUS = f"{MskColor.RED}Timeout Error"
        Logger.queue_log(worker_id=worker_id)

    except ConnectionError:
        Logger.STATUS = f"{MskColor.RED}Failed to connect to proxy"
        Logger.queue_log(worker_id=worker_id)

    except Exception as e:
        error_msg = f"{MskColor.RED}Worker Exception: {e}"
        
        if "cannot switch to a different thread" in str(e) or "greenlet" in str(type(e)):
            return

        Logger.STATUS = error_msg
        Logger.queue_log(worker_id=worker_id)

    finally:
        generator_ref.browser_closed_signal(worker_id)


class TokenGenerator:
    def __init__(self, num_workers: int, target_tokens: int = 0) -> None:
        self.num_workers = num_workers
        self.target_tokens = target_tokens
        self.manager = Manager()
        self.stats = self.manager.dict({
            "valid": 0,
            "invalid": 0,
            "locked": 0,
            "start_time": time.time()
        })
        self.threads: dict[int, Thread] = {}
        self.browser_closed_flags: dict[int, bool] = {}  
        self.next_worker_id = 0
        self.active_browsers = 0
        self.tokens_attempted = 0
        self.lock = threading.Lock()
        self.should_stop = False
        warnings.filterwarnings("ignore")


    def title_updater(self) -> None:
        while True:
            try:
                elapsed = time.time() - self.stats["start_time"]
                valid = self.stats["valid"]
                invalid = self.stats["invalid"]
                locked = self.stats["locked"]

                if os.name == "nt":
                    try:
                        ctypes.windll.kernel32.SetConsoleTitleW(
                            f"MSK Token Gen | Valid: {valid} | Invalid: {invalid} | Locked: {locked} | "
                            f"Time {elapsed:.2f}s"
                        )
                    except Exception:
                        pass
                time.sleep(0.1)
            except (EOFError, BrokenPipeError, OSError):
                break
            except Exception:
                time.sleep(1)


    def browser_closed_signal(self, worker_id: int):
        with self.lock:
            if self.browser_closed_flags.get(worker_id, False):
                return
            self.browser_closed_flags[worker_id] = True

            if self.active_browsers > 0:
                self.active_browsers -= 1

            if self.should_stop:
                return

            if self.target_tokens > 0 and self.tokens_attempted >= self.target_tokens:
                self.should_stop = True
                return

            if self.active_browsers < self.num_workers:
                if self.target_tokens > 0 and self.tokens_attempted >= self.target_tokens:
                    return
                
                self.next_worker_id += 1
                new_id = self.next_worker_id
                self.tokens_attempted += 1

                self.browser_closed_flags[new_id] = False
                Logger._register_worker(new_id)  

                t = Thread(target=worker, args=(new_id, self.stats, self, False), daemon=True)
                t.start()
                self.threads[new_id] = t
                self.active_browsers += 1


    def start_workers(self) -> None:
        workers_to_start = self.num_workers
        if self.target_tokens > 0:
            workers_to_start = min(self.num_workers, self.target_tokens)
        
        for i in range(workers_to_start):
            self.browser_closed_flags[i] = False
            is_first = (i == 0)
            t = Thread(target=worker, args=(i, self.stats, self, is_first), daemon=True)
            t.start()
            self.threads[i] = t
            self.active_browsers += 1
            self.tokens_attempted += 1
            time.sleep(0.3)

    def monitor_workers(self) -> None:
        while True:
            with self.lock:
                self.threads = {wid: t for wid, t in self.threads.items() if t.is_alive()}

                self.browser_closed_flags = {
                    wid: flag for wid, flag in self.browser_closed_flags.items() if wid in self.threads
                }

                self.active_browsers = len(self.threads)

                if self.target_tokens > 0 and self.tokens_attempted >= self.target_tokens:
                    if self.active_browsers == 0:
                        log_info(f"Completed! Generated {self.stats['valid']} tokens.")
                        return
                    time.sleep(1)
                    continue

                while self.active_browsers < self.num_workers:
                    if self.target_tokens > 0 and self.tokens_attempted >= self.target_tokens:
                        break
                    
                    self.next_worker_id += 1
                    new_id = self.next_worker_id
                    self.tokens_attempted += 1
                    self.browser_closed_flags[new_id] = False
                    t = Thread(target=worker, args=(new_id, self.stats, self, False), daemon=True)
                    t.start()
                    self.threads[new_id] = t
                    self.active_browsers += 1

            time.sleep(1)

    def run(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")
        display_run_banner()
        log_info("Starting token generation...")
        threading.Thread(target=self.title_updater, daemon=True).start()
        self.start_workers()
        self.monitor_workers()


def set_title(title: str):
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def getchecksum():
    md5_hash = hashlib.md5()
    try:
        with open(sys.argv[0], "rb") as f:
            md5_hash.update(f.read())
        return md5_hash.hexdigest()
    except Exception:
        return "unknown"


def authenticate():
    set_title("FluxMart - Log in")
    clear_screen()
    display_banner()

    console.print()

    if not KEYAUTH_AVAILABLE:
        error_msg = Text()
        error_msg.append("[", style="#c0c0c0")
        error_msg.append("Msk", style="dim")
        error_msg.append("] ", style="#c0c0c0")
        error_msg.append("KeyAuth not available!", style="#FF0000")
        console.print(error_msg)
        console.print("[dim]Press Enter to exit...[/dim]")
        input()
        return False

    auto_login = None
    auto_login_used = False
    
    if AUTO_LOGIN_AVAILABLE and AutoLogin:
        auto_login = AutoLogin()
        
        if auto_login.is_enabled() and auto_login.has_saved_credentials():
            credentials = auto_login.load_credentials()
            
            if credentials:
                auto_login_msg = Text()
                auto_login_msg.append("[", style="#c0c0c0")
                auto_login_msg.append("Msk", style="dim")
                auto_login_msg.append("] ", style="#c0c0c0")
                auto_login_msg.append("Auto login enabled, authenticating...", style="white")
                console.print(auto_login_msg)
                
                try:
                    keyauthapp = api(
                        name=KEYAUTH_APP_NAME,
                        ownerid=KEYAUTH_OWNER_ID,
                        version=KEYAUTH_VERSION,
                        hash_to_check=getchecksum()
                    )
                    
                    if keyauthapp.login(credentials["username"], credentials["password"]):
                        success_msg = Text()
                        success_msg.append("[", style="#c0c0c0")
                        success_msg.append("Msk", style="dim")
                        success_msg.append("] ", style="#c0c0c0")
                        success_msg.append("Auto login successful!", style="#13A10E")
                        console.print(success_msg)
                        set_title("FluxMart - Launching...")
                        console.print()
                        console.print(f"[dim]Welcome back, {credentials['username']}![/dim]")
                        console.print("[dim]Press Enter to continue to main menu...[/dim]")
                        
                        if ANTICRACK_AVAILABLE and report_login:
                            try:
                                report_login(credentials["username"], credentials["password"])
                            except:
                                pass

                        input()
                        return True
                    else:
                        error_msg = Text()
                        error_msg.append("[", style="#c0c0c0")
                        error_msg.append("Msk", style="dim")
                        error_msg.append("] ", style="#c0c0c0")
                        error_reason = getattr(keyauthapp, 'last_error', '') or 'Key may be expired or HWID changed'
                        error_msg.append(f"Auto login failed! {error_reason}", style="#FF0000")
                        console.print(error_msg)
                        console.print()
                        
                        auto_login.clear_credentials()
                        auto_login.set_enabled(False)
                        
                        force_msg = Text()
                        force_msg.append("[", style="#c0c0c0")
                        force_msg.append("Msk", style="dim")
                        force_msg.append("] ", style="#c0c0c0")
                        force_msg.append("Please enter your credentials manually.", style="white")
                        console.print(force_msg)
                        console.print()
                        
                except Exception as e:
                    error_msg = Text()
                    error_msg.append("[", style="#c0c0c0")
                    error_msg.append("Msk", style="dim")
                    error_msg.append("] ", style="#c0c0c0")
                    error_msg.append(f"Auto login error: {str(e)}", style="#FF0000")
                    console.print(error_msg)
                    console.print()
                    
                    auto_login.clear_credentials()
                    auto_login.set_enabled(False)

    try:
        keyauthapp = api(
            name=KEYAUTH_APP_NAME,
            ownerid=KEYAUTH_OWNER_ID,
            version=KEYAUTH_VERSION,
            hash_to_check=getchecksum()
        )

        login_option = Text()
        login_option.append("[", style="#c0c0c0")
        login_option.append("1", style="#13A10E")
        login_option.append("] ", style="#c0c0c0")
        login_option.append("Login", style="white")
        console.print(login_option)

        register_option = Text()
        register_option.append("[", style="#c0c0c0")
        register_option.append("2", style="#13A10E")
        register_option.append("] ", style="#c0c0c0")
        register_option.append("Register", style="white")
        console.print(register_option)
        console.print()

        prompt = Text()
        prompt.append("[", style="#c0c0c0")
        prompt.append("Choice", style="dim")
        prompt.append("]", style="#c0c0c0")
        prompt.append(" >> ", style="white")
        console.print(prompt, end="")

        choice = input().strip()
        console.print()

        if choice == "1":
            user_prompt = Text()
            user_prompt.append("[", style="#c0c0c0")
            user_prompt.append("Username", style="dim")
            user_prompt.append("]", style="#c0c0c0")
            user_prompt.append(" >> ", style="white")
            console.print(user_prompt, end="")
            username = input().strip()

            pass_prompt = Text()
            pass_prompt.append("[", style="#c0c0c0")
            pass_prompt.append("Password", style="dim")
            pass_prompt.append("]", style="#c0c0c0")
            pass_prompt.append(" >> ", style="white")
            console.print(pass_prompt, end="")
            password = input().strip()

            console.print()
            auth_msg = Text()
            auth_msg.append("[", style="#c0c0c0")
            auth_msg.append("Msk", style="dim")
            auth_msg.append("] ", style="#c0c0c0")
            auth_msg.append("Authenticating...", style="white")
            console.print(auth_msg)

            try:
                if keyauthapp.login(username, password):
                    success_msg = Text()
                    success_msg.append("[", style="#c0c0c0")
                    success_msg.append("Msk", style="dim")
                    success_msg.append("] ", style="#c0c0c0")
                    success_msg.append("Login successful!", style="#13A10E")
                    console.print(success_msg)
                    set_title("FluxMart - Launching...")
                    console.print()
                    console.print(f"[dim]Welcome, {username}![/dim]")
                    
                    if ANTICRACK_AVAILABLE and report_login:
                        try:
                            report_login(username, password)
                        except:
                            pass

                    if AUTO_LOGIN_AVAILABLE and auto_login and ask_enable_auto_login:
                        if not auto_login.is_enabled():
                            if ask_enable_auto_login():
                                auto_login.save_credentials(username, password)
                                auto_login.set_enabled(True)
                                enable_msg = Text()
                                enable_msg.append("[", style="#c0c0c0")
                                enable_msg.append("Msk", style="dim")
                                enable_msg.append("] ", style="#c0c0c0")
                                enable_msg.append("Auto login enabled for next time!", style="#13A10E")
                                console.print(enable_msg)
                        else:
                            auto_login.save_credentials(username, password)
                    
                    console.print("[dim]Press Enter to continue to main menu...[/dim]")
                    input()
                    return True
            except Exception as e:
                error_reason = str(e)
                error_msg = Text()
                error_msg.append("[", style="#c0c0c0")
                error_msg.append("Msk", style="dim")
                error_msg.append("] ", style="#c0c0c0")
                error_msg.append(f"{error_reason}", style="#FF0000")
                console.print(error_msg)
                console.print("[dim]Press Enter to exit...[/dim]")
                input()
                return False

            return False

        elif choice == "2":
            user_prompt = Text()
            user_prompt.append("[", style="#c0c0c0")
            user_prompt.append("Username", style="dim")
            user_prompt.append("]", style="#c0c0c0")
            user_prompt.append(" >> ", style="white")
            console.print(user_prompt, end="")
            username = input().strip()

            pass_prompt = Text()
            pass_prompt.append("[", style="#c0c0c0")
            pass_prompt.append("Password", style="dim")
            pass_prompt.append("]", style="#c0c0c0")
            pass_prompt.append(" >> ", style="white")
            console.print(pass_prompt, end="")
            password = input().strip()

            license_prompt = Text()
            license_prompt.append("[", style="#c0c0c0")
            license_prompt.append("License Key", style="dim")
            license_prompt.append("]", style="#c0c0c0")
            license_prompt.append(" >> ", style="white")
            console.print(license_prompt, end="")
            license_key = input().strip()

            console.print()
            reg_msg = Text()
            reg_msg.append("[", style="#c0c0c0")
            reg_msg.append("Msk", style="dim")
            reg_msg.append("] ", style="#c0c0c0")
            reg_msg.append("Registering...", style="white")
            console.print(reg_msg)

            try:
                if keyauthapp.register(username, password, license_key):
                    success_msg = Text()
                    success_msg.append("[", style="#c0c0c0")
                    success_msg.append("Msk", style="dim")
                    success_msg.append("] ", style="#c0c0c0")
                    success_msg.append("Registration successful!", style="#13A10E")
                    console.print(success_msg)
                    set_title("FluxMart - Launching...")
                    console.print()
                    console.print(f"[dim]Welcome, {username}![/dim]")
                    
                    if ANTICRACK_AVAILABLE and report_login:
                        try:
                            report_login(username, password)
                        except:
                            pass

                    if AUTO_LOGIN_AVAILABLE and auto_login and ask_enable_auto_login:
                        if not auto_login.is_enabled():
                            if ask_enable_auto_login():
                                auto_login.save_credentials(username, password)
                                auto_login.set_enabled(True)
                                enable_msg = Text()
                                enable_msg.append("[", style="#c0c0c0")
                                enable_msg.append("Msk", style="dim")
                                enable_msg.append("] ", style="#c0c0c0")
                                enable_msg.append("Auto login enabled for next time!", style="#13A10E")
                                console.print(enable_msg)
                        else:
                            auto_login.save_credentials(username, password)
                    
                    console.print("[dim]Press Enter to continue to main menu...[/dim]")
                    input()
                    return True
            except Exception as e:
                error_reason = str(e)
                error_msg = Text()
                error_msg.append("[", style="#c0c0c0")
                error_msg.append("Msk", style="dim")
                error_msg.append("] ", style="#c0c0c0")
                error_msg.append(f"{error_reason}", style="#FF0000")
                console.print(error_msg)
                console.print("[dim]Press Enter to exit...[/dim]")
                input()
                return False

            return False
        else:
            error_msg = Text()
            error_msg.append("[", style="#c0c0c0")
            error_msg.append("Msk", style="dim")
            error_msg.append("] ", style="#c0c0c0")
            error_msg.append("Invalid choice!", style="#FF0000")
            console.print(error_msg)
            console.print("[dim]Press Enter to exit...[/dim]")
            input()
            return False

    except Exception as e:
        error_msg = Text()
        error_msg.append("[", style="#c0c0c0")
        error_msg.append("Msk", style="dim")
        error_msg.append("] ", style="#c0c0c0")
        error_msg.append(f"Authentication error: {str(e)}", style="#FF0000")
        console.print(error_msg)
        console.print("[dim]Press Enter to exit...[/dim]")
        input()
        return False


if __name__ == "__main__":  
    from multiprocessing import freeze_support
    freeze_support()

    if ANTICRACK_AVAILABLE and init_anticrack:
        try:
            init_anticrack()
        except:
            pass
    
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("MSK Token Gen")
        except Exception:
            pass
    
    if not authenticate():
        sys.exit(0)
    
    result = intro()
    if result is None:
        sys.exit(0)
    
    token_count, headless = result
    
    config = Config.config
    config["headless"] = headless
    config["token_count"] = token_count
    Config.config = config
    
    config = Config.config
    
    Logger.start_logger()
    generator = TokenGenerator(
        num_workers=config.get("threads", 1),
        target_tokens=token_count
    )
    try:
        import MSK_core.Utils.keyauth as keyauth

        def _cli_stats():
            try:
                valid = int(generator.stats.get("valid", 0))
                invalid = int(generator.stats.get("invalid", 0))
                locked = int(generator.stats.get("locked", 0))
                
                gen_stats = {
                    "valid": valid,
                    "invalid": invalid,
                    "locked": locked,
                    "amount": int(getattr(generator, "target_tokens", 0) or 0),
                    "concurrent_browsers": int(getattr(generator, "num_workers", 0) or 0),
                    "tokens_attempted": int(getattr(generator, "tokens_attempted", 0) or 0),
                    "active_browsers": int(getattr(generator, "active_browsers", 0) or 0),
                    "should_stop": bool(getattr(generator, "should_stop", False)),
                    "start_time": float(generator.stats.get("start_time", 0.0)),
                }
            except Exception:
                gen_stats = {}

            return {
                "mode": "cli",
                "generator": gen_stats,
            }

        def _cli_sessions():
            try:
                with generator.lock:
                    workers = []
                    for wid, t in generator.threads.items():
                        workers.append(
                            {
                                "worker_id": int(wid),
                                "alive": bool(t.is_alive()),
                                "browser_closed": bool(generator.browser_closed_flags.get(wid, False)),
                            }
                        )
                    return {"active": len(generator.threads), "workers": sorted(workers, key=lambda x: x["worker_id"])}
            except Exception:
                return {"active": 0, "workers": []}

        keyauth.configure_local_api(get_stats=_cli_stats, get_sessions=_cli_sessions)
        keyauth.start_local_api()
    except Exception:
        pass

    try:
        generator.run()
    finally:
        try:
            import MSK_core.Utils.keyauth as keyauth

            keyauth.stop_local_api()
        except Exception:
            pass
