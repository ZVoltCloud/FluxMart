"""
window_manager.py -- Browser window layout, anti-minimize, and launch ordering.

Features:
  1. Grid-based slot system: each browser gets a unique, non-overlapping screen position.
  2. Anti-minimize monitor: auto-restores minimized windows so CDP keeps working.
  3. Launch lock: only one browser launches at a time; others wait.
  4. Supports up to N concurrent browser instances (configurable).
  5. Thread-safe implementation.
"""

import ctypes
import math
import os
import sys
import time
import threading
from typing import Dict, Optional, Tuple

from .logger import Logger

def info(tag, msg):
    try:
        Logger.STATUS = f"[Msk][WM] {msg}"
        Logger.queue_log()
    except:
        pass

def warn(tag, msg):
    try:
        Logger.STATUS = f"[Msk][WM][WARN] {msg}"
        Logger.queue_log()
    except:
        pass

# ── Windows API constants ─────────────────────────────────────────────────────

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    SW_RESTORE = 9
    SW_SHOW = 5
    SW_SHOWNOACTIVATE = 4
    HWND_TOP = 0
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    SM_CXSCREEN = 0
    SM_CYSCREEN = 1
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    # EnumWindows callback type -- use c_void_p so HWND arrives as plain int
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _get_screen_size() -> Tuple[int, int]:
        """Get primary screen resolution."""
        w = user32.GetSystemMetrics(SM_CXSCREEN)
        h = user32.GetSystemMetrics(SM_CYSCREEN)
        return (w or 1920, h or 1080)

    def _is_minimized(hwnd: int) -> bool:
        return bool(user32.IsIconic(hwnd))

    def _is_window_valid(hwnd: int) -> bool:
        return bool(user32.IsWindow(hwnd))

    def _restore_window(hwnd: int):
        user32.ShowWindow(hwnd, SW_RESTORE)

    def _set_window_pos(hwnd: int, x: int, y: int, w: int, h: int):
        user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def _find_hwnd_by_pid(pid: int) -> Optional[int]:
        """Find the main window handle for a given process ID."""
        result = []

        def callback(hwnd, _):
            hwnd = int(hwnd)  # ensure plain int
            if not user32.IsWindowVisible(hwnd):
                return True
            proc_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                result.append(hwnd)
                return False  # stop enumerating
            return True

        cb_func = WNDENUMPROC(callback)
        user32.EnumWindows(cb_func, 0)
        return result[0] if result else None
        
    def _find_hwnd_by_title(title: str) -> Optional[int]:
        """Find the main window handle by exact window title."""
        result = []
        def callback(hwnd, _):
            hwnd = int(hwnd)
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                # Playwright titles often have suffixes, use exact match or "in"
                if title in buff.value:
                    result.append(hwnd)
                    return False
            return True
        cb_func = WNDENUMPROC(callback)
        user32.EnumWindows(cb_func, 0)
        return result[0] if result else None

else:
    # Non-Windows: provide stubs so the code doesn't crash.
    def _get_screen_size() -> Tuple[int, int]:
        return (1920, 1080)

    def _is_minimized(hwnd: int) -> bool:
        return False

    def _is_window_valid(hwnd: int) -> bool:
        return True

    def _restore_window(hwnd: int):
        pass

    def _set_window_pos(hwnd: int, x: int, y: int, w: int, h: int):
        pass

    def _find_hwnd_by_pid(pid: int) -> Optional[int]:
        return None
        
    def _find_hwnd_by_title(title: str) -> Optional[int]:
        return None


# ── Slot Grid ─────────────────────────────────────────────────────────────────

