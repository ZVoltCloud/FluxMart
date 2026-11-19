import os
import sys
import time
from typing import Dict, Optional, List, Tuple
from datetime import datetime

try:
    import tls_client
except ImportError:
    tls_client = None

try:
    from pystyle import Colorate, Colors
except ImportError:
    Colorate = None
    Colors = None

from rich.console import Console
from rich.text import Text

import sys
import os

def _is_frozen() -> bool:
    if getattr(sys, 'frozen', False):
        return True
    try:
        return bool(__compiled__)
    except NameError:
        pass
    exe_name = os.path.basename(sys.executable).lower()
    if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw',
                         'python3.exe', 'python3'):
        return True
    return False

def get_base_path() -> str:
    if _is_frozen():
        _candidates = []
        try:
            _candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
        except Exception:
            pass
        try:
            _candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        except Exception:
            pass
        try:
            _candidates.append(os.getcwd())
        except Exception:
            pass
        _extended = []
        for _c in _candidates:
            _cur = _c
            for _ in range(4):
                if _cur not in _extended:
                    _extended.append(_cur)
                _parent = os.path.dirname(_cur)
                if _parent == _cur:
                    break
                _cur = _parent
        for _d in _extended:
            if os.path.isdir(os.path.join(_d, 'data')):
                return _d
        if _extended:
            return _extended[0]
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_resource_path(relative_path: str) -> str:
    return os.path.join(get_base_path(), relative_path)

console = Console()

TOKEN_FILE = get_resource_path("data/output/tokens.txt")
CHECKED_VALID_FILE = get_resource_path("data/output/checked_valid.txt")
CHECKED_INVALID_FILE = get_resource_path("data/output/checked_invalid.txt")


