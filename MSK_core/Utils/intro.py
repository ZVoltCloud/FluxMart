import os
import sys
import time
import json

from rich.console import Console
from rich.text import Text
from MSK_core.Utils.utils import get_config_path, load_config as utils_load_config, save_config as utils_save_config

console = Console()

TOKEN_FILE = "data/output/tokens.txt"
PROXY_FILE = "data/input/proxies.txt"


def _find_data_file(relative_path: str) -> str:
    """Locate a data file using multiple resolution strategies (EXE-safe)."""
    candidates = []
    try:
        from MSK_core.Utils.utils import get_base_path
        candidates.append(os.path.join(get_base_path(), relative_path))
    except Exception:
        pass
    candidates.append(os.path.join(os.path.dirname(sys.executable), relative_path))
    candidates.append(os.path.join(os.getcwd(), relative_path))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0] if candidates else relative_path


def count_lines(filepath):
    try:
        if not os.path.isabs(filepath):
            filepath = _find_data_file(filepath)
        with open(filepath, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
            return len(lines)
    except FileNotFoundError:
        return 0


def load_config():
    """Load config using proper path resolution for EXE compatibility."""
    return utils_load_config()


def save_config(config):
    """Save config using proper path resolution for EXE compatibility."""
    if not utils_save_config(config):
        console.print(f"      [red]Failed to save config[/red]")


def display_banner():
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
        "#FFFFFF",
        "#F5F5F5",
        "#E8E8E8",
        "#DBDBDB",
        "#CCCCCC",
        "#BFBFBF",
        "#B2B2B2",
        "#A6A6A6",
        "#999999",
        "#8C8C8C"
    ]

    for i, line in enumerate(banner_lines):
        console.print(spacing + line, style=gradient_colors[i])

    console.print()


def display_stats():
    spacing = "                    "
    
    from MSK_core.Utils.utils import get_base_path
    token_file_path = os.path.join(get_base_path(), TOKEN_FILE)
    proxy_file_path = os.path.join(get_base_path(), PROXY_FILE)
    
    token_count = count_lines(token_file_path)
    proxy_count = count_lines(proxy_file_path)

    stats_text = Text()
    stats_text.append(spacing, style="")
    stats_text.append("[", style="dim")
    stats_text.append("Tokens", style="#c0c0c0")
    stats_text.append("]", style="dim")
    stats_text.append(" >> ", style="white")
    stats_text.append(str(token_count), style="#e0e0e0")
    stats_text.append(" - ", style="white")
    stats_text.append("[", style="dim")
    stats_text.append("Proxies", style="#c0c0c0")
    stats_text.append("]", style="dim")
    stats_text.append(" >> ", style="white")
    stats_text.append(str(proxy_count), style="#e0e0e0")
    stats_text.append(" - ", style="white")
    stats_text.append("[", style="dim")
    stats_text.append("Version", style="#c0c0c0")
    stats_text.append("]", style="dim")
    stats_text.append(" >> ", style="white")
    stats_text.append("3.3.4", style="#e0e0e0")
    stats_text.append(" - ", style="white")
    stats_text.append("msktool.shop", style="dim")

    console.print(stats_text)
    console.print()


def display_menu():
    menu_grid = [
        [("[01]", "Token Generator"), ("[02]", "Token Checker"), ("[03]", "Settings")],
    ]

    bracket_colors = ["#c0c0c0", "#b0b0b0", "#a0a0a0", "#909090", "#808080"]

    for row_idx, row in enumerate(menu_grid):
        line = Text()
        bracket_color = bracket_colors[row_idx] if row_idx < len(bracket_colors) else "#a0a0a0"

        line.append("                    ", style="")

        for num, name in row:
            bracket_open = num[0]
            number = num[1:-1]
            bracket_close = num[-1]

            line.append(bracket_open, style=bracket_color)
            line.append(number, style="bright_black")
            line.append(bracket_close + " ", style=bracket_color)
            line.append(f"{name:<17} ", style="white")
        console.print(line)

    console.print()


def styled_input(prompt_text):
    prompt = Text()
    prompt.append("                    ", style="")
    prompt.append("[", style="#c0c0c0")
    prompt.append("Msk", style="dim")
    prompt.append("] ", style="#c0c0c0")
    prompt.append(prompt_text, style="white")
    console.print(prompt, end="")
    return input().strip()


