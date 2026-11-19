import subprocess
import time
import re
import random
import threading
import json
import os
from typing import Optional, Tuple, List, Dict
from rich.console import Console

console = Console()
def _is_frozen() -> bool:
    if getattr(__import__('sys'), 'frozen', False):
        return True
    try:
        return bool(__compiled__)
    except NameError:
        pass
    import os
    exe_name = os.path.basename(__import__('sys').executable).lower()
    if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw',
                         'python3.exe', 'python3'):
        return True
    return False

_NO_WINDOW: int = 0x08000000 if __import__('sys').platform == 'win32' else 0

class MullvadManager:
    DISCORD_BLOCKED_SERVERS = [
        "us-nyc",
        "us-lax",
        "us-sea",
    ]
    
    PREFERRED_SERVERS = [
        "se-sto",
        "se-got",
        "se-mma",
        "ch-zrh",
        "de-ber",
        "de-fra",
        "nl-ams",
        "gb-lon",
        "at-vie",
        "be-bru",
        "cz-prg",
        "dk-cph",
        "fi-hel",
        "no-osl",
        "pl-waw",
        "ro-buc",
        "es-mad",
        "it-mil",
    ]
    
    _current_server_index = 0
    _used_servers = []
    _lock = threading.Lock()
    _bad_ips: set = set()
    _bad_ips_loaded: bool = False
    _verified_clean_servers: list = []
    _relay_ip_map: Dict[str, str] = {}
    _relay_ip_map_time: float = 0
    _flagged_relays: set = set()
    _flagged_relays_loaded: bool = False

    @staticmethod
    def _get_flagged_relays_path() -> str:
        try:
            import sys
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(base, "data", "credentials", "flagged_relays.json")
        except Exception:
            return "data/credentials/flagged_relays.json"

    @staticmethod
    def _get_bad_ips_path() -> str:
        try:
            import sys
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(base, "data", "credentials", "bad_ips.json")
        except Exception:
            return "data/credentials/bad_ips.json"

    @staticmethod
    def _load_bad_ips() -> None:
        if MullvadManager._bad_ips_loaded:
            return
        try:
            path = MullvadManager._get_bad_ips_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                MullvadManager._bad_ips = set(data.get("bad_ips", []))
        except Exception:
            pass
        MullvadManager._bad_ips_loaded = True

    @staticmethod
    def _save_bad_ips() -> None:
        try:
            path = MullvadManager._get_bad_ips_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"bad_ips": sorted(MullvadManager._bad_ips)}, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def flag_bad_ip(ip: str) -> None:
        """Permanently flag an IP so it is never used again."""
        if not ip or ip.startswith("via "):
            return
        MullvadManager._load_bad_ips()
        if ip not in MullvadManager._bad_ips:
            MullvadManager._bad_ips.add(ip)
            MullvadManager._save_bad_ips()

    @staticmethod
    def is_ip_flagged(ip: str) -> bool:
        """Check if an IP was previously flagged as bad."""
        if not ip or ip.startswith("via "):
            return False
        MullvadManager._load_bad_ips()
        return ip in MullvadManager._bad_ips

    @staticmethod
    def _get_flagged_relays_path() -> str:
        try:
            import sys
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(base, "data", "credentials", "flagged_relays.json")
        except Exception:
            return "data/credentials/flagged_relays.json"

    @staticmethod
    def _load_flagged_relays() -> None:
        if MullvadManager._flagged_relays_loaded:
            return
        try:
            path = MullvadManager._get_flagged_relays_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                MullvadManager._flagged_relays = set(data.get("flagged_relays", []))
        except Exception:
            MullvadManager._flagged_relays = set()
        MullvadManager._flagged_relays_loaded = True
        # Also load persisted bad IPs on startup
        MullvadManager._load_bad_ips()

    @staticmethod
    def _save_flagged_relays() -> None:
        try:
            path = MullvadManager._get_flagged_relays_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"flagged_relays": sorted(MullvadManager._flagged_relays)}, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def flag_relay(relay_id: str, reason: str = "") -> None:
        """Permanently flag a relay ID so it is never used again."""
        if not relay_id:
            return
        MullvadManager._load_flagged_relays()
        if relay_id not in MullvadManager._flagged_relays:
            MullvadManager._flagged_relays.add(relay_id)
            MullvadManager._save_flagged_relays()

    @staticmethod
    def get_current_relay_id() -> Optional[str]:
        """Get the relay server ID from the current Mullvad connection."""
        try:
            success, output = MullvadManager._run_command(["mullvad", "status"])
            if success:
                relay_m = re.search(r'Relay:\s+(\S+)', output)
                if relay_m:
                    return relay_m.group(1)
        except Exception:
            pass
        return None

    @staticmethod
    def _build_relay_ip_map(force: bool = False) -> Dict[str, str]:
        """Parse 'mullvad relay list' to map relay_id -> IP. Cached for 10 minutes."""
        now = time.time()
        if not force and MullvadManager._relay_ip_map and (now - MullvadManager._relay_ip_map_time) < 600:
            return MullvadManager._relay_ip_map
        try:
            success, output = MullvadManager._run_command(["mullvad", "relay", "list"])
            if success:
                mapping = {}
                for line in output.split('\n'):
                    m = re.search(r'(\w{2}-\w{3}-\w{2}-\d+)\s+\(([\d.]+)', line)
                    if m:
                        mapping[m.group(1)] = m.group(2)
                if mapping:
                    MullvadManager._relay_ip_map = mapping
                    MullvadManager._relay_ip_map_time = now
                    return mapping
        except Exception:
            pass
        return MullvadManager._relay_ip_map
    
    @staticmethod
    def _run_command(command: List[str], timeout: int = 30) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=_NO_WINDOW
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except FileNotFoundError:
            return False, "Mullvad CLI not found"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_current_ip() -> Optional[str]:
        success, output = MullvadManager._run_command(["mullvad", "status"])
        if success:
            ip_match = re.search(r'IPv4:\s*(\d+\.\d+\.\d+\.\d+)', output)
            if ip_match:
                return ip_match.group(1)
            relay_match = re.search(r'Connected to\s+(\S+)', output)
            if relay_match:
                try:
                    import socket
                    relay = relay_match.group(1)
                    return f"via {relay}"
                except:
                    pass
        try:
            import urllib.request
            with urllib.request.urlopen('https://api.ipify.org', timeout=10) as response:
                return response.read().decode('utf-8').strip()
        except:
            pass
        return None
    
    @staticmethod
    def is_connected() -> bool:
        success, output = MullvadManager._run_command(["mullvad", "status"])
        if success:
            return "Connected" in output and "Disconnected" not in output
        return False
    
    @staticmethod
    def get_available_servers() -> List[str]:
        success, output = MullvadManager._run_command(["mullvad", "relay", "list"])
        if not success:
            return MullvadManager.PREFERRED_SERVERS.copy()
        
        servers = []
        for line in output.split('\n'):
            match = re.search(r'(\w{2}-\w{3})-', line)
            if match:
                server = match.group(1)
                if server not in servers and server not in MullvadManager.DISCORD_BLOCKED_SERVERS:
                    servers.append(server)
        
        return servers if servers else MullvadManager.PREFERRED_SERVERS.copy()
    
    @staticmethod
    def _check_ip_quality(ip: str) -> Tuple[bool, str]:
        """Check IP quality via proxycheck.io and ip-api.com.
        
        Returns (True, '') if the IP looks usable for Discord registration.
        Returns (False, reason) if the IP is flagged as high-risk.
        On any network error, returns (True, '') to avoid blocking.
        """
        if not ip or ip.startswith("via "):
            return True, ""
        
        try:
            import urllib.request
            import json as _json
            url = f"https://proxycheck.io/v2/{ip}?vpn=1&risk=1&seen=1&days=30"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode())
            status = data.get("status", "ok")
            if status in ("ok", "warning"):
                ip_data = data.get(ip, {})
                risk = int(ip_data.get("risk", 0) or 0)
                seen_days = ip_data.get("seen days ago", None)
                if risk >= 75:
                    return False, f"risk score too high ({risk}/100)"
                if seen_days is not None and int(seen_days or 999) <= 7 and risk >= 50:
                    return False, f"recently flagged (risk={risk}, seen {seen_days}d ago)"
        except Exception:
            pass
        
        try:
            import urllib.request
            import json as _json
            url = f"http://ip-api.com/json/{ip}?fields=proxy,hosting,status"
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = _json.loads(resp.read().decode())
            if data.get("hosting") and data.get("proxy"):
                return False, "datacenter proxy detected"
        except Exception:
            pass
        
        return True, ""

    @staticmethod
    def get_best_undetected_server() -> str:
        MullvadManager._load_flagged_relays()
        available = MullvadManager.get_available_servers()
        
        preferred_available = [s for s in MullvadManager.PREFERRED_SERVERS if s in available]
        
        # Filter out location prefixes where every individual relay ID is flagged
        relay_map = MullvadManager._build_relay_ip_map()
        
        def location_has_clean_relay(loc_prefix: str) -> bool:
            if not MullvadManager._flagged_relays or not relay_map:
                return True  # Can't check, allow through
            for relay_id in relay_map:
                if relay_id.startswith(loc_prefix + '-') or relay_id.startswith(loc_prefix):
                    if relay_id not in MullvadManager._flagged_relays:
                        return True
            return False
        
        preferred_available = [s for s in preferred_available if location_has_clean_relay(s)]
        
        if MullvadManager._verified_clean_servers:
            clean_unused = [s for s in MullvadManager._verified_clean_servers
                           if s not in MullvadManager._used_servers and location_has_clean_relay(s)]
            if clean_unused:
                server = random.choice(clean_unused)
                MullvadManager._used_servers.append(server)
                return server
        
        unused = [s for s in preferred_available if s not in MullvadManager._used_servers]
        
        if not unused:
            MullvadManager._used_servers = []
            unused = preferred_available.copy()
        
        if not unused:
            unused = [s for s in available
                      if s not in MullvadManager.DISCORD_BLOCKED_SERVERS
                      and location_has_clean_relay(s)]
        
        if unused:
            server = random.choice(unused)
            MullvadManager._used_servers.append(server)
            return server
        
        return "se-sto"
    
    @staticmethod
    def connect(server: Optional[str] = None) -> Tuple[bool, str]:
        if server:
            MullvadManager._run_command(["mullvad", "relay", "set", "location", server])
        
        success, output = MullvadManager._run_command(["mullvad", "connect"])
        if not success:
            return False, output
        
        for _ in range(30):
            time.sleep(1)
            if MullvadManager.is_connected():
                new_ip = MullvadManager.get_current_ip()
                return True, new_ip or "Connected"
        
        return False, "Connection timeout"
    
    @staticmethod
    def disconnect() -> Tuple[bool, str]:
        success, output = MullvadManager._run_command(["mullvad", "disconnect"])
        if not success:
            return False, output
        
        for _ in range(10):
            time.sleep(0.5)
            if not MullvadManager.is_connected():
                return True, "Disconnected"
        
        return False, "Disconnect timeout"
    
    @staticmethod
    def reconnect() -> Tuple[bool, str, str]:
        old_ip = MullvadManager.get_current_ip()
        
        MullvadManager.disconnect()
        time.sleep(1)
        
        new_server = MullvadManager.get_best_undetected_server()
        success, result = MullvadManager.connect(new_server)
        
        if success:
            new_ip = MullvadManager.get_current_ip()
            if new_ip and new_ip != old_ip:
                return True, new_ip or result, new_server
            for attempt in range(3):
                MullvadManager.disconnect()
                time.sleep(1)
                new_server = MullvadManager.get_best_undetected_server()
                success, result = MullvadManager.connect(new_server)
                if success:
                    new_ip = MullvadManager.get_current_ip()
                    if new_ip and new_ip != old_ip:
                        return True, new_ip, new_server
        
        return False, "Failed to get new IP", ""
    
    @staticmethod
    def display_first_account_status(worker_id: int = 0) -> bool:
        from ..MskColors.color import MskColor
        from ..Utils.logger import Logger
        
        with MullvadManager._lock:
            current_ip = MullvadManager.get_current_ip()
            
            if MullvadManager.is_connected():
                Logger.STATUS = f"{MskColor.YELLOW}Mullvad is already connected, reconnecting..."
                Logger.queue_log(worker_id=worker_id)
                time.sleep(0.5)
                
                MullvadManager.disconnect()
                time.sleep(1)
            
            Logger.STATUS = f"{MskColor.PRIMARY}Your IP: {MskColor.WHITE}{current_ip or 'Unknown'}"
            Logger.queue_log(worker_id=worker_id)
            time.sleep(0.3)
            
            Logger.STATUS = f"{MskColor.PRIMARY}Checking for the best server & undetected IP"
            Logger.queue_log(worker_id=worker_id)
            
            best_server = MullvadManager.get_best_undetected_server()
            time.sleep(0.5)
            
            Logger.STATUS = f"{MskColor.PRIMARY}Connecting to Mullvad"
            Logger.queue_log(worker_id=worker_id)
            
            success, new_ip = MullvadManager.connect(best_server)
            
            if success:
                if new_ip and new_ip != current_ip:
                    is_clean, reason = MullvadManager._check_ip_quality(new_ip)
                    if is_clean:
                        if best_server not in MullvadManager._verified_clean_servers:
                            MullvadManager._verified_clean_servers.append(best_server)
                        Logger.STATUS = f"{MskColor.GREEN}Connected to Mullvad IP: {MskColor.WHITE}{new_ip}"
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(0.5)
                        return True
                    else:
                        MullvadManager.flag_bad_ip(new_ip)
                        # Flag the specific relay ID so it's permanently skipped
                        relay_id = MullvadManager.get_current_relay_id()
                        if relay_id:
                            MullvadManager.flag_relay(relay_id, reason)
                        Logger.STATUS = f"{MskColor.YELLOW}IP {new_ip} flagged ({reason}), switching server..."
                        Logger.queue_log(worker_id=worker_id)
                
                for attempt in range(5):
                    MullvadManager.disconnect()
                    time.sleep(1)
                    best_server = MullvadManager.get_best_undetected_server()
                    success, new_ip = MullvadManager.connect(best_server)
                    if success and new_ip and new_ip != current_ip:
                        # Skip IPs known-bad from previous sessions
                        if MullvadManager.is_ip_flagged(new_ip):
                            relay_id = MullvadManager.get_current_relay_id()
                            if relay_id:
                                MullvadManager.flag_relay(relay_id, "previously flagged IP")
                            Logger.STATUS = f"{MskColor.YELLOW}IP {new_ip} was previously flagged, retrying ({attempt + 1}/5)..."
                            Logger.queue_log(worker_id=worker_id)
                            continue
                        is_clean, reason = MullvadManager._check_ip_quality(new_ip)
                        if is_clean:
                            if best_server not in MullvadManager._verified_clean_servers:
                                MullvadManager._verified_clean_servers.append(best_server)
                            Logger.STATUS = f"{MskColor.GREEN}Connected to Mullvad IP: {MskColor.WHITE}{new_ip}"
                            Logger.queue_log(worker_id=worker_id)
                            time.sleep(0.5)
                            return True
                        else:
                            MullvadManager.flag_bad_ip(new_ip)
                            relay_id = MullvadManager.get_current_relay_id()
                            if relay_id:
                                MullvadManager.flag_relay(relay_id, reason)
                            Logger.STATUS = f"{MskColor.YELLOW}IP flagged ({reason}), retrying ({attempt + 1}/5)..."
                            Logger.queue_log(worker_id=worker_id)
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}IP unchanged, retrying ({attempt + 1}/5)..."
                        Logger.queue_log(worker_id=worker_id)
                Logger.STATUS = f"{MskColor.RED}Failed to get clean IP after retries"
                Logger.queue_log(worker_id=worker_id)
                return False
            else:
                Logger.STATUS = f"{MskColor.RED}Failed to connect to Mullvad: {new_ip}"
                Logger.queue_log(worker_id=worker_id)
                return False
    
    @staticmethod
    def display_reconnect_status(worker_id: int = 0) -> bool:
        from ..MskColors.color import MskColor
        from ..Utils.logger import Logger
        
        with MullvadManager._lock:
            current_ip = MullvadManager.get_current_ip()
            
            Logger.STATUS = f"{MskColor.PRIMARY}Your IP: {MskColor.WHITE}{current_ip or 'Unknown'}"
            Logger.queue_log(worker_id=worker_id)
            time.sleep(0.3)
            
            Logger.STATUS = f"{MskColor.PRIMARY}Checking for the best server & undetected IP"
            Logger.queue_log(worker_id=worker_id)
            time.sleep(0.5)
            
            Logger.STATUS = f"{MskColor.YELLOW}Disconnecting from Mullvad, reconnecting to Mullvad"
            Logger.queue_log(worker_id=worker_id)
            
            max_retries = 6
            for attempt in range(max_retries):
                success, new_ip, server = MullvadManager.reconnect()
                
                if success and new_ip and new_ip != current_ip:
                    # Skip IPs known-bad from previous sessions
                    if MullvadManager.is_ip_flagged(new_ip):
                        relay_id = MullvadManager.get_current_relay_id()
                        if relay_id:
                            MullvadManager.flag_relay(relay_id, "previously flagged IP")
                        Logger.STATUS = f"{MskColor.YELLOW}IP {new_ip} was previously flagged, retrying ({attempt + 1}/{max_retries})..."
                        Logger.queue_log(worker_id=worker_id)
                        continue
                    is_clean, reason = MullvadManager._check_ip_quality(new_ip)
                    if is_clean:
                        if server and server not in MullvadManager._verified_clean_servers:
                            MullvadManager._verified_clean_servers.append(server)
                        Logger.STATUS = f"{MskColor.GREEN}Connected to Mullvad IP: {MskColor.WHITE}{new_ip}"
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(0.5)
                        return True
                    else:
                        MullvadManager.flag_bad_ip(new_ip)
                        # Flag by relay ID so we never reconnect to this server again
                        relay_id = MullvadManager.get_current_relay_id()
                        if relay_id:
                            MullvadManager.flag_relay(relay_id, reason)
                        Logger.STATUS = f"{MskColor.YELLOW}IP {new_ip} flagged ({reason}), retrying ({attempt + 1}/{max_retries})..."
                        Logger.queue_log(worker_id=worker_id)
                        time.sleep(0.5)
                elif success:
                    Logger.STATUS = f"{MskColor.YELLOW}IP unchanged, retrying ({attempt + 1}/{max_retries})..."
                    Logger.queue_log(worker_id=worker_id)
                    time.sleep(0.5)
                else:
                    Logger.STATUS = f"{MskColor.RED}Reconnect failed, retrying ({attempt + 1}/{max_retries})..."
                    Logger.queue_log(worker_id=worker_id)
                    time.sleep(1)
            
            Logger.STATUS = f"{MskColor.RED}Failed to get clean IP after {max_retries} attempts"
            Logger.queue_log(worker_id=worker_id)
            return False