class TokenColors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    ORANGE = "\033[38;5;208m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    PURPLE = "\033[95m"
    RESET = "\033[0m"
    DIM = "\033[2m"
    BRACKET = "\033[38;2;192;192;192m"


def censor_token(token: str, visible_start: int = 6) -> str:
    if len(token) <= visible_start:
        return "***"
    return f"{token[:visible_start]}{'*' * 10}"


def extract_token(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    
    if ':' not in line:
        return line
        
    parts = line.split(':')
    
    import re
    token_pattern = re.compile(r'^[\w-]{24,}\.[\w-]{6,}\.[\w-]{25,}')
    
    # Check for perfect token match first
    for part in parts:
        part = part.strip()
        if token_pattern.search(part):
            return part
            
    candidates = [p.strip() for p in parts if '@' not in p]
    if candidates:
        for c in candidates:
            # Must have 2 dots to be a Discord token, not just 1 dot (which is a fingerprint)
            if c.count('.') >= 2 and len(c) > 50:
                return c
        # If no valid token is found, return the first part that looks like a token, or empty
        for c in candidates:
            if len(c) > 50 and '.' in c:
                return c
                
    return ""


def get_pystyle_colored_token(token: str, color_name: str) -> str:
    censored = censor_token(token)
    
    if Colorate is None or Colors is None:
        color_map = {
            "green": TokenColors.GREEN,
            "red": TokenColors.RED,
            "orange": TokenColors.ORANGE,
            "blue": TokenColors.BLUE,
            "yellow": TokenColors.YELLOW,
            "purple": TokenColors.PURPLE
        }
        color = color_map.get(color_name, TokenColors.GREEN)
        return f"{color}{censored}{TokenColors.RESET}"
    
    color_map = {
        "green": Colors.green,
        "red": Colors.red,
        "orange": Colors.orange,
        "blue": Colors.blue,
        "yellow": Colors.yellow,
        "purple": Colors.purple
    }
    
    color = color_map.get(color_name, Colors.green)
    return Colorate.Color(color, censored, True)


def check_token_safe(token: str, proxy: Optional[Dict[str, str]] = None) -> Dict[str, any]:
    result = {
        "valid": False,
        "banned": False,
        "locked": False,
        "phone_required": False,
        "email_required": False,
        "phone_verified": False,
        "email_verified": False,
        "nitro": False,
        "boost": False,
        "username": None,
        "discriminator": None,
        "id": None,
        "error": None
    }
    
    if tls_client is None:
        result["error"] = "tls_client not installed"
        return result
    
    session = tls_client.Session(
        client_identifier="chrome_136",
        random_tls_extension_order=True
    )
    
    if proxy:
        try:
            server_url = proxy.get('server', '').split('://')[-1]
            if 'username' in proxy and 'password' in proxy:
                proxy_url = f"http://{proxy['username']}:{proxy['password']}@{server_url}"
            else:
                proxy_url = f"http://{server_url}"
            session.proxies = {'http': proxy_url, 'https': proxy_url}
        except:
            pass
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": "America/New_York",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    
    try:
        r = session.get("https://discord.com/api/v9/users/@me", headers=headers)
        
        if r.status_code == 401:
            result["error"] = "Invalid token"
            return result
        
        if r.status_code == 429:
            result["error"] = "Rate limited"
            return result
        
        if r.status_code == 403:
            try:
                data = r.json()
                message = data.get("message", "").lower()
                code = data.get("code", 0)
                
                if code == 40002 or "verify your account" in message or "email" in message:
                    result["valid"] = True
                    result["email_required"] = True
                    return result
                elif code == 40003 or "phone" in message:
                    result["valid"] = True
                    result["phone_required"] = True
                    return result
                elif code in (40001, 20001, 20002, 50009):
                    # Explicit Discord ban/disable codes -- definitely disabled
                    result["banned"] = True
                    result["error"] = "Account disabled"
                    return result
                elif "unauthorized" in message or "banned" in message or "disabled" in message:
                    result["banned"] = True
                    result["error"] = "Account disabled"
                    return result
                else:
                    # Generic 403 without an explicit ban code.
                    # Discord returns 403 on /users/@me for datacenter/shared
                    # proxy IPs even for perfectly valid tokens. Do NOT mark as
                    # banned -- mark as valid but note the proxy issue.
                    result["valid"] = True
                    result["error"] = "403 from proxy IP (token may be valid)"
                    return result
            except:
                # JSON parse failed: probably a proxy/CDN block page, not Discord.
                # Do NOT mark as banned -- it's a network issue, not a token issue.
                result["error"] = "403 proxy block (retry without proxy)"
                return result
        
        if r.status_code != 200:
            result["error"] = f"Unknown error: {r.status_code}"
            return result
        
        user_data = r.json()
        result["valid"] = True
        result["username"] = user_data.get("username", "Unknown")
        result["discriminator"] = user_data.get("discriminator", "0")
        result["id"] = user_data.get("id")
        result["email_verified"] = user_data.get("verified", False)
        result["phone_verified"] = user_data.get("phone") is not None
        
        result["global_name"] = user_data.get("global_name", "")
        result["avatar_hash"] = user_data.get("avatar", "")
        
        flags = user_data.get("flags", 0) or 0
        public_flags = user_data.get("public_flags", 0) or 0
        
        all_flags = flags | public_flags
        hypesquad = ""
        if all_flags & 64: hypesquad = "Bravery"
        elif all_flags & 128: hypesquad = "Brilliance"
        elif all_flags & 256: hypesquad = "Balance"
        result["hypesquad"] = hypesquad
        
        premium_type = user_data.get("premium_type", 0)
        if premium_type and premium_type > 0:
            result["nitro"] = True
        
    except Exception as e:
        err_str = str(e).lower()
        # Detect connection-level errors -- these are caused by VPN/proxy
        # routing issues and do NOT indicate the token is invalid.
        _network_keywords = (
            'connection', 'timeout', 'timed out', 'network', 'ssl',
            'refused', 'reset', 'unreachable', 'eof', 'broken pipe',
            'remote end closed', 'errno', 'socket', 'proxy', 'tunnel',
            'nodename nor servname', 'getaddrinfo', 'name or service'
        )
        is_network_error = any(kw in err_str for kw in _network_keywords)

        if is_network_error and proxy:
            # Retry once without proxy -- the VPN is likely causing the issue
            try:
                session_retry = tls_client.Session(
                    client_identifier="chrome_136",
                    random_tls_extension_order=True
                )
                r_retry = session_retry.get(
                    "https://discord.com/api/v9/users/@me",
                    headers=headers
                )
                if r_retry.status_code == 401:
                    result["error"] = "Invalid token"
                    return result
                elif r_retry.status_code == 200:
                    user_data = r_retry.json()
                    result["valid"] = True
                    result["username"] = user_data.get("username", "Unknown")
                    result["discriminator"] = user_data.get("discriminator", "0")
                    result["id"] = user_data.get("id")
                    result["email_verified"] = user_data.get("verified", False)
                    result["phone_verified"] = user_data.get("phone") is not None
                    result["global_name"] = user_data.get("global_name", "")
                    result["avatar_hash"] = user_data.get("avatar", "")
                    flags = user_data.get("flags", 0) or 0
                    public_flags = user_data.get("public_flags", 0) or 0
                    all_flags = flags | public_flags
                    hypesquad = ""
                    if all_flags & 64: hypesquad = "Bravery"
                    elif all_flags & 128: hypesquad = "Brilliance"
                    elif all_flags & 256: hypesquad = "Balance"
                    result["hypesquad"] = hypesquad
                    premium_type = user_data.get("premium_type", 0)
                    if premium_type and premium_type > 0:
                        result["nitro"] = True
                    return result
                else:
                    # Still a network/proxy issue -- don't mark invalid
                    result["error"] = f"Network error (VPN?): proxy retry got {r_retry.status_code}"
                    return result
            except Exception as e2:
                # Both attempts failed with network errors — don't mark invalid
                result["error"] = f"Network error (VPN?): {str(e2)[:80]}"
                return result
        elif is_network_error:
            # No proxy was used — genuine network error, not a bad token
            result["error"] = f"Network error: {str(e)[:80]}"
            return result
        else:
            result["error"] = str(e)
            return result
    
    try:
        r2 = session.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers)
        if r2.status_code == 200:
            boost_data = r2.json()
            if boost_data and len(boost_data) > 0:
                for slot in boost_data:
                    if slot.get("premium_guild_subscription"):
                        result["boost"] = True
                        break
    except:
        pass
    
    try:
        r3 = session.get("https://discord.com/api/v9/users/@me/settings", headers=headers)
        if r3.status_code == 403:
            try:
                data = r3.json()
                message = data.get("message", "").lower()
                code = data.get("code", 0)

                if code == 40002 or "email" in message:
                    result["email_required"] = True
                elif code == 40003 or "phone" in message:
                    result["phone_required"] = True
                # Keep this separate so explicit lock responses are handled consistently.
                elif code in (40001, 40002, 40003, 20001, 20002):
                    # Known Discord lock codes — definitely locked
                    result["locked"] = True
                elif not result["email_verified"]:
                    # If email wasn't verified, that's the real lock cause
                    result["email_required"] = True
                # else: generic 403 from proxy IP rate-limiting — do NOT mark as locked.
                # Discord returns 403 on /settings for datacenter/shared proxy IPs even
                # for perfectly valid tokens. Only trust explicit lock codes above.
            except:
                # JSON parse failed: generic proxy block — do not set locked
                pass
    except:
        pass
    
    return result


def determine_token_color(result: Dict) -> str:
    if not result.get("valid"):
        return "red"
    
    if result.get("banned"):
        return "red"
    
    if result.get("locked") or result.get("email_required") or result.get("phone_required"):
        return "orange"
    
    if result.get("nitro") and result.get("boost"):
        return "purple"
    
    return "green"


def format_status_line(result: Dict) -> str:
    parts = []
    
    if result.get("email_required"):
        parts.append(f"{TokenColors.ORANGE}Email: Locked{TokenColors.RESET}")
    elif result.get("email_verified"):
        parts.append(f"{TokenColors.GREEN}Email: Verified{TokenColors.RESET}")
    else:
        parts.append(f"{TokenColors.DIM}Email: No{TokenColors.RESET}")
    
    if result.get("phone_required"):
        parts.append(f"{TokenColors.ORANGE}Phone: Locked{TokenColors.RESET}")
    elif result.get("phone_verified"):
        parts.append(f"{TokenColors.GREEN}Phone: Verified{TokenColors.RESET}")
    else:
        parts.append(f"{TokenColors.DIM}Phone: No{TokenColors.RESET}")
    
    if not result.get("valid"):
        parts.append(f"{TokenColors.RED}Status: Invalid{TokenColors.RESET}")
    elif result.get("banned"):
        parts.append(f"{TokenColors.RED}Status: Banned{TokenColors.RESET}")
    elif result.get("locked") or result.get("email_required") or result.get("phone_required"):
        parts.append(f"{TokenColors.ORANGE}Status: Locked{TokenColors.RESET}")
    else:
        parts.append(f"{TokenColors.GREEN}Status: Active{TokenColors.RESET}")
    
    if result.get("nitro"):
        parts.append(f"{TokenColors.PURPLE}Nitro: Yes{TokenColors.RESET}")
    else:
        parts.append(f"{TokenColors.DIM}Nitro: No{TokenColors.RESET}")
    
    if result.get("boost"):
        parts.append(f"{TokenColors.PURPLE}Boost: Yes{TokenColors.RESET}")
    else:
        parts.append(f"{TokenColors.DIM}Boost: No{TokenColors.RESET}")
    
    return " | ".join(parts)


def print_token_result(token: str, result: Dict):
    spacing = "                    "
    color_name = determine_token_color(result)
    colored_token = get_pystyle_colored_token(token, color_name)
    status_line = format_status_line(result)
    
    prefix = f"{TokenColors.BRACKET}[{TokenColors.RESET}{TokenColors.DIM}Msk{TokenColors.RESET}{TokenColors.BRACKET}]{TokenColors.RESET}"
    
    print(f"{spacing}{prefix} {colored_token} >> {status_line}")


def load_tokens() -> List[Tuple[str, str]]:
    tokens = []
    token_file = get_resource_path("data/output/tokens.txt")
    try:
        with open(token_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                token = extract_token(line)
                if token and len(token) > 50:
                    tokens.append((line, token))
    except FileNotFoundError:
        pass
    return tokens


def save_checked_tokens(valid_tokens: List[Tuple[str, Dict]], invalid_tokens: List[str]):
    valid_file = get_resource_path("data/output/checked_valid.txt")
    invalid_file = get_resource_path("data/output/checked_invalid.txt")
    
    os.makedirs(os.path.dirname(valid_file), exist_ok=True)
    
    with open(valid_file, 'w', encoding='utf-8') as f:
        for token, result in valid_tokens:
            status_parts = []
            if result.get("nitro"):
                status_parts.append("NITRO")
            if result.get("boost"):
                status_parts.append("BOOST")
            if result.get("locked"):
                status_parts.append("LOCKED")
            if not result.get("email_verified"):
                status_parts.append("EMAIL_UNVERIFIED")
            if not result.get("phone_verified"):
                status_parts.append("PHONE_UNVERIFIED")
            
            status = ",".join(status_parts) if status_parts else "CLEAN"
            f.write(f"{token} | {status}\n")
    
    with open(invalid_file, 'w', encoding='utf-8') as f:
        for token in invalid_tokens:
            f.write(f"{token}\n")


def run_token_checker():
    os.system("cls" if os.name == "nt" else "clear")
    
    from MSK_core.Utils.intro import display_banner
    display_banner()
    
    spacing = "                    "
    
    console.print()
    console.print(f"{spacing}[#c0c0c0]Token Checker[/#c0c0c0] [dim]- Safe Mode[/dim]")
    console.print()
    
    tokens = load_tokens()
    
    if not tokens:
        console.print(f"{spacing}[red]No tokens found in {TOKEN_FILE}[/red]")
        console.print()
        input(f"{spacing}Press Enter to go back...")
        return
    
    console.print(f"{spacing}[dim]Found[/dim] [#c0c0c0]{len(tokens)}[/#c0c0c0] [dim]tokens to check[/dim]")
    console.print()
    
    valid_tokens = []
    invalid_tokens = []
    
    stats = {
        "total": len(tokens),
        "valid": 0,
        "banned": 0,
        "locked": 0,
        "nitro": 0,
        "boost": 0,
        "email_unverified": 0,
        "phone_unverified": 0
    }
    
    for i, (original_line, token) in enumerate(tokens):
        result = check_token_safe(token)
        
        print_token_result(token, result)
        
        if result.get("valid"):
            stats["valid"] += 1
            valid_tokens.append((original_line, result))
            
            if result.get("nitro"):
                stats["nitro"] += 1
            if result.get("boost"):
                stats["boost"] += 1
            if result.get("locked"):
                stats["locked"] += 1
            if not result.get("email_verified"):
                stats["email_unverified"] += 1
            if not result.get("phone_verified"):
                stats["phone_unverified"] += 1
        else:
            if result.get("banned"):
                stats["banned"] += 1
            invalid_tokens.append(original_line)
        
        time.sleep(0.5)
    
    save_checked_tokens(valid_tokens, invalid_tokens)
    
    console.print()
    console.print(f"{spacing}[#c0c0c0]═══════════════════════════════════════════════════════[/#c0c0c0]")
    console.print()
    console.print(f"{spacing}[dim][[/dim][#c0c0c0]Summary[/#c0c0c0][dim]][/dim]")
    console.print(f"{spacing}  Total: [white]{stats['total']}[/white] | Valid: [green]{stats['valid']}[/green] | Banned: [red]{stats['banned']}[/red] | Locked: [#ff8c00]{stats['locked']}[/#ff8c00]")
    console.print(f"{spacing}  Nitro: [#c0c0c0]{stats['nitro']}[/#c0c0c0] | Boost: [#c0c0c0]{stats['boost']}[/#c0c0c0]")
    console.print(f"{spacing}  Email Unverified: [blue]{stats['email_unverified']}[/blue] | Phone Unverified: [yellow]{stats['phone_unverified']}[/yellow]")
    console.print()
    console.print(f"{spacing}[dim]Results saved to:[/dim]")
    console.print(f"{spacing}  [green]{CHECKED_VALID_FILE}[/green]")
    console.print(f"{spacing}  [red]{CHECKED_INVALID_FILE}[/red]")
    console.print()
    
    input(f"{spacing}Press Enter to go back...")
