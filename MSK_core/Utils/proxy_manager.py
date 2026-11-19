import sys
import os
import threading
from pathlib import Path
from typing import Optional, Dict, List

from ..MskColors.color import MskColor
from .logger import Logger


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
            _candidates.append(os.getcwd())
        except Exception:
            pass
        try:
            _candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
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


def _find_proxy_file(relative_path: str) -> Path:
    base_dirs: list[str] = []

    try:
        base_dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    try:
        base_dirs.append(os.getcwd())
    except Exception:
        pass
    try:
        base_dirs.append(get_base_path())
    except Exception:
        pass
    try:
        f_dir = os.path.dirname(os.path.abspath(__file__))
        base_dirs.append(os.path.dirname(os.path.dirname(f_dir)))
    except Exception:
        pass
    try:
        base_dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass

    expanded: list[str] = []
    seen_dirs: set[str] = set()
    for bd in base_dirs:
        cur = bd
        for _ in range(4):
            normed = os.path.normpath(cur)
            if normed not in seen_dirs:
                seen_dirs.add(normed)
                expanded.append(normed)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    seen_files: set[str] = set()
    unique_files: list[str] = []
    for bd in expanded:
        p = os.path.normpath(os.path.join(bd, relative_path))
        if p not in seen_files:
            seen_files.add(p)
            unique_files.append(p)

    for path in unique_files:
        if os.path.isfile(path):
            return Path(path)

    return Path(unique_files[0]) if unique_files else Path(relative_path)


