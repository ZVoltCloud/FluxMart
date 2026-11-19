import sys
import re
import threading
import queue
from datetime import datetime
from typing import ClassVar, Optional

from rich.console import Console
from rich.text import Text

console = Console()

LOG_SPACING = "                    "

# ── Sensitive data patterns (terminal output redaction) ──────────────────
_REDACT_TOKEN_RE = re.compile(
    r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}(?![A-Za-z0-9_-])'
)
_REDACT_BEARER_RE = re.compile(
    r'(?i)(Bearer\s+)([A-Za-z0-9_\-\.]{16,})'
)
_REDACT_APIKEY_RE = re.compile(
    r'(?i)((?:api[-_]?key|apikey|access[-_]?token|secret|Authorization)\s*[=:]\s*["\']?)([A-Za-z0-9_\-\.]{16,})'
)
_REDACT_WEBHOOK_RE = re.compile(
    r'(https?://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/)([A-Za-z0-9_\-]{40,})',
    re.IGNORECASE
)


def _redact(message: str) -> str:
    """Redact tokens, API keys, and auth credentials from a log message."""
    if not message or not isinstance(message, str):
        return message
    message = _REDACT_WEBHOOK_RE.sub(r'\1[REDACTED]', message)
    message = _REDACT_BEARER_RE.sub(r'\1[REDACTED]', message)
    message = _REDACT_APIKEY_RE.sub(r'\1[REDACTED]', message)
    message = _REDACT_TOKEN_RE.sub(lambda m: m.group(0)[:10] + '***', message)
    return message


def _timestamp() -> str:
    """Return a short HH:MM:SS timestamp string."""
    return datetime.now().strftime('%H:%M:%S')


class Logger:
    STATUS: ClassVar[str] = ""
    
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _workers: ClassVar[dict[int, dict[str, int]]] = {}
    _logger_thread: ClassVar[Optional[threading.Thread]] = None
    _stop_event: ClassVar[threading.Event] = threading.Event()
    _queue: ClassVar[queue.Queue] = queue.Queue()

    @classmethod
    def start_logger(cls) -> None:
        if cls._logger_thread and cls._logger_thread.is_alive():
            return
        cls._stop_event.clear()
        cls._logger_thread = threading.Thread(target=cls._run_logger, daemon=True)
        cls._logger_thread.start()

    @classmethod
    def stop_logger(cls) -> None:
        cls._stop_event.set()
        if cls._logger_thread:
            cls._logger_thread.join()

    @classmethod
    def _run_logger(cls):
        while not cls._stop_event.is_set():
            try:
                func, args, kwargs = cls._queue.get(timeout=0.1)
                func(*args, **kwargs)
            except queue.Empty:
                continue

    @classmethod
    def _register_worker(cls, worker_id: int):
        if worker_id not in cls._workers:
            start_line = 7
            if cls._workers:
                start_line = max(
                    w["log_line"] + w["stats_lines"] for w in cls._workers.values()
                ) + 1
            cls._workers[worker_id] = {"log_line": start_line, "stats_lines": 0, "last_log": None}

    @classmethod
    def _worker_log_line(cls, worker_id: int) -> int:
        cls._register_worker(worker_id)
        return cls._workers[worker_id]["log_line"]

    @classmethod
    def _worker_stats_start(cls, worker_id: int) -> int:
        cls._register_worker(worker_id)
        return cls._workers[worker_id]["log_line"] + 1 + cls._workers[worker_id]["stats_lines"]

    @classmethod
    def queue_log(cls, worker_id: int, status: Optional[str] = None, overwrite: bool = True):
        with cls._lock:
            if status is None:
                status = cls.STATUS
            cls._register_worker(worker_id)
            cls._workers[worker_id]["last_log"] = status
        cls._queue.put((cls.log_process, (worker_id,), {"status": status, "overwrite": overwrite}))

    @classmethod
    def queue_stats(cls, worker_id: int, stats_list: list[tuple[str, str, bool]]):
        cls._queue.put((cls.print_stats, (worker_id, stats_list), {}))

    @classmethod
    def log_process(cls, worker_id: int, status: Optional[str] = None, overwrite: bool = True):
        if status is None:
            status = cls.STATUS
        with cls._lock:
            cls._register_worker(worker_id)
            cls._workers[worker_id]["last_log"] = status
            line = cls._workers[worker_id]["log_line"]

        log_status(status, "info")
        try:
            if sys.stdout:
                sys.stdout.flush()
        except Exception:
            pass

    @classmethod
    def print_stats(cls, worker_id: int, stats_list: list[tuple[str, str, bool]]):
        with cls._lock:
            start_line = cls._worker_stats_start(worker_id)
            stats_count = sum(1 for _, _, should in stats_list if should)
            cls._workers[worker_id]["stats_lines"] = stats_count

        line = start_line
        for i, (stat, value, should_print) in enumerate(stats_list):
            if not should_print:
                continue
            is_last = i == len(stats_list) - 1
            prefix = f"{LOG_SPACING}    {'├' if not is_last else '└'}─ {stat}: "
            
            if value in ["Invalid", "Locked"]:
                log_error(f"{prefix}{value}")
            else:
                log_info(f"{prefix}{value}")
            line += 1
        try:
            if sys.stdout:
                sys.stdout.flush()
        except Exception:
            pass


def log_status(status: str, status_type: str = "info"):
    status = _redact(status)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Msk", style="dim")
    line.append("] ", style="#c0c0c0")
    
    if "\033[" in status:
        from rich.ansi import AnsiDecoder
        decoder = AnsiDecoder()
        for text_obj in decoder.decode(status):
            line.append(text_obj)
    else:
        if status_type == "success":
            line.append(status, style="#44ff00")
        elif status_type == "error":
            line.append(status, style="#ff001e")
        else:
            line.append(status, style="#e0e0e0")
    
    console.print(line)


def log_info(message: str):
    message = _redact(message)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Msk", style="dim")
    line.append("] ", style="#c0c0c0")
    
    if "\033[" in message:
        from rich.ansi import AnsiDecoder
        decoder = AnsiDecoder()
        for text_obj in decoder.decode(message):
            line.append(text_obj)
    else:
        line.append(message, style="white")
    console.print(line)


def log_success(message: str):
    message = _redact(message)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Msk", style="dim")
    line.append("] ", style="#c0c0c0")
    line.append(message, style="#44ff00")
    console.print(line)


def log_error(message: str):
    message = _redact(message)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Msk", style="dim")
    line.append("] ", style="#c0c0c0")
    line.append(message, style="#ff001e")
    console.print(line)


def log_warning(message: str):
    """Log a WARNING-level message in orange."""
    message = _redact(message)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Msk", style="dim")
    line.append("] ", style="#c0c0c0")
    line.append(message, style="#ff9800")
    console.print(line)


def log_progress(current: int, total: int, message: str = ""):
    message = _redact(message)
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append(f"{current}/{total}", style="dim")
    line.append("] ", style="#c0c0c0")
    line.append(message, style="white")
    console.print(line)


def log_summary(success: int, failed: int, total: int, action: str = "Processed"):
    console.print()
    line = Text()
    line.append(LOG_SPACING, style="")
    line.append("[", style="#c0c0c0")
    line.append("Summary", style="dim")
    line.append("] ", style="#c0c0c0")
    line.append(f"{action}: ", style="white")
    line.append(str(success), style="#44ff00")
    line.append(" success, ", style="white")
    line.append(str(failed), style="#ff001e")
    line.append(" failed, ", style="white")
    line.append(str(total), style="#e0e0e0")
    line.append(" total", style="white")
    console.print(line)