def styled_yn_prompt(prompt_text):
    prompt = Text()
    prompt.append("                    ", style="")
    prompt.append("[", style="#c0c0c0")
    prompt.append("Msk", style="dim")
    prompt.append("] ", style="#c0c0c0")
    prompt.append(prompt_text, style="white")
    prompt.append(" (", style="dim")
    prompt.append("y", style="green")
    prompt.append("/", style="dim")
    prompt.append("n", style="red")
    prompt.append(")", style="dim")
    prompt.append(": ", style="white")
    console.print(prompt, end="")
    return input().strip().lower()


def get_menu_choice():
    while True:
        choice = styled_input("Choice : ")
        if choice in ["1", "01"]:
            return 1
        elif choice in ["2", "02"]:
            return 2
        elif choice in ["3", "03"]:
            return 3
        else:
            console.print("                    [red]Invalid choice. Please enter 1, 2, or 3.[/red]")


def token_generator_setup():
    config = load_config()
    
    console.print()
    
    while True:
        token_count = styled_input("How many tokens do you want to generate : ")
        try:
            token_count = int(token_count)
            if token_count > 0:
                break
            else:
                console.print("                    [red]Please enter a positive number.[/red]")
        except ValueError:
            console.print("                    [red]Please enter a valid number.[/red]")
    
    auto_solver = config.get("auto_solver_captcha", True)
    
    if auto_solver:
        headless_choice = styled_yn_prompt("You want it headless")
        headless = headless_choice == "y"
        config["headless"] = headless
    else:
        config["headless"] = False
        console.print("                    [dim]Headless mode disabled (auto_solver_captcha is false)[/dim]")
    
    config["token_count"] = token_count
    save_config(config)
    
    console.print()
    return token_count, config["headless"]


def token_checker_menu():
    from MSK_core.WorkFlow.token_checker import run_token_checker
    run_token_checker()
    return None


