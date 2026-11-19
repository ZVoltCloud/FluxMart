import os
import sys
import json
import base64
import hashlib
from typing import Optional, Dict, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .utils import get_base_path


def _generate_hwid() -> str:
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
        return "N/A"


def get_machine_key() -> bytes:
    hwid = _generate_hwid()
    return hashlib.sha256(hwid.encode()).digest()


def get_encryption_key() -> bytes:
    machine_key = get_machine_key()
    salt = b'FluxMarten_Salt_2026'

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    return base64.urlsafe_b64encode(kdf.derive(machine_key))


class AutoLogin:
    def __init__(self):
        self.data_dir = os.path.join(get_base_path(), "data", "credentials")
        self.credentials_file = os.path.join(self.data_dir, ".login-credentials")
        self.config_file = os.path.join(get_base_path(), "data", "autologin.json")
        self._ensure_data_dir()
        self._migrate_old_credentials()

    def _ensure_data_dir(self):
        os.makedirs(self.data_dir, exist_ok=True)

    def _migrate_old_credentials(self):
        """Migrate old .credentials to new path and name if it exists."""
        old_path = os.path.join(get_base_path(), "data", ".credentials")
        if os.path.exists(old_path) and not os.path.exists(self.credentials_file):
            try:
                import shutil
                shutil.move(old_path, self.credentials_file)
            except:
                pass

    def _get_fernet(self) -> Fernet:
        return Fernet(get_encryption_key())

    def is_enabled(self) -> bool:
        try:
            if not os.path.exists(self.credentials_file):
                return False
                
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("auto_login_enabled", False)
        except Exception:
            pass
        return False

    def set_enabled(self, enabled: bool):
        try:
            config = {}
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except:
                    pass

            config["auto_login_enabled"] = enabled

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        except Exception:
            pass

    def save_credentials(self, username: str, password: str) -> bool:
        try:
            fernet = self._get_fernet()

            credentials = {
                "username": username,
                "password": password
            }

            data = json.dumps(credentials).encode()
            encrypted = fernet.encrypt(data)

            with open(self.credentials_file, "wb") as f:
                f.write(encrypted)

            return True
        except Exception:
            return False

    def load_credentials(self) -> Optional[Dict[str, str]]:
        try:
            if not os.path.exists(self.credentials_file):
                return None

            fernet = self._get_fernet()

            with open(self.credentials_file, "rb") as f:
                encrypted = f.read()

            decrypted = fernet.decrypt(encrypted)
            credentials = json.loads(decrypted.decode())

            if credentials and isinstance(credentials, dict) and credentials.get("username") and credentials.get("password"):
                return credentials
            else:
                self.clear_credentials()
                return None
        except Exception:
            self.clear_credentials()
            return None

    def clear_credentials(self):
        try:
            if os.path.exists(self.credentials_file):
                os.remove(self.credentials_file)
        except Exception:
            pass

    def has_saved_credentials(self) -> bool:
        return os.path.exists(self.credentials_file)

    def disable_auto_login(self):
        self.set_enabled(False)
        self.clear_credentials()


def ask_enable_auto_login() -> bool:
    from rich.console import Console
    from rich.text import Text

    console = Console()

    console.print()
    prompt = Text()
    prompt.append("[", style="#c0c0c0")
    prompt.append("Auto Login", style="dim")
    prompt.append("]", style="#c0c0c0")
    prompt.append(" Do you want to enable auto login for next time? (y/n): ", style="white")
    console.print(prompt, end="")

    try:
        choice = input().strip().lower()
        return choice in ["y", "yes", "1"]
    except:
        return False
