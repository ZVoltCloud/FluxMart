#!/usr/bin/env python3
"""
Android Device Fingerprint Collector
Run this script on your Vivo V17 Pro (via Termux, ADB, or Python on Android)
to collect comprehensive device fingerprint data for building realistic profiles.

Usage:
    python3 android_device_collector.py --output vivo_v17_pro_fingerprint.json
    adb shell python3 /sdcard/android_device_collector.py --output /sdcard/vivo_v17_pro_fingerprint.json
"""

import json
import os
import sys
import platform
import subprocess
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional


class AndroidDeviceCollector:
    """Collects comprehensive Android device fingerprint data."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {
            "collection_timestamp": datetime.utcnow().isoformat() + "Z",
            "collector_version": "1.0.0",
            "device": {},
            "system": {},
            "display": {},
            "hardware": {},
            "software": {},
            "browser": {},
            "sensors": {},
            "network": {},
            "identifiers": {},
            "build": {},
            "runtime": {},
        }
    
    def run_cmd(self, cmd: List[str], shell: bool = False) -> Optional[str]:
        """Execute command and return output."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def run_cmd_shell(self, cmd: str) -> Optional[str]:
        """Execute shell command."""
        return self.run_cmd(cmd, shell=True)
    
    def collect_build_properties(self) -> Dict[str, Any]:
        """Collect Android build properties (ro.*)."""
        props = {}
        # Key build properties to collect
        keys = [
            "ro.product.brand", "ro.product.model", "ro.product.manufacturer",
            "ro.product.name", "ro.product.device", "ro.product.board",
            "ro.product.cpu.abi", "ro.product.cpu.abi2", "ro.product.cpu.abilist",
            "ro.build.version.sdk", "ro.build.version.release", "ro.build.version.release_or_codename",
            "ro.build.version.incremental", "ro.build.version.security_patch",
            "ro.build.version.base_os", "ro.build.version.preview_sdk",
            "ro.build.id", "ro.build.display.id", "ro.build.type", "ro.build.tags",
            "ro.build.user", "ro.build.host", "ro.build.date", "ro.build.date.utc",
            "ro.build.fingerprint", "ro.build.description", "ro.build.characteristics",
            "ro.vendor.build.fingerprint", "ro.system.build.fingerprint",
            "ro.bootimage.build.fingerprint", "ro.vendor.build.version.sdk",
            "ro.hardware", "ro.hardware.chipname", "ro.hardware.keystore",
            "ro.board.platform", "ro.arch", "ro.arch.primary", "ro.arch.secondary",
            "ro.product.locale", "ro.product.locale.region", "ro.product.locale.language",
            "ro.sf.lcd_density", "ro.sf.hwrotation", "ro.surface_flinger.max_frame_buffer_acquired_buffers",
            "ro.config.low_ram", "ro.config.notification_sound", "ro.config.alarm_alert",
            "ro.config.ringtone", "ro.carrier", "ro.com.google.clientidbase",
            "ro.com.google.gmsversion", "ro.setupwizard.mode", "ro.setupwizard.enterprise_mode",
            "ro.secure", "ro.debuggable", "ro.adb.secure", "ro.allow.mock.location",
            "ro.zygote", "ro.dalvik.vm.native.bridge", "ro.enable.native.bridge.exec",
            "ro.vendor.api_level", "ro.product.first_api_level",
            "ro.build.version.codename", "ro.build.version.all_codenames",
            "ro.product.brand", "ro.product.manufacturer", "ro.product.model",
            "ro.vivo.product.model", "ro.vivo.product.name", "ro.vivo.rom.version",
            "ro.vivo.os.version", "ro.vivo.build.version", "ro.vivo.software.version",
        ]
        
        for key in keys:
            val = self.run_cmd(["getprop", key])
            if val:
                props[key] = val
        
        # Also get all props for completeness
        all_props = self.run_cmd(["getprop"])
        if all_props:
            props["_all_props_raw"] = all_props
        
        return props
    
    def collect_display_info(self) -> Dict[str, Any]:
        """Collect display/screen information."""
        display = {}
        
        # Screen density
        density = self.run_cmd(["wm", "density"])
        if density:
            display["density"] = density
        
        # Screen size
        size = self.run_cmd(["wm", "size"])
        if size:
            display["size"] = size
        
        # Display info via dumpsys
        dumpsys_display = self.run_cmd(["dumpsys", "display"])
        if dumpsys_display:
            display["dumpsys_display"] = dumpsys_display[:5000]  # Truncate
        
        # SurfaceFlinger info
        sf = self.run_cmd(["dumpsys", "SurfaceFlinger"])
        if sf:
            display["surface_flinger"] = sf[:5000]
        
        # Display metrics via settings
        display_settings = {}
        for key in ["display_density", "display_size", "display_rotation", "display_width", "display_height"]:
            val = self.run_cmd(["settings", "get", "system", key])
            if val:
                display_settings[key] = val
        display["settings"] = display_settings
        
        return display
    
    def collect_hardware_info(self) -> Dict[str, Any]:
        """Collect hardware information."""
        hw = {}
        
        # CPU info
        cpuinfo = self.run_cmd(["cat", "/proc/cpuinfo"])
        if cpuinfo:
            hw["cpuinfo"] = cpuinfo
        
        # Memory info
        meminfo = self.run_cmd(["cat", "/proc/meminfo"])
        if meminfo:
            hw["meminfo"] = meminfo
        
        # GPU info
        gpu = self.run_cmd(["cat", "/proc/gpuinfo"])
        if gpu:
            hw["gpuinfo"] = gpu
        
        # Try to get GPU renderer
        gpu_renderer = self.run_cmd(["getprop", "ro.hardware.egl"])
        if gpu_renderer:
            hw["egl"] = gpu_renderer
        
        # Vulkan info
        vulkan = self.run_cmd(["dumpsys", "gpu"])
        if vulkan:
            hw["gpu_dumpsys"] = vulkan[:5000]
        
        # Battery info
        battery = self.run_cmd(["dumpsys", "battery"])
        if battery:
            hw["battery"] = battery[:2000]
        
        # Thermal info
        thermal = self.run_cmd(["cat", "/sys/class/thermal/thermal_zone0/temp"])
        if thermal:
            hw["thermal_zone0_temp"] = thermal
        
        # Sensors list
        sensors = self.run_cmd(["dumpsys", "sensorservice"])
        if sensors:
            hw["sensors_raw"] = sensors[:5000]
        
        # Input devices
        input_devices = self.run_cmd(["cat", "/proc/bus/input/devices"])
        if input_devices:
            hw["input_devices"] = input_devices
        
        return hw
    
    def collect_software_info(self) -> Dict[str, Any]:
        """Collect software/runtime information."""
        sw = {}
        
        # Android version details
        sw["android_version"] = self.run_cmd(["getprop", "ro.build.version.release"])
        sw["android_sdk"] = self.run_cmd(["getprop", "ro.build.version.sdk"])
        sw["security_patch"] = self.run_cmd(["getprop", "ro.build.version.security_patch"])
        
        # Java/ART runtime
        java_version = self.run_cmd(["dalvikvm", "-version"])
        if java_version:
            sw["dalvik_version"] = java_version
        
        # Installed packages (just count and key ones)
        packages = self.run_cmd(["pm", "list", "packages"])
        if packages:
            sw["package_count"] = len(packages.strip().split('\n'))
            # Check for key packages
            key_packages = ["com.android.chrome", "com.google.android.webview", "com.vivo.browser"]
            sw["key_packages"] = {pkg: pkg in packages for pkg in key_packages}
        
        # WebView version
        webview_ver = self.run_cmd(["dumpsys", "package", "com.google.android.webview"])
        if webview_ver:
            sw["webview_info"] = webview_ver[:3000]
        
        # Chrome version
        chrome_ver = self.run_cmd(["dumpsys", "package", "com.android.chrome"])
        if chrome_ver:
            sw["chrome_info"] = chrome_ver[:3000]
        
        # SELinux status
        selinux = self.run_cmd(["getenforce"])
        if selinux:
            sw["selinux"] = selinux
        
        # Root status
        root_check = self.run_cmd(["which", "su"])
        sw["root_available"] = root_check is not None
        
        return sw
    
    def collect_browser_fingerprint(self) -> Dict[str, Any]:
        """Collect browser-specific fingerprint data."""
        browser = {}
        
        # User agent from WebView
        ua = self.run_cmd(["settings", "get", "global", "user_agent"])
        if ua:
            browser["webview_user_agent"] = ua
        
        # Chrome user agent (if available)
        chrome_ua = self.run_cmd(["dumpsys", "package", "com.android.chrome"])
        if chrome_ua and "userAgent" in chrome_ua:
            # Extract user agent from dumpsys
            for line in chrome_ua.split('\n'):
                if "userAgent" in line.lower():
                    browser["chrome_user_agent"] = line.strip()
                    break
        
        # WebView settings
        webview_settings = {}
        for key in ["webview_javascript_enabled", "webview_dom_storage_enabled", "webview_database_enabled"]:
            val = self.run_cmd(["settings", "get", "global", key])
            if val:
                webview_settings[key] = val
        browser["webview_settings"] = webview_settings
        
        # Accept-Language
        locale = self.run_cmd(["getprop", "ro.product.locale"])
        if locale:
            browser["locale"] = locale
            browser["accept_language"] = f"{locale},{locale.split('-')[0]};q=0.9,en;q=0.8"
        
        # Timezone
        tz = self.run_cmd(["getprop", "persist.sys.timezone"])
        if not tz:
            tz = self.run_cmd(["cat", "/etc/timezone"])
        if tz:
            browser["timezone"] = tz
        
        return browser
    
    def collect_network_info(self) -> Dict[str, Any]:
        """Collect network-related information."""
        net = {}
        
        # WiFi info
        wifi = self.run_cmd(["dumpsys", "wifi"])
        if wifi:
            net["wifi"] = wifi[:3000]
        
        # Mobile network info
        telephony = self.run_cmd(["dumpsys", "telephony.registry"])
        if telephony:
            net["telephony"] = telephony[:3000]
        
        # IP addresses
        ip_addr = self.run_cmd(["ip", "addr", "show"])
        if ip_addr:
            net["interfaces"] = ip_addr
        
        # DNS
        dns = self.run_cmd(["getprop", "net.dns1"])
        if dns:
            net["dns1"] = dns
        dns2 = self.run_cmd(["getprop", "net.dns2"])
        if dns2:
            net["dns2"] = dns2
        
        return net
    
    def collect_identifiers(self) -> Dict[str, Any]:
        """Collect device identifiers (non-sensitive)."""
        ids = {}
        
        # Android ID
        android_id = self.run_cmd(["settings", "get", "secure", "android_id"])
        if android_id:
            ids["android_id"] = android_id
        
        # Build fingerprint
        fp = self.run_cmd(["getprop", "ro.build.fingerprint"])
        if fp:
            ids["build_fingerprint"] = fp
        
        # Serial (may be restricted)
        serial = self.run_cmd(["getprop", "ro.serialno"])
        if serial:
            ids["serial"] = serial
        
        # IMEI (requires permission, may not work)
        imei = self.run_cmd(["service", "call", "iphonesubinfo", "1"])
        if imei:
            ids["imei_raw"] = imei
        
        # MAC addresses (may be randomized)
        mac = self.run_cmd(["cat", "/sys/class/net/wlan0/address"])
        if mac:
            ids["wifi_mac"] = mac
        
        return ids
    
    def collect_runtime_info(self) -> Dict[str, Any]:
        """Collect runtime environment information."""
        rt = {}
        
        # Environment variables
        env = self.run_cmd(["printenv"])
        if env:
            rt["environment"] = env[:3000]
        
        # Mount points
        mounts = self.run_cmd(["mount"])
        if mounts:
            rt["mounts"] = mounts
        
        # Running processes (count)
        ps = self.run_cmd(["ps", "-A"])
        if ps:
            rt["process_count"] = len(ps.strip().split('\n'))
        
        # Uptime
        uptime = self.run_cmd(["cat", "/proc/uptime"])
        if uptime:
            rt["uptime"] = uptime
        
        # Load average
        loadavg = self.run_cmd(["cat", "/proc/loadavg"])
        if loadavg:
            rt["loadavg"] = loadavg
        
        return rt
    
    def collect_all(self) -> Dict[str, Any]:
        """Collect all fingerprint data."""
        print("[*] Collecting build properties...")
        self.data["build"] = self.collect_build_properties()
        
        print("[*] Collecting display info...")
        self.data["display"] = self.collect_display_info()
        
        print("[*] Collecting hardware info...")
        self.data["hardware"] = self.collect_hardware_info()
        
        print("[*] Collecting software info...")
        self.data["software"] = self.collect_software_info()
        
        print("[*] Collecting browser fingerprint...")
        self.data["browser"] = self.collect_browser_fingerprint()
        
        print("[*] Collecting network info...")
        self.data["network"] = self.collect_network_info()
        
        print("[*] Collecting identifiers...")
        self.data["identifiers"] = self.collect_identifiers()
        
        print("[*] Collecting runtime info...")
        self.data["runtime"] = self.collect_runtime_info()
        
        # Populate device summary
        self.data["device"] = {
            "brand": self.data["build"].get("ro.product.brand", "Unknown"),
            "model": self.data["build"].get("ro.product.model", "Unknown"),
            "manufacturer": self.data["build"].get("ro.product.manufacturer", "Unknown"),
            "device": self.data["build"].get("ro.product.device", "Unknown"),
            "board": self.data["build"].get("ro.product.board", "Unknown"),
            "hardware": self.data["build"].get("ro.hardware", "Unknown"),
            "chipname": self.data["build"].get("ro.hardware.chipname", "Unknown"),
            "cpu_abi": self.data["build"].get("ro.product.cpu.abi", "Unknown"),
            "cpu_abi2": self.data["build"].get("ro.product.cpu.abi2", ""),
        }
        
        self.data["system"] = {
            "android_version": self.data["build"].get("ro.build.version.release", "Unknown"),
            "sdk_version": self.data["build"].get("ro.build.version.sdk", "Unknown"),
            "security_patch": self.data["build"].get("ro.build.version.security_patch", "Unknown"),
            "build_id": self.data["build"].get("ro.build.id", "Unknown"),
            "build_fingerprint": self.data["build"].get("ro.build.fingerprint", "Unknown"),
            "build_type": self.data["build"].get("ro.build.type", "Unknown"),
            "build_tags": self.data["build"].get("ro.build.tags", "Unknown"),
        }
        
        return self.data
    
    def save(self, output_path: str):
        """Save collected data to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved fingerprint to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Android Device Fingerprint Collector")
    parser.add_argument("--output", "-o", default="device_fingerprint.json",
                        help="Output JSON file path")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Android Device Fingerprint Collector v1.0.0")
    print("=" * 60)
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print()
    
    collector = AndroidDeviceCollector()
    data = collector.collect_all()
    collector.save(args.output)
    
    print()
    print("=" * 60)
    print("Collection Complete!")
    print("=" * 60)
    print(f"Device: {data['device'].get('brand')} {data['device'].get('model')}")
    print(f"Android: {data['system'].get('android_version')} (SDK {data['system'].get('sdk_version')})")
    print(f"Build: {data['system'].get('build_id')}")
    print(f"Output: {args.output}")
    print()
    print("Next steps:")
    print("1. Transfer the JSON file to your PC")
    print("2. Run the fingerprint generator to create profiles")
    print("3. Integrate with FluxMart EXE")


if __name__ == "__main__":
    main()