def settings_menu():
    while True:
        config = load_config()
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]Settings[/#c0c0c0]")
        console.print()
        
        if "rate_limit_checker" not in config:
            config["rate_limit_checker"] = {}
        if "humanizer" not in config:
            config["humanizer"] = {}
        if "ai_api" not in config:
            config["ai_api"] = {"cloudflare": {"account_id": "f0f083c448327b55239ec74ab50528df", "api_key": "yourkey", "model": "@cf/openai/gpt-oss-120b"}, "openrouter": {"api_key": "", "model": "liquid/lfm3-1.7b:free"}, "groq": {"api_key": "", "model": "openai/gpt-oss-120b"}}
        if "solver_ai" not in config:
            config["solver_ai"] = {"cloudflare": True, "groq": False, "openrouter": False}
        if "proxies" not in config:
            config["proxies"] = {"enabled": False}
        if "logs" not in config:
            config["logs"] = {
                "censor_token": True,
                "generation_time": True,
                "startup_time": True,
                "hcaptcha_waiting": True,
                "hcaptcha_solving": True,
                "humanize_time": True,
                "verify_time": True,
                "total_time": True
            }
        
        auto_solver_status = "[green]Enabled[/green]" if config.get("auto_solver_captcha", True) else "[red]Disabled[/red]"
        headless_status = "[green]Enabled[/green]" if config.get("headless", False) else "[red]Disabled[/red]"
        rate_limit_status = "[green]Enabled[/green]" if config.get("rate_limit_checker", {}).get("enabled", False) else "[red]Disabled[/red]"
        humanizer_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("enabled", False) else "[red]Disabled[/red]"
        mullvad_status = "[green]Enabled[/green]" if config.get("mullvad", False) else "[red]Disabled[/red]"
        proxies_status = "[green]Enabled[/green]" if config.get("proxies", {}).get("enabled", False) else "[red]Disabled[/red]"
        
        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Auto Captcha Solver    : {auto_solver_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]2[/#c0c0c0][dim]][/dim] Headless Mode          : {headless_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]3[/#c0c0c0][dim]][/dim] Rate Limit Checker     : {rate_limit_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]4[/#c0c0c0][dim]][/dim] Humanizer              : {humanizer_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]5[/#c0c0c0][dim]][/dim] Mullvad Bypass         : {mullvad_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]6[/#c0c0c0][dim]][/dim] Proxies                : {proxies_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]7[/#c0c0c0][dim]][/dim] Threads                : {config.get('threads', 1)}")
        console.print(f"                    [dim][[/dim][#c0c0c0]8[/#c0c0c0][dim]][/dim] Captcha Timeout        : {config.get('captcha_timeout', 30)}s")
        fivesim_status = "[green]Enabled[/green]" if config.get("fivesim", {}).get("enabled", False) else "[red]Disabled[/red]"
        
        console.print(f"                    [dim][[/dim][#c0c0c0]9[/#c0c0c0][dim]][/dim] API Keys & Models")
        console.print(f"                    [dim][[/dim][#c0c0c0]10[/#c0c0c0][dim]][/dim] Humanizer Options")
        console.print(f"                    [dim][[/dim][#c0c0c0]11[/#c0c0c0][dim]][/dim] Log Options")
        console.print(f"                    [dim][[/dim][#c0c0c0]12[/#c0c0c0][dim]][/dim] Solver AI Options")
        console.print(f"                    [dim][[/dim][#c0c0c0]13[/#c0c0c0][dim]][/dim] 5sim Phone Verify     : {fivesim_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        if choice == "1":
            config["auto_solver_captcha"] = not config.get("auto_solver_captcha", True)
            save_config(config)
        elif choice == "2":
            config["headless"] = not config.get("headless", False)
            save_config(config)
        elif choice == "3":
            config["rate_limit_checker"]["enabled"] = not config.get("rate_limit_checker", {}).get("enabled", False)
            save_config(config)
        elif choice == "4":
            config["humanizer"]["enabled"] = not config.get("humanizer", {}).get("enabled", False)
            save_config(config)
        elif choice == "5":
            config["mullvad"] = not config.get("mullvad", False)
            save_config(config)
        elif choice == "6":
            config["proxies"]["enabled"] = not config.get("proxies", {}).get("enabled", False)
            save_config(config)
        elif choice == "7":
            while True:
                threads_input = styled_input(f"Enter threads (current: {config.get('threads', 1)}) : ")
                try:
                    threads = int(threads_input)
                    if threads > 0:
                        config["threads"] = threads
                        save_config(config)
                        break
                    else:
                        console.print("                    [red]Please enter a positive number.[/red]")
                except ValueError:
                    console.print("                    [red]Please enter a valid number.[/red]")
        elif choice == "8":
            while True:
                timeout_input = styled_input(f"Enter captcha timeout in seconds (current: {config.get('captcha_timeout', 30)}) : ")
                try:
                    timeout = int(timeout_input)
                    if timeout > 0:
                        config["captcha_timeout"] = timeout
                        save_config(config)
                        break
                    else:
                        console.print("                    [red]Please enter a positive number.[/red]")
                except ValueError:
                    console.print("                    [red]Please enter a valid number.[/red]")
        elif choice == "9":
            api_keys_menu(config)
        elif choice == "10":
            humanizer_options_menu(config)
        elif choice == "11":
            log_options_menu(config)
        elif choice == "12":
            solver_ai_options_menu(config)
        elif choice == "13":
            fivesim_options_menu(config)
        elif choice == "0":
            return None
    
    return None


def fivesim_options_menu(config):
    """Sub-menu for 5sim phone verification options."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]5sim Phone Verification[/#c0c0c0]")
        console.print()
        
        if "fivesim" not in config:
            config["fivesim"] = {
                "enabled": False,
                "api_key": "",
                "number_limit": 2,
                "country": "england",
                "operator": "any"
            }
        
        fivesim_enabled = "[green]Enabled[/green]" if config.get("fivesim", {}).get("enabled", False) else "[red]Disabled[/red]"
        fivesim_key = config.get("fivesim", {}).get("api_key", "")
        fivesim_display = f"{fivesim_key[:8]}...{fivesim_key[-4:]}" if len(fivesim_key) > 12 else "None"
        number_limit = config.get("fivesim", {}).get("number_limit", 2)
        country = config.get("fivesim", {}).get("country", "england")
        operator = config.get("fivesim", {}).get("operator", "any")
        
        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Enable 5sim           : {fivesim_enabled}")
        console.print(f"                    [dim][[/dim][#c0c0c0]2[/#c0c0c0][dim]][/dim] API Key               : {fivesim_display}")
        console.print(f"                    [dim][[/dim][#c0c0c0]3[/#c0c0c0][dim]][/dim] Number Limit          : {number_limit}")
        console.print(f"                    [dim][[/dim][#c0c0c0]4[/#c0c0c0][dim]][/dim] Country               : {country}")
        console.print(f"                    [dim][[/dim][#c0c0c0]5[/#c0c0c0][dim]][/dim] Operator              : {operator}")
        console.print(f"                    [dim][[/dim][#c0c0c0]6[/#c0c0c0][dim]][/dim] Test API Key")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        if choice == "1":
            config["fivesim"]["enabled"] = not config.get("fivesim", {}).get("enabled", False)
            save_config(config)
        elif choice == "2":
            new_key = styled_input("Enter 5sim API Key : ")
            config["fivesim"]["api_key"] = new_key
            save_config(config)
        elif choice == "3":
            while True:
                limit_input = styled_input(f"Enter number limit (current: {number_limit}, 0 = unlimited) : ")
                try:
                    limit = int(limit_input)
                    if limit >= 0:
                        config["fivesim"]["number_limit"] = limit
                        save_config(config)
                        break
                    else:
                        console.print("                    [red]Please enter a non-negative number.[/red]")
                except ValueError:
                    console.print("                    [red]Please enter a valid number.[/red]")
        elif choice == "4":
            new_country = styled_input(f"Enter country code (current: {country}, 'any' for all) : ")
            config["fivesim"]["country"] = new_country if new_country else "any"
            save_config(config)
        elif choice == "5":
            new_operator = styled_input(f"Enter operator (current: {operator}, 'any' for all) : ")
            config["fivesim"]["operator"] = new_operator if new_operator else "any"
            save_config(config)
        elif choice == "6":
            api_key = config.get("fivesim", {}).get("api_key", "")
            if not api_key:
                console.print("                    [red]Please set an API key first.[/red]")
                time.sleep(2)
            else:
                console.print("                    [dim]Testing API key...[/dim]")
                try:
                    from MSK_core.Utils.fivesim import FiveSimAPI
                    api = FiveSimAPI(api_key)
                    valid, message, balance = api.validate_api_key()
                    if valid:
                        console.print(f"                    [green]API Key Valid! Balance: {balance}[/green]")
                    else:
                        console.print(f"                    [red]{message}[/red]")
                except Exception as e:
                    console.print(f"                    [red]Error: {e}[/red]")
                time.sleep(3)
        elif choice == "0":
            return


def api_keys_menu(config):
    """Sub-menu for API keys and models."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]API Keys & Models[/#c0c0c0]")
        console.print()

        cybertemp_key = config.get("cybertemp_api_key", "")
        cybertemp_display = f"{cybertemp_key[:8]}...{cybertemp_key[-4:]}" if len(cybertemp_key) > 12 else "None"
        
        openrouter_key = config.get("ai_api", {}).get("openrouter", {}).get("api_key", "")
        openrouter_display = f"{openrouter_key[:8]}...{openrouter_key[-4:]}" if len(openrouter_key) > 12 else "None"
        openrouter_model = config.get("ai_api", {}).get("openrouter", {}).get("model", "nvidia/nemotron-3-super-120b-a12b:free")
        
        groq_key = config.get("ai_api", {}).get("groq", {}).get("api_key", "")
        groq_display = f"{groq_key[:8]}...{groq_key[-4:]}" if len(groq_key) > 12 else "None"
        groq_model = config.get("ai_api", {}).get("groq", {}).get("model", "llama-3.3-70b-versatile")
        
        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Cybertemp API Key      : {cybertemp_display}")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        if choice == "1":
            new_key = styled_input(f"Enter Cybertemp API Key (current: {cybertemp_display}) : ")
            config["cybertemp_api_key"] = new_key
            save_config(config)
        elif choice == "2":
            new_key = styled_input(f"Enter OpenRouter API Key (current: {openrouter_display}) : ")
            if "ai_api" not in config:
                config["ai_api"] = {}
            if "openrouter" not in config["ai_api"]:
                config["ai_api"]["openrouter"] = {}
            config["ai_api"]["openrouter"]["api_key"] = new_key
            save_config(config)
        elif choice == "3":
            new_model = styled_input(f"Enter OpenRouter Model (current: {openrouter_model}) : ")
            if "ai_api" not in config:
                config["ai_api"] = {}
            if "openrouter" not in config["ai_api"]:
                config["ai_api"]["openrouter"] = {}
            config["ai_api"]["openrouter"]["model"] = new_model
            save_config(config)
        elif choice == "4":
            new_key = styled_input(f"Enter Groq API Key (current: {groq_display}) : ")
            if "ai_api" not in config:
                config["ai_api"] = {}
            if "groq" not in config["ai_api"]:
                config["ai_api"]["groq"] = {}
            config["ai_api"]["groq"]["api_key"] = new_key
            save_config(config)
        elif choice == "5":
            new_model = styled_input(f"Enter Groq Model (current: {groq_model}) : ")
            if "ai_api" not in config:
                config["ai_api"] = {}
            if "groq" not in config["ai_api"]:
                config["ai_api"]["groq"] = {}
            config["ai_api"]["groq"]["model"] = new_model
            save_config(config)
        elif choice == "0":
            return


def humanizer_options_menu(config):
    """Sub-menu for humanizer options."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]Humanizer Options[/#c0c0c0]")
        console.print()
        
        if "humanizer" not in config:
            config["humanizer"] = {}
        
        avatar_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("avatar", True) else "[red]Disabled[/red]"
        pronouns_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("pronouns", True) else "[red]Disabled[/red]"
        bio_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("bio", True) else "[red]Disabled[/red]"
        hypesquad_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("hypesquad", True) else "[red]Disabled[/red]"
        display_name_status = "[green]Enabled[/green]" if config.get("humanizer", {}).get("display_name", True) else "[red]Disabled[/red]"
        
        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Avatar       : {avatar_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]2[/#c0c0c0][dim]][/dim] Pronouns     : {pronouns_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]3[/#c0c0c0][dim]][/dim] Bio          : {bio_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]4[/#c0c0c0][dim]][/dim] Hypesquad    : {hypesquad_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]5[/#c0c0c0][dim]][/dim] Display Name : {display_name_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        if choice == "1":
            config["humanizer"]["avatar"] = not config.get("humanizer", {}).get("avatar", True)
            save_config(config)
        elif choice == "2":
            config["humanizer"]["pronouns"] = not config.get("humanizer", {}).get("pronouns", True)
            save_config(config)
        elif choice == "3":
            config["humanizer"]["bio"] = not config.get("humanizer", {}).get("bio", True)
            save_config(config)
        elif choice == "4":
            config["humanizer"]["hypesquad"] = not config.get("humanizer", {}).get("hypesquad", True)
            save_config(config)
        elif choice == "5":
            config["humanizer"]["display_name"] = not config.get("humanizer", {}).get("display_name", True)
            save_config(config)
        elif choice == "0":
            return


def log_options_menu(config):
    """Sub-menu for log options."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]Log Options[/#c0c0c0]")
        console.print()

        log_config = config.get("logs", {})
        censor_status = "[green]Enabled[/green]" if log_config.get("censor_token", True) else "[red]Disabled[/red]"
        gen_time_status = "[green]Enabled[/green]" if log_config.get("generation_time", True) else "[red]Disabled[/red]"
        startup_time_status = "[green]Enabled[/green]" if log_config.get("startup_time", True) else "[red]Disabled[/red]"
        hcaptcha_wait_status = "[green]Enabled[/green]" if log_config.get("hcaptcha_waiting", True) else "[red]Disabled[/red]"
        hcaptcha_solve_status = "[green]Enabled[/green]" if log_config.get("hcaptcha_solving", True) else "[red]Disabled[/red]"
        humanize_time_status = "[green]Enabled[/green]" if log_config.get("humanize_time", True) else "[red]Disabled[/red]"
        verify_time_status = "[green]Enabled[/green]" if log_config.get("verify_time", True) else "[red]Disabled[/red]"
        total_time_status = "[green]Enabled[/green]" if log_config.get("total_time", True) else "[red]Disabled[/red]"

        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Censor Token      : {censor_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]2[/#c0c0c0][dim]][/dim] Generation Time   : {gen_time_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]3[/#c0c0c0][dim]][/dim] Startup Time      : {startup_time_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]4[/#c0c0c0][dim]][/dim] hCaptcha Waiting  : {hcaptcha_wait_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]5[/#c0c0c0][dim]][/dim] hCaptcha Solving  : {hcaptcha_solve_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]6[/#c0c0c0][dim]][/dim] Humanize Time     : {humanize_time_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]7[/#c0c0c0][dim]][/dim] Verify Time       : {verify_time_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]8[/#c0c0c0][dim]][/dim] Total Time        : {total_time_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        if choice == "1":
            config["logs"]["censor_token"] = not config.get("logs", {}).get("censor_token", True)
            save_config(config)
        elif choice == "2":
            config["logs"]["generation_time"] = not config.get("logs", {}).get("generation_time", True)
            save_config(config)
        elif choice == "3":
            config["logs"]["startup_time"] = not config.get("logs", {}).get("startup_time", True)
            save_config(config)
        elif choice == "4":
            config["logs"]["hcaptcha_waiting"] = not config.get("logs", {}).get("hcaptcha_waiting", True)
            save_config(config)
        elif choice == "5":
            config["logs"]["hcaptcha_solving"] = not config.get("logs", {}).get("hcaptcha_solving", True)
            save_config(config)
        elif choice == "6":
            config["logs"]["humanize_time"] = not config.get("logs", {}).get("humanize_time", True)
            save_config(config)
        elif choice == "7":
            config["logs"]["verify_time"] = not config.get("logs", {}).get("verify_time", True)
            save_config(config)
        elif choice == "8":
            config["logs"]["total_time"] = not config.get("logs", {}).get("total_time", True)
            save_config(config)
        elif choice == "0":
            return


def solver_ai_options_menu(config):
    """Sub-menu for solver AI options."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()
        
        console.print("                    [#c0c0c0]Solver AI Options[/#c0c0c0]")
        console.print("                    [dim]Only one solver can be active at a time.[/dim]")
        console.print()
        
        if "solver_ai" not in config:
            config["solver_ai"] = {"cloudflare": True, "groq": False, "openrouter": False}
        
        cloudflare_status = "[green]Enabled[/green]" if config.get("solver_ai", {}).get("cloudflare", False) else "[red]Disabled[/red]"
        groq_status = "[green]Enabled[/green]" if config.get("solver_ai", {}).get("groq", False) else "[red]Disabled[/red]"
        openrouter_status = "[green]Enabled[/green]" if config.get("solver_ai", {}).get("openrouter", False) else "[red]Disabled[/red]"
        
        console.print(f"                    [dim][[/dim][#c0c0c0]1[/#c0c0c0][dim]][/dim] Cloudflare      : {cloudflare_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]2[/#c0c0c0][dim]][/dim] Groq            : {groq_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]3[/#c0c0c0][dim]][/dim] OpenRouter      : {openrouter_status}")
        console.print(f"                    [dim][[/dim][#c0c0c0]0[/#c0c0c0][dim]][/dim] Back")
        console.print()
        
        choice = styled_input("Choice : ")
        
        solvers = ["cloudflare", "groq", "openrouter"]
        solver_map = {"1": "cloudflare", "2": "groq", "3": "openrouter"}
        
        if choice in solver_map:
            selected = solver_map[choice]
            is_currently_enabled = config.get("solver_ai", {}).get(selected, False)
            if is_currently_enabled:
                config["solver_ai"][selected] = False
            else:
                for s in solvers:
                    config["solver_ai"][s] = (s == selected)
            save_config(config)
        elif choice == "0":
            return


def display_changelog():
    """Display v3.3.5 changelog."""
    spacing = "                    "
    console.print(f"{spacing}[dim]─── What's new in v3.3.5 ───────────────────────────────────[/dim]")
    changelog = [
        ("remove", "Removed Ollama (not working for free anymore)"),
        ("fix", "OpenRouter now enabled by default for captcha solving"),
        ("fix", "Improved OpenRouter integration and error handling"),
        ("fix", "Chromium/Clearcote year dropdown: improved reliability & exact match"),
        ("fix", "Mullvad flagged servers persist across restarts (no repeated bad IPs)"),
        ("fix", "Clearcote log format now matches Brave/Chromium output"),
    ]
    for tag, msg in changelog:
        color = "#13A10E" if tag == "add" else "#5B36B8" if tag == "fix" else "#c0c0c0"
        label = "ADD" if tag == "add" else "FIX"
        console.print(f"{spacing}[{color}][{label}][/{color}] [dim]{msg}[/dim]")
    console.print(f"{spacing}[dim]──────────────────────────────────────────────────────────[/dim]")
    console.print()


def intro():
    os.system("cls" if os.name == "nt" else "clear")
    display_banner()
    display_stats()
    display_changelog()
    display_menu()
    
    choice = get_menu_choice()
    
    if choice == 1:
        return token_generator_setup()
    elif choice == 2:
        token_checker_menu()
        return intro()
    elif choice == 3:
        settings_menu()
        return intro()
    
    return None


silver_gradient = [
    '\033[38;2;192;192;192m',
    '\033[38;2;169;169;169m',
    '\033[38;2;144;144;144m',
    '\033[38;2;128;128;128m',
]