class SlotGrid:
    """Calculates a grid of non-overlapping window positions."""

    MIN_CELL_W = 400
    MIN_CELL_H = 500

    def __init__(self, max_slots: int, screen_w: int = 0, screen_h: int = 0,
                 taskbar_height: int = 48):
        sw, sh = _get_screen_size()
        self.screen_w = screen_w or sw
        self.screen_h = (screen_h or sh) - taskbar_height
        self.max_slots = max_slots

        # Compute grid dimensions -- prefer horizontal layout (single row)
        # to maximize window height for captcha visibility
        max_cols = max(1, self.screen_w // self.MIN_CELL_W)
        max_rows = max(1, self.screen_h // self.MIN_CELL_H)
        max_fit = max_cols * max_rows

        if max_slots > max_fit:
            self.max_slots = max_fit

        # Start with all in one row; add rows only if too many
        self.cols = min(self.max_slots, max_cols)
        self.rows = math.ceil(self.max_slots / self.cols)

        # Cell size
        self.cell_w = self.screen_w // self.cols
        self.cell_h = self.screen_h // self.rows

    def position(self, slot_index: int) -> Tuple[int, int, int, int]:
        """Return (x, y, width, height) for a given slot index."""
        col = slot_index % self.cols
        row = slot_index // self.cols
        x = col * self.cell_w
        y = row * self.cell_h
        return (x, y, self.cell_w, self.cell_h)


# ── WindowManager ────────────────────────────────────────────────────────────

class WindowManager:
    """Coordinates browser window positioning, anti-minimize, and launch ordering.

    Usage:
        wm = WindowManager(max_slots=10)
        wm.start_monitor()

        # In each solver task:
        slot_idx, pos = wm.acquire_slot()
        with wm.launch_lock:
            proc = launch_browser(pos)
            hwnd = wm.find_and_register_by_title("my-uuid", slot_idx, pos)
        ...
        wm.release(slot_idx)
    """

    def __init__(self, max_slots: int = 10, headless: bool = False):
        self.max_slots = max_slots
        self._headless = headless
        self.grid = SlotGrid(max_slots)
        self.launch_lock = threading.Lock()

        # Slot availability: index -> True means available
        self._slots: Dict[int, bool] = {i: True for i in range(max_slots)}
        self._slot_lock = threading.Lock()

        # Window tracking: hwnd -> {"slot_idx": int, "x": int, "y": int, "w": int, "h": int}
        self._windows: Dict[int, dict] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_event = threading.Event()

        if not self._headless:
            info("WindowManager", f"grid={self.grid.cols}x{self.grid.rows} "
                 f"cell={self.grid.cell_w}x{self.grid.cell_h} "
                 f"screen={self.grid.screen_w}x{self.grid.screen_h + 48} "
                 f"slots={max_slots}")

    def acquire_slot(self) -> Tuple[int, Tuple[int, int, int, int]]:
        """Wait for and reserve a free grid slot.

        Returns:
            (slot_index, (x, y, w, h))
        """
        while True:
            with self._slot_lock:
                for idx, available in self._slots.items():
                    if available:
                        self._slots[idx] = False
                        pos = self.grid.position(idx)
                        return (idx, pos)
            # All slots busy -- wait and retry
            time.sleep(0.5)

    def release(self, slot_idx: int):
        """Release a grid slot and unregister its window."""
        with self._slot_lock:
            # Find and remove the window associated with this slot
            to_remove = [h for h, w in self._windows.items() if w["slot_idx"] == slot_idx]
            for h in to_remove:
                del self._windows[h]
            self._slots[slot_idx] = True

    def find_and_register(self, pid: int, slot_idx: int, pos: Tuple[int, int, int, int]) -> Optional[int]:
        """Find the browser window handle by PID and register it for monitoring."""
        if not _IS_WINDOWS:
            return None

        hwnd = None
        for _ in range(30):
            hwnd = _find_hwnd_by_pid(pid)
            if hwnd:
                break
            time.sleep(0.2)

        if not hwnd:
            return None

        x, y, w, h = pos
        with self._slot_lock:
            self._windows[hwnd] = {"slot_idx": slot_idx, "x": x, "y": y, "w": w, "h": h}
        _set_window_pos(hwnd, x, y, w, h)
        return hwnd

    def find_and_register_by_title(self, title: str, slot_idx: int, pos: Tuple[int, int, int, int]) -> Optional[int]:
        """Find the browser window handle by title and register it for monitoring."""
        if not _IS_WINDOWS:
            return None

        hwnd = None
        for _ in range(30):
            hwnd = _find_hwnd_by_title(title)
            if hwnd:
                break
            time.sleep(0.2)

        if not hwnd:
            return None

        x, y, w, h = pos
        with self._slot_lock:
            self._windows[hwnd] = {"slot_idx": slot_idx, "x": x, "y": y, "w": w, "h": h}
        _set_window_pos(hwnd, x, y, w, h)
        return hwnd

    def unregister_window(self, hwnd: int):
        """Stop tracking a window."""
        with self._slot_lock:
            if hwnd in self._windows:
                del self._windows[hwnd]

    # ── Anti-minimize monitor ─────────────────────────────────────────────

    def start_monitor(self):
        """Start the background anti-minimize monitor."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._monitor_stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def stop_monitor(self):
        """Stop the background monitor."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_stop_event.set()

    def _monitor_loop(self):
        """Periodically check all tracked windows; restore any that got minimized."""
        while not self._monitor_stop_event.is_set():
            try:
                # wait returns True if flag is set, otherwise False after timeout
                if self._monitor_stop_event.wait(2.0):
                    break
                
                if not _IS_WINDOWS:
                    continue

                dead = []
                with self._slot_lock:
                    # snapshot to iterate safely
                    windows_snapshot = list(self._windows.items())
                    
                for hwnd, winfo in windows_snapshot:
                    if not _is_window_valid(hwnd):
                        dead.append(hwnd)
                        continue
                    if _is_minimized(hwnd):
                        info("Monitor", f"restoring minimized HWND={hwnd} slot=#{winfo['slot_idx']}")
                        _restore_window(hwnd)
                        time.sleep(0.3)
                        # Reapply position after restore (Windows may reposition)
                        _set_window_pos(hwnd, winfo["x"], winfo["y"],
                                        winfo["w"], winfo["h"])

                # Clean up dead windows
                if dead:
                    with self._slot_lock:
                        for hwnd in dead:
                            if hwnd in self._windows:
                                slot_idx = self._windows[hwnd]["slot_idx"]
                                del self._windows[hwnd]
                                self._slots[slot_idx] = True

            except Exception:
                pass  # Don't crash the monitor for transient errors