class ProxyManager:
    """
    Thread-safe proxy manager -- cycles through proxies.txt round-robin.

    Each call to get_proxy() returns the NEXT proxy in the list.
    The proxy string is used exactly as-is from the file.

    Sticky vs rotating IPs is handled by the proxy PROVIDER, not by this tool.
    The user configures it in the proxy string itself:
      - Rotating: user:pass@host:port          (new IP each connection)
      - Sticky:   user-session-xxx:pass@host:port  (same IP for session)
    """

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._init_lock:
                if not cls._instance:
                    cls._instance = super(ProxyManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, filename: str | Path = "data/input/proxies.txt") -> None:
        if getattr(self, '_initialized', False):
            return
        self._relative_path = str(filename)
        self.filename: Path = _find_proxy_file(self._relative_path)
        self._lock: threading.Lock = threading.Lock()
        self._proxies: List[Dict[str, str]] = []
        self._index: int = 0
        self._loaded_mtime: float = 0.0
        self._load_proxies()
        self._initialized = True

    def _read_lines(self) -> List[str]:
        if not self.filename.exists():
            self.filename = _find_proxy_file(self._relative_path)
        if not self.filename.exists():
            return []
        try:
            content = self.filename.read_text(encoding="utf-8")
            return [ln.strip() for ln in content.splitlines() if ln.strip()]
        except Exception:
            return []

    def _parse_proxy_line(self, line: str, worker_id: int = 0, known_hosts: Optional[set] = None) -> Optional[Dict[str, str]]:
        try:
            protocol = "http"
            working = line.strip()
            if not working or working.startswith("#") or working.startswith("//"):
                return None

            # Strip inline comments or annotations
            for sep in (" #", " //", " ;"):
                if sep in working:
                    working = working.split(sep, 1)[0].strip()

            # If there is whitespace or trailing metadata (e.g. "http://...:7070 (840 KB left)"),
            # extract the proxy URL token
            if " " in working or "\t" in working:
                working = working.split()[0].strip()

            if "://" in working:
                protocol, working = working.split("://", 1)
                protocol = protocol.lower()

            if "@" in working:
                credentials, host_port = working.rsplit("@", 1)

                # Auto-repair truncated host:port if copied from dashboard with ellipsis
                if (":" not in host_port or "..." in host_port) and known_hosts:
                    clean_prefix = host_port.rstrip(".").lower()
                    for kh in known_hosts:
                        if kh.lower().startswith(clean_prefix) or clean_prefix in kh.lower():
                            host_port = kh
                            break

                if ":" not in host_port:
                    raise ValueError(f"Missing port in '{host_port}'")

                host, port = host_port.rsplit(":", 1)
                if "..." in host and known_hosts:
                    clean_prefix = host.rstrip(".").lower()
                    for kh in known_hosts:
                        if ":" in kh:
                            k_h, _ = kh.rsplit(":", 1)
                            if k_h.lower().startswith(clean_prefix):
                                host = k_h
                                break

                username = credentials.split(":", 1)[0] if ":" in credentials else credentials
                password = credentials.split(":", 1)[1] if ":" in credentials else credentials
                return {
                    "raw": line,
                    "server": f"{protocol}://{host}:{port}",
                    "username": username,
                    "password": password,
                }

            parts = working.split(":")

            if len(parts) == 2:
                host, port = parts
                return {
                    "raw": line,
                    "server": f"{protocol}://{host}:{port}",
                    "username": "",
                    "password": "",
                }

            if len(parts) == 3:
                host, port, token = parts
                return {
                    "raw": line,
                    "server": f"{protocol}://{host}:{port}",
                    "username": token,
                    "password": token,
                }

            if len(parts) >= 4:
                host  = parts[0]
                port  = parts[1]
                username = ":".join(parts[2:-1])
                password = parts[-1]
                return {
                    "raw": line,
                    "server": f"{protocol}://{host}:{port}",
                    "username": username,
                    "password": password,
                }

            Logger.STATUS = f"{MskColor.RED}Unrecognized proxy format: '{line}'"
            Logger.queue_log(worker_id=worker_id)
            return None

        except Exception as exc:
            Logger.STATUS = f"{MskColor.RED}Error parsing proxy '{line}': {exc}"
            Logger.queue_log(worker_id=worker_id)
            return None

    def _load_proxies(self) -> None:
        lines = self._read_lines()
        parsed: List[Dict[str, str]] = []

        # Pass 1: Collect known valid host:port endpoints for auto-repair
        known_hosts: set = set()
        for l in lines:
            try:
                w = l.strip()
                if " #" in w: w = w.split(" #", 1)[0].strip()
                if " " in w: w = w.split()[0].strip()
                if "://" in w: _, w = w.split("://", 1)
                if "@" in w:
                    hp = w.rsplit("@", 1)[1]
                    if ":" in hp and "..." not in hp:
                        known_hosts.add(hp)
                elif ":" in w:
                    p = w.split(":")
                    if len(p) >= 2 and "..." not in p[0] and p[1].isdigit():
                        known_hosts.add(f"{p[0]}:{p[1]}")
            except Exception:
                pass

        # Pass 2: Parse all lines
        for line in lines:
            proxy = self._parse_proxy_line(line, known_hosts=known_hosts)
            if not proxy:
                continue

            proto = "http"
            if "://" in line:
                proto = line.split("://", 1)[0].lower()

            if proto in ("socks5", "socks5h", "socks4", "socks4a"):
                Logger.STATUS = f"{MskColor.RED}Skipping SOCKS proxy '{proxy['server']}' -- SOCKS proxies are not supported. Use HTTP/HTTPS proxies only."
                Logger.queue_log(worker_id=0)
                continue

            parsed.append(proxy)

        self._proxies = parsed
        self._index = 0

        if self.filename.exists():
            self._loaded_mtime = self.filename.stat().st_mtime

    def _file_changed(self) -> bool:
        if not self.filename.exists():
            self.filename = _find_proxy_file(self._relative_path)
        if not self.filename.exists():
            return False
        try:
            return self.filename.stat().st_mtime > self._loaded_mtime
        except Exception:
            return False

    def _proxy_count(self) -> int:
        return len(self._proxies)

    def get_proxy(self, worker_id: int = 0, **kwargs) -> Optional[Dict[str, str]]:
        """Return the next proxy in round-robin order.

        Each call returns the NEXT proxy from proxies.txt.
        The proxy string is used exactly as-is -- no modification.
        """
        with self._lock:
            if self._file_changed():
                self._load_proxies()

            if not self._proxies:
                return None

            proxy = self._proxies[self._index % len(self._proxies)]
            self._index = (self._index + 1) % len(self._proxies)
            return proxy

    def wait_for_proxies(
        self,
        worker_id: int = 0,
        check_interval: float = 1.0,
        stable_wait: float = 1.0,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[Dict[str, str]]:
        """Block until at least one proxy is available, then return it."""
        import time

        Logger.STATUS = f"{MskColor.YELLOW}Waiting for proxies..."
        Logger.queue_log(worker_id=worker_id)

        start = time.time()
        printed_waiting = False

        while True:
            if timeout is not None and (time.time() - start) > timeout:
                Logger.STATUS = f"{MskColor.RED}Proxy wait timed out"
                Logger.queue_log(worker_id=worker_id)
                return None

            with self._lock:
                self.filename = _find_proxy_file(self._relative_path)
                if self._file_changed() or not self._proxies:
                    self._load_proxies()

                if self._proxies:
                    proxy = self._proxies[self._index % len(self._proxies)]
                    self._index = (self._index + 1) % len(self._proxies)
                    return proxy

            if not printed_waiting:
                printed_waiting = True
                Logger.STATUS = f"{MskColor.YELLOW}No proxies found. Add proxies to {self.filename}..."
                Logger.queue_log(worker_id=worker_id)

            time.sleep(check_interval)

    def reload(self) -> int:
        with self._lock:
            self._load_proxies()
            return self._proxy_count()

    def remove_proxy(self, proxy_dict: Dict[str, str]) -> None:
        """Remove the specific used proxy from the pool and file permanently.

        Only the one proxy that matches is removed -- all others stay intact.
        The round-robin position is preserved so the next call picks up
        where it left off.
        """
        if not proxy_dict or "raw" not in proxy_dict:
            return

        with self._lock:
            if not self.filename.exists():
                return

            raw_line = proxy_dict["raw"].strip()

            try:
                content = self.filename.read_text(encoding="utf-8")
                lines = content.splitlines()

                new_lines = [ln for ln in lines if ln.strip() != raw_line]

                if len(new_lines) < len(lines):
                    self.filename.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
                    self._loaded_mtime = self.filename.stat().st_mtime

            except Exception as e:
                Logger.STATUS = f"{MskColor.RED}Failed to write proxy file: {e}"
                Logger.queue_log(worker_id=0)
                return

            raw_normalized = raw_line
            original_len = len(self._proxies)
            self._proxies = [p for p in self._proxies if p.get("raw", "").strip() != raw_normalized]

            removed_count = original_len - len(self._proxies)
            if removed_count > 0 and self._proxies:
                self._index = self._index % len(self._proxies)
            elif not self._proxies:
                self._index = 0

    @property
    def count(self) -> int:
        with self._lock:
            return self._proxy_count()
