import os
import json as jsond
import time
import binascii
import platform
import subprocess
import sys
import hashlib
import uuid
import threading
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Callable, Any

try:
    if os.name == 'nt':
        import win32security
    import requests
except ModuleNotFoundError:
    import requests

KEYAUTH_APP_NAME = "R.p.s.shikhari's Application"
KEYAUTH_OWNER_ID = "GKV1swkOjp"
KEYAUTH_VERSION = "1.0"

class KeyAuthError(Exception):
    """Base exception for KeyAuth errors"""
    pass

class api:
    name = ownerid = version = hash_to_check = ""

    def __init__(self, name, ownerid, version, hash_to_check, gui_mode=False):
        self.gui_mode = gui_mode
        if len(ownerid) != 10:
            raise KeyAuthError("Invalid OwnerID.\nGo to `https://keyauth.cc/app/,`  copy the Python code, and replace the code in main.py!")

        self.name = name
        self.ownerid = ownerid
        self.version = version
        self.hash_to_check = hash_to_check
        self.init()

    sessionid = enckey = ""
    initialized = False

    def init(self):
        if self.sessionid != "":
            raise KeyAuthError("The application is already initialized!")

        post_data = {
            "type": "init",
            "ver": self.version,
            "hash": self.hash_to_check,
            "name": self.name,
            "ownerid": self.ownerid
        }

        response = self.__do_request(post_data)

        if response == "KeyAuth_Invalid":
            raise KeyAuthError("The application does not exist!")

        json = jsond.loads(response)

        if json["message"] == "invalidver":
            if json.get("download") and json["download"] != "":
                raise KeyAuthError(f"Invalid application version.\nDownload the latest version from our dashboard or our discord server!\n\nOur dashboard: `http://mskhub.shop/` \n\nOur discord server: `https://discord.gg/BcwHsh3zBk` ")
            else:
                raise KeyAuthError("Invalid application version.\nDownload the latest version from our dashboard or our discord server!\n\nOur dashboard: `http://mskhub.shop/` \n\nOur discord server: `https://discord.gg/BcwHsh3zBk` ")

        if not json["success"]:
            raise KeyAuthError(json["message"])

        self.sessionid = json["sessionid"]
        self.initialized = True

    def register(self, user, password, license, hwid=None):
        self.checkinit()
        if hwid is None:
            hwid = others.get_hwid()

        post_data = {
            "type": "register",
            "username": user,
            "pass": password,
            "key": license,
            "hwid": hwid,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }

        response = self.__do_request(post_data)
        json = jsond.loads(response)

        if json["success"]:
            self.__load_user_data(json["info"])
            return True
        else:
            raise KeyAuthError(json["message"])

    def upgrade(self, user, license):
        self.checkinit()

        post_data = {
            "type": "upgrade",
            "username": user,
            "key": license,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }

        response = self.__do_request(post_data)
        json = jsond.loads(response)

        if json["success"]:
            raise KeyAuthError("Upgrade completed.\nPlease restart the program and log in again!")
        else:
            raise KeyAuthError(json["message"])

    def login(self, user, password, hwid=None):
        self.checkinit()
        if hwid is None:
            hwid = others.get_hwid()

        post_data = {
            "type": "login",
            "username": user,
            "pass": password,
            "hwid": hwid,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }

        response = self.__do_request(post_data)
        json = jsond.loads(response)

        if json["success"]:
            self.__load_user_data(json["info"])
            return True
        else:
            self.last_error = json.get("message", "Login failed")
            raise KeyAuthError(json["message"])

    def license(self, key, hwid=None):
        self.checkinit()
        if hwid is None:
            hwid = others.get_hwid()

        post_data = {
            "type": "license",
            "key": key,
            "hwid": hwid,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }

        response = self.__do_request(post_data)
        json = jsond.loads(response)

        if json["success"]:
            self.__load_user_data(json["info"])
            return True
        else:
            raise KeyAuthError(json["message"])

    def var(self, name):
        self.checkinit()
        post_data = {
            "type": "var",
            "varid": name,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return json["message"]
        else:
            raise KeyAuthError(json["message"])

    def getvar(self, var_name):
        self.checkinit()
        post_data = {
            "type": "getvar",
            "var": var_name,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return json["response"]
        else:
            raise KeyAuthError("Variable not found or invalid!")

    def setvar(self, var_name, var_data):
        self.checkinit()
        post_data = {
            "type": "setvar",
            "var": var_name,
            "data": var_data,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return True
        else:
            raise KeyAuthError(json["message"])

    def ban(self):
        self.checkinit()
        post_data = {
            "type": "ban",
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return True
        else:
            raise KeyAuthError(json["message"])

    def file(self, fileid):
        self.checkinit()
        post_data = {
            "type": "file",
            "fileid": fileid,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if not json["success"]:
            raise KeyAuthError(json["message"])
        return binascii.unhexlify(json["contents"])

    def webhook(self, webid, param, body="", conttype=""):
        self.checkinit()
        post_data = {
            "type": "webhook",
            "webid": webid,
            "params": param,
            "body": body,
            "conttype": conttype,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return json["message"]
        else:
            raise KeyAuthError(json["message"])

    def check(self):
        self.checkinit()
        post_data = {
            "type": "check",
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            if "info" in json:
                self.__load_user_data(json["info"])
            return True
        return False

    def checkblacklist(self):
        self.checkinit()
        hwid = others.get_hwid()
        post_data = {
            "type": "checkblacklist",
            "hwid": hwid,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        return json["success"]

    def log(self, message):
        self.checkinit()
        post_data = {
            "type": "log",
            "pcuser": os.getenv('username'),
            "message": message,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        self.__do_request(post_data)

    def fetchOnline(self):
        self.checkinit()
        post_data = {
            "type": "fetchOnline",
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return json["users"] if len(json["users"]) > 0 else None
        else:
            return None

    def fetchStats(self):
        self.checkinit()
        post_data = {
            "type": "fetchStats",
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            self.__load_app_data(json["appinfo"])

    def chatGet(self, channel):
        self.checkinit()
        post_data = {
            "type": "chatget",
            "channel": channel,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return json["messages"]
        else:
            return None

    def chatSend(self, message, channel):
        self.checkinit()
        post_data = {
            "type": "chatsend",
            "message": message,
            "channel": channel,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        return json["success"]

    def checkinit(self):
        if not self.initialized:
            raise KeyAuthError("Initialize the application first to use the functions!")

    def changeUsername(self, username):
        self.checkinit()
        post_data = {
            "type": "changeUsername",
            "newUsername": username,
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return True
        else:
            raise KeyAuthError(json["message"])

    def logout(self):
        self.checkinit()
        post_data = {
            "type": "logout",
            "sessionid": self.sessionid,
            "name": self.name,
            "ownerid": self.ownerid
        }
        response = self.__do_request(post_data)
        json = jsond.loads(response)
        if json["success"]:
            return True
        else:
            raise KeyAuthError(json["message"])

    def __do_request(self, post_data):
        try:
            response = requests.post(
                "https://keyauth.win/api/1.3/", data=post_data, timeout=10
            )
            if post_data["type"] == "log" or post_data["type"] == "file":
                return response.text

            return response.text

        except requests.exceptions.Timeout:
            raise KeyAuthError("Request timed out.\nServer unreachable.")

    class application_data_class:
        numUsers = numKeys = app_ver = customer_panel = onlineUsers = ""

    class user_data_class:
        username = ip = hwid = expires = createdate = lastlogin = subscription = subscriptions = ""

    user_data = user_data_class()
    app_data = application_data_class()
    last_error = ""

    def __load_app_data(self, data):
        self.app_data.numUsers = data["numUsers"]
        self.app_data.numKeys = data["numKeys"]
        self.app_data.app_ver = data["version"]
        self.app_data.customer_panel = data["customerPanelLink"]
        self.app_data.onlineUsers = data["numOnlineUsers"]

    def __load_user_data(self, data):
        self.user_data.username = data["username"]
        self.user_data.ip = data["ip"]
        self.user_data.hwid = data["hwid"] or "N/A"
        self.user_data.expires = data["subscriptions"][0]["expiry"]
        self.user_data.createdate = data["createdate"]
        self.user_data.lastlogin = data["lastlogin"]
        self.user_data.subscription = data["subscriptions"][0]["subscription"]
        self.user_data.subscriptions = data["subscriptions"]

    def get_hwid(self):
        return others.get_hwid()

class others:
    @staticmethod
    def get_hwid():
        if platform.system() == "Linux":
            with open("/etc/machine-id") as f:
                hwid = f.read().strip()
                return hashlib.sha256(hwid.encode()).hexdigest()
        elif platform.system() == 'Windows':
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
                pass
            return "N/A"
        elif platform.system() == 'Darwin':
            output = subprocess.Popen("ioreg -l | grep IOPlatformSerialNumber", stdout=subprocess.PIPE, shell=True).communicate()[0]
            serial = output.decode().split('=', 1)[1].replace(' ', '')
            hwid = serial[1:-2]
            return hashlib.sha256(hwid.encode()).hexdigest()
        return "N/A"

keyauthapp: Optional[api] = None

_local_api_lock = threading.Lock()
_local_api_server = None
_local_api_get_stats: Optional[Callable[[], dict[str, Any]]] = None
_local_api_get_sessions: Optional[Callable[[], Any]] = None
_mongo_lock = threading.Lock()
_mongo_client = None
_mongo_uri = "mongodb+srv://brothailovearch_db_user:aAq12dX4SZ360Ufs@mskev.rkz2eug.mongodb.net/"
_mongo_client_uri = "MSKEV"
_mongo_collection_name = "MSKSTATS"
_mongo_cached_uri = ""
_mongo_backoff_until = 0.0
_mongo_backoff_seconds = 2.0
_snapshot_lock = threading.Lock()
_snapshot_last_digest = ""
_mongo_last_saved_digest = ""
_mongo_last_saved_time = 0.0
_snapshot_last_payload: dict[str, Any] = {}
_mongo_last_saved_digest_by_user: dict[str, str] = {}
_mongo_last_saved_time_by_user: dict[str, float] = {}
_keyauth_var_last_digest_by_user: dict[str, str] = {}

LOCAL_API_ENABLE_STATS_HTTP = False
LOCAL_API_ENABLE_ACC_DS_HTTP = False
KEYAUTH_STATS_VAR_PREFIX = "acc_ds_"


def _local_api_is_frozen() -> bool:
    if getattr(sys, "frozen", False):
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


def _local_api_base_path() -> str:
    if _local_api_is_frozen():
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


def _local_api_output_file(filename: str) -> str:
    return os.path.join(_local_api_base_path(), "data", "output", filename)


def _local_api_count_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0
    except Exception:
        return 0


def _local_api_read_lines(path: str, limit: int = 5000) -> list[str]:
    out: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if len(out) >= limit:
                    break
                line = line.strip()
                if line:
                    out.append(line)
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return out


def configure_local_api(
    *,
    get_stats: Optional[Callable[[], dict[str, Any]]] = None,
    get_sessions: Optional[Callable[[], Any]] = None,
):
    global _local_api_get_stats, _local_api_get_sessions
    with _local_api_lock:
        if get_stats is not None:
            _local_api_get_stats = get_stats
        if get_sessions is not None:
            _local_api_get_sessions = get_sessions


def _local_api_snapshot_files() -> dict[str, Any]:
    tokens_file = _local_api_output_file("tokens.txt")
    locked_file = _local_api_output_file("locked.txt")
    invalid_file = _local_api_output_file("invalid.txt")
    linkverify_file = _local_api_output_file("linkverify.txt")
    checked_valid_file = _local_api_output_file("checked_valid.txt")
    checked_invalid_file = _local_api_output_file("checked_invalid.txt")

    tokens_count = _local_api_count_lines(tokens_file)
    locked_count = _local_api_count_lines(locked_file)
    invalid_count = _local_api_count_lines(invalid_file)
    linkverify_count = _local_api_count_lines(linkverify_file)

    checked_valid_count = _local_api_count_lines(checked_valid_file)
    checked_invalid_count = _local_api_count_lines(checked_invalid_file)

    return {
        "paths": {
            "tokens": tokens_file,
            "locked": locked_file,
            "invalid": invalid_file,
            "linkverify": linkverify_file,
            "checked_valid": checked_valid_file,
            "checked_invalid": checked_invalid_file,
        },
        "counts": {
            "tokens": tokens_count,
            "locked": locked_count,
            "invalid": invalid_count,
            "linkverify": linkverify_count,
            "checked_valid": checked_valid_count,
            "checked_invalid": checked_invalid_count,
        },
        "accounts": {
            "created": tokens_count + locked_count + invalid_count + linkverify_count,
            "valid": tokens_count,
            "invalid": invalid_count,
        },
    }


def _local_api_keyauth_session() -> dict[str, Any]:
    try:
        sess = {}
        if keyauthapp is None:
            return {"active": False}
        sess["active"] = bool(getattr(keyauthapp, "initialized", False))
        sess["sessionid"] = getattr(keyauthapp, "sessionid", "") or ""
        user = getattr(keyauthapp, "user_data", None)
        if user is not None:
            sess["user"] = {
                "username": getattr(user, "username", "") or "",
                "ip": getattr(user, "ip", "") or "",
                "hwid": getattr(user, "hwid", "") or "",
                "expires": getattr(user, "expires", "") or "",
                "createdate": getattr(user, "createdate", "") or "",
                "lastlogin": getattr(user, "lastlogin", "") or "",
                "subscription": getattr(user, "subscription", "") or "",
            }
        return sess
    except Exception:
        return {"active": False}


def _local_api_discord_user() -> dict[str, Any]:
    return {"connected": False}


def _local_api_get_mongo_uri() -> str:
    uri = (os.getenv("MSK_MONGO_URI") or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "").strip()
    if uri:
        return uri
    try:
        return str(_mongo_uri or "").strip()
    except Exception:
        return ""


def _local_api_mask_mongo_uri(uri: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit

        s = urlsplit(uri)
        netloc = s.netloc
        if "@" in netloc:
            _, host = netloc.split("@", 1)
            netloc = f"***@{host}"
        return urlunsplit((s.scheme, netloc, s.path, s.query, s.fragment))
    except Exception:
        return ""


def _local_api_mongo_get_collection():
    uri = _local_api_get_mongo_uri()
    if not uri:
        return None, {"enabled": False, "saved": False}

    try:
        from pymongo import MongoClient
    except Exception:
        return None, {
            "enabled": True,
            "saved": False,
            "uri_masked": _local_api_mask_mongo_uri(uri),
            "error": "pymongo_not_installed",
        }

    global _mongo_backoff_until, _mongo_backoff_seconds
    now = time.time()
    if _mongo_backoff_until and now < _mongo_backoff_until:
        return None, {
            "enabled": True,
            "saved": False,
            "uri_masked": _local_api_mask_mongo_uri(uri),
            "error": "mongo_backoff",
        }

    db_name = ""
    try:
        db_name = str(_mongo_client_uri or "").strip()
    except Exception:
        db_name = ""
    try:
        coll_name = str(_mongo_collection_name or "").strip() or "acc_ds"
    except Exception:
        coll_name = "acc_ds"
    try:
        if not db_name:
            from urllib.parse import urlsplit

            s = urlsplit(uri)
            path = (s.path or "").lstrip("/")
            if path:
                db_name = path.split("/", 1)[0]
        if not db_name:
            db_name = "FluxMart"
    except Exception:
        if not db_name:
            db_name = "FluxMart"

    with _mongo_lock:
        global _mongo_client, _mongo_cached_uri

        if _mongo_client is None or _mongo_cached_uri != uri:
            try:
                if _mongo_client is not None:
                    _mongo_client.close()
            except Exception:
                pass

            try:
                _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=1500, connectTimeoutMS=1500)
                _mongo_cached_uri = uri
                _mongo_backoff_until = 0.0
                _mongo_backoff_seconds = 2.0
            except Exception as e:
                _mongo_client = None
                _mongo_cached_uri = ""
                _mongo_backoff_until = time.time() + _mongo_backoff_seconds
                _mongo_backoff_seconds = min(_mongo_backoff_seconds * 2.0, 60.0)
                return None, {
                    "enabled": True,
                    "saved": False,
                    "uri_masked": _local_api_mask_mongo_uri(uri),
                    "error": str(e)[:200],
                }

        client = _mongo_client

    try:
        client.admin.command("ping")
    except Exception as e:
        _mongo_backoff_until = time.time() + _mongo_backoff_seconds
        _mongo_backoff_seconds = min(_mongo_backoff_seconds * 2.0, 60.0)
        return None, {
            "enabled": True,
            "saved": False,
            "uri_masked": _local_api_mask_mongo_uri(uri),
            "error": str(e)[:200],
        }

    coll = client[db_name][coll_name]
    return coll, {
        "enabled": True,
        "saved": False,
        "uri_masked": _local_api_mask_mongo_uri(uri),
    }


def _local_api_mongo_save(snapshot: dict[str, Any]) -> dict[str, Any]:
    global _mongo_last_saved_time
    coll, status = _local_api_mongo_get_collection()
    if coll is None:
        return status

    try:
        doc = dict(snapshot)
        doc.pop("mongodb", None)
        now_dt = datetime.utcnow()
        now_ts = time.time()
        coll.update_one(
            {"_id": "latest"},
            {
                "$set": {
                    "data": doc,
                    "updated_at": now_dt,
                    "date": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp": int(now_ts),
                }
            },
            upsert=True,
        )
        _mongo_last_saved_time = now_ts
        status["saved"] = True
        return status
    except Exception as e:
        status["saved"] = False
        status["error"] = str(e)[:200]
        return status


def _local_api_snapshot_digest(core: dict[str, Any]) -> str:
    try:
        payload = jsond.dumps(core, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def _local_api_get_keyauth_username(snapshot: Optional[dict[str, Any]] = None) -> str:
    try:
        if snapshot is not None and isinstance(snapshot.get("keyauth"), dict):
            ku = snapshot.get("keyauth") or {}
            user = ku.get("user") if isinstance(ku.get("user"), dict) else {}
            username = str(user.get("username", "") or "").strip()
            if username:
                return username
    except Exception:
        pass

    try:
        if keyauthapp is not None:
            user = getattr(keyauthapp, "user_data", None)
            username = str(getattr(user, "username", "") or "").strip() if user is not None else ""
            if username:
                return username
    except Exception:
        pass

    try:
        from .auto_login import AutoLogin

        creds = AutoLogin().load_credentials()
        if creds and isinstance(creds, dict):
            username = str(creds.get("username", "") or "").strip()
            if username:
                return username
    except Exception:
        pass

    return ""


def _local_api_mongo_save_if_changed(digest: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    global _mongo_last_saved_digest

    coll, status = _local_api_mongo_get_collection()
    if coll is None:
        return status

    username = _local_api_get_keyauth_username(snapshot)

    if not username:
        status["saved"] = False
        status["skipped"] = True
        status["reason"] = "missing_keyauth_username"
        if status.get("enabled") is True and not status.get("uri_masked"):
            status["uri_masked"] = _local_api_mask_mongo_uri(_local_api_get_mongo_uri())
        return status

    doc_id = f"latest:{username}"
    now_ts = time.time()
    last_user_time = _mongo_last_saved_time_by_user.get(username, 0.0)
    force_update = (now_ts - last_user_time) >= 5.0

    with _snapshot_lock:
        if not force_update:
            if digest and _mongo_last_saved_digest_by_user.get(username) == digest:
                status["saved"] = False
                status["skipped"] = True
                if status.get("enabled") is True and not status.get("uri_masked"):
                    status["uri_masked"] = _local_api_mask_mongo_uri(_local_api_get_mongo_uri())
                status["doc_id"] = doc_id
                return status

            if digest and _mongo_last_saved_digest == digest:
                status["saved"] = False
                status["skipped"] = True
                if status.get("enabled") is True and not status.get("uri_masked"):
                    status["uri_masked"] = _local_api_mask_mongo_uri(_local_api_get_mongo_uri())
                status["doc_id"] = doc_id
                return status

    try:
        doc = dict(snapshot)
        doc.pop("mongodb", None)
        now_dt = datetime.utcnow()
        coll.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "data": doc,
                    "updated_at": now_dt,
                    "date": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp": int(now_ts),
                    "keyauth_username": username,
                    "digest": digest,
                }
            },
            upsert=True,
        )
        with _snapshot_lock:
            _mongo_last_saved_digest = digest or _mongo_last_saved_digest
            if digest and username:
                _mongo_last_saved_digest_by_user[username] = digest
            _mongo_last_saved_time_by_user[username] = now_ts
        status["saved"] = True
        status["skipped"] = False
        if status.get("enabled") is True and not status.get("uri_masked"):
            status["uri_masked"] = _local_api_mask_mongo_uri(_local_api_get_mongo_uri())
        status["doc_id"] = doc_id
        return status
    except Exception as e:
        status["saved"] = False
        status["skipped"] = False
        status["error"] = str(e)[:200]
        if status.get("enabled") is True and not status.get("uri_masked"):
            status["uri_masked"] = _local_api_mask_mongo_uri(_local_api_get_mongo_uri())
        status["doc_id"] = doc_id
        return status


def _local_api_keyauth_update_var_if_changed(digest: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    username = _local_api_get_keyauth_username(snapshot)

    if not username:
        return {"enabled": False}

    var_name = f"{KEYAUTH_STATS_VAR_PREFIX}{username}"

    with _snapshot_lock:
        if digest and _keyauth_var_last_digest_by_user.get(username) == digest:
            return {"enabled": True, "updated": False, "var": var_name}

    try:
        if keyauthapp is None:
            return {"enabled": False, "updated": False, "var": var_name}
        if not bool(getattr(keyauthapp, "initialized", False)):
            return {"enabled": False, "updated": False, "var": var_name}

        files = snapshot.get("files") or {}
        accounts = files.get("accounts") if isinstance(files, dict) else {}
        counts = files.get("counts") if isinstance(files, dict) else {}

        sessions = snapshot.get("sessions") or {}
        active = None
        if isinstance(sessions, dict):
            if "active" in sessions:
                active = sessions.get("active")
            elif isinstance(sessions.get("generator"), dict) and "active" in sessions["generator"]:
                active = sessions["generator"].get("active")

        compact = {
            "created": accounts.get("created") if isinstance(accounts, dict) else None,
            "valid": accounts.get("valid") if isinstance(accounts, dict) else None,
            "invalid": accounts.get("invalid") if isinstance(accounts, dict) else None,
            "counts": counts if isinstance(counts, dict) else {},
            "active_sessions": active,
            "timestamp": snapshot.get("timestamp"),
        }

        keyauthapp.setvar(var_name, jsond.dumps(compact, separators=(",", ":")))

        with _snapshot_lock:
            if digest:
                _keyauth_var_last_digest_by_user[username] = digest

        return {"enabled": True, "updated": True, "var": var_name}
    except Exception as e:
        return {"enabled": True, "updated": False, "var": var_name, "error": str(e)[:200]}


def _local_api_build_snapshot() -> tuple[dict[str, Any], str]:
    runtime_stats: dict[str, Any] = {}
    sessions: Any = None

    with _local_api_lock:
        get_stats = _local_api_get_stats
        get_sessions = _local_api_get_sessions

    if get_stats is not None:
        try:
            runtime_stats = get_stats() or {}
        except Exception as e:
            runtime_stats = {"error": str(e)[:200]}
    if get_sessions is not None:
        try:
            sessions = get_sessions()
        except Exception as e:
            sessions = {"error": str(e)[:200]}

    file_stats = _local_api_snapshot_files()

    from .utils import load_config
    config = load_config()

    def format_val(val):
        if not val or val == "False": return "False"
        if val == "onlinesim": return "OnlineSim"
        if val == "hero_sms": return "HeroSms"
        if val == "hotmail007": return "Hotmail007"
        if val == "cybertemp": return "Cybertemp"
        if val == "mailcow": return "Mailcow"
        if val == "zeus": return "Zeus"
        if val == "fivesim": return "Fivesim"
        if val == "camoufox": return "Camoufox"
        if val == "brave": return "Brave"
        if val == "chromium2": return "Chromium 2"
        if val == "clearcote": return "Clearcote"
        if val == "groq": return "Groq"
        if val == "ollama": return "Ollama"
        if val == "openrouter": return "Openrouter"
        if val == "gemini": return "Gemini"
        return str(val).capitalize()

    browser = format_val(config.get("browser_method", "brave"))
    
    email_provider = "False"
    providers = config.get("email_providers", {})
    for p_name, p_data in providers.items():
        if isinstance(p_data, dict) and p_data.get("enabled"):
            email_provider = format_val(p_name)
            break
            
    phone_verification = "False"
    for p_name in ["fivesim", "onlinesim", "hero_sms"]:
        p_data = config.get(p_name)
        if isinstance(p_data, dict) and p_data.get("enabled"):
            phone_verification = format_val(p_name)
            break
            
    ai_solver = "False"
    solver_ai = config.get("solver_ai", {})
    if isinstance(solver_ai, dict):
        for s_name, s_enabled in solver_ai.items():
            if s_enabled:
                ai_solver = format_val(s_name)
                break

    core = {
        "files": file_stats,
        "runtime": runtime_stats,
        "sessions": sessions,
        "keyauth": _local_api_keyauth_session(),
        "discord": _local_api_discord_user(),
        "config": {
            "headless": bool(config.get("headless", False)),
            "auto_solver_captcha": bool(config.get("auto_solver_captcha", False)),
            "browser": browser,
            "email_provider": email_provider,
            "phone_verification": phone_verification,
            "ai_solver": ai_solver,
        }
    }

    digest = _local_api_snapshot_digest(core)
    out = dict(core)
    out["timestamp"] = time.time()
    out["mongodb"] = _local_api_mongo_save_if_changed(digest, out)
    out["keyauth_var"] = _local_api_keyauth_update_var_if_changed(digest, out)
    return out, digest


class _LocalAPIServer:
    def __init__(self, host: str, port: int):
        from flask import Flask, jsonify
        from werkzeug.serving import make_server

        self.host = host
        self.port = port
        self._app = Flask("msk_local_stats_api")
        self._server = make_server(host, port, self._app, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._stop_event = threading.Event()
        self._bg_thread = threading.Thread(target=self._background_loop, daemon=True)

        @self._app.get("/health")
        def _health():
            return jsonify({"ok": True})

        @self._app.get("/stats")
        def _stats():
            global _snapshot_last_digest, _snapshot_last_payload
            if not LOCAL_API_ENABLE_STATS_HTTP:
                from flask import abort
                abort(404)
            with _snapshot_lock:
                if _snapshot_last_payload:
                    return jsonify(_snapshot_last_payload)
            out, digest = _local_api_build_snapshot()
            with _snapshot_lock:
                _snapshot_last_digest = digest or _snapshot_last_digest
                _snapshot_last_payload = out
            return jsonify(out)

        @self._app.get("/stats/stream")
        def _stats_stream():
            from flask import Response, stream_with_context

            if not LOCAL_API_ENABLE_STATS_HTTP:
                from flask import abort
                abort(404)

            def _gen():
                last = ""
                while True:
                    with _snapshot_lock:
                        digest = _snapshot_last_digest
                        out = dict(_snapshot_last_payload) if _snapshot_last_payload else None
                    if out is not None and digest and digest != last:
                        last = digest
                        yield f"event: stats\ndata: {jsond.dumps(out, separators=(',', ':'))}\n\n"
                    time.sleep(0.5)

            return Response(
                stream_with_context(_gen()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )

        @self._app.get("/")
        def _root():
            from flask import redirect
            if not LOCAL_API_ENABLE_ACC_DS_HTTP:
                from flask import abort
                abort(404)
            return redirect("/acc-ds", code=302)

        @self._app.get("/acc-ds")
        def _acc_ds():
            from flask import Response
            if not LOCAL_API_ENABLE_ACC_DS_HTTP:
                from flask import abort
                abort(404)

            html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MSK ACC-DS</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; background:#0b0b10; color:#e8e8f0; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 20px; }
    .top { display:flex; gap:14px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
    .title { font-size: 18px; font-weight: 700; letter-spacing: .2px; }
    .muted { color:#a6a6bf; font-size: 12px; }
    .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap: 12px; margin-top: 14px; }
    .card { grid-column: span 6; background:#12121a; border:1px solid #222236; border-radius: 12px; padding: 14px; }
    .card h3 { margin:0 0 10px; font-size: 13px; color:#c9c9dd; font-weight: 700; text-transform: uppercase; letter-spacing:.12em; }
    .row { display:flex; align-items:center; justify-content:space-between; padding: 8px 0; border-top: 1px solid #1f1f2f; }
    .row:first-of-type { border-top: none; }
    .k { color:#a6a6bf; font-size: 13px; }
    .v { font-size: 14px; font-weight: 700; }
    .pill { font-size: 12px; padding: 4px 10px; border-radius: 999px; background:#1b1b29; border:1px solid #2a2a44; }
    .ok { color:#78f0a6; border-color:#2a6b46; background:#102116; }
    .bad { color:#ff7a7a; border-color:#6b2a2a; background:#211010; }
    .user { display:flex; align-items:center; gap: 10px; }
    .pfp { width: 34px; height: 34px; border-radius: 999px; border: 1px solid #2a2a44; background:#0f0f16; object-fit: cover; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; background:#0f0f16; border:1px solid #222236; border-radius: 10px; padding: 10px; color:#d7d7ee; font-size: 12px; }
    .card.wide { grid-column: span 12; }
    @media (max-width: 840px) { .card { grid-column: span 12; } }
    a { color:#9aa7ff; text-decoration:none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <div class="title">MSK ACC-DS</div>
        <div class="muted">Live view of <a href="/stats" target="_blank" rel="noreferrer">/stats</a></div>
      </div>
      <div class="pill" id="status">loading…</div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>Accounts</h3>
        <div class="row"><div class="k">Created</div><div class="v" id="created">-</div></div>
        <div class="row"><div class="k">Valid</div><div class="v" id="valid">-</div></div>
        <div class="row"><div class="k">Invalid</div><div class="v" id="invalid">-</div></div>
      </div>

      <div class="card">
        <h3>Sessions</h3>
        <div class="row"><div class="k">Runtime mode</div><div class="v" id="mode">-</div></div>
        <div class="row"><div class="k">Active</div><div class="v" id="activeSessions">-</div></div>
        <div class="row"><div class="k">KeyAuth</div><div class="v" id="keyauthUser">-</div></div>
        <div class="row"><div class="k">MongoDB</div><div class="v" id="mongoStatus">-</div></div>
        <div class="row"><div class="k">Mongo URI</div><div class="v" id="mongoUri">-</div></div>
      </div>

      <div class="card">
        <h3>Discord</h3>
        <div class="row">
          <div class="k">User</div>
          <div class="v user">
            <img id="pfp" class="pfp" alt="" />
            <span id="discordUser">-</span>
          </div>
        </div>
        <div class="row"><div class="k">Status</div><div class="v" id="discordStatus">-</div></div>
      </div>

      <div class="card">
        <h3>Files</h3>
        <div class="row"><div class="k">tokens.txt</div><div class="v" id="f_tokens">-</div></div>
        <div class="row"><div class="k">locked.txt</div><div class="v" id="f_locked">-</div></div>
        <div class="row"><div class="k">invalid.txt</div><div class="v" id="f_invalid">-</div></div>
        <div class="row"><div class="k">linkverify.txt</div><div class="v" id="f_linkverify">-</div></div>
      </div>

      <div class="card wide">
        <h3>Raw</h3>
        <pre id="raw">{}</pre>
      </div>
    </div>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const statusEl = $("status");
    const setStatus = (ok, text) => {
      statusEl.textContent = text;
      statusEl.className = "pill " + (ok ? "ok" : "bad");
    };

    const safe = (v) => (v === undefined || v === null) ? "-" : v;

    function applyStats(data) {
      try {

        const files = data.files || {};
        const counts = files.counts || {};
        const accounts = files.accounts || {};
        const runtime = data.runtime || {};
        const sessions = data.sessions || {};
        const keyauth = data.keyauth || {};
        const discord = data.discord || {};
        const mongodb = data.mongodb || {};

        $("created").textContent = safe(accounts.created);
        $("valid").textContent = safe(accounts.valid);
        $("invalid").textContent = safe(accounts.invalid);

        $("f_tokens").textContent = safe(counts.tokens);
        $("f_locked").textContent = safe(counts.locked);
        $("f_invalid").textContent = safe(counts.invalid);
        $("f_linkverify").textContent = safe(counts.linkverify);

        $("mode").textContent = safe(runtime.mode);

        let active = "-";
        if (sessions && sessions.active !== undefined) active = sessions.active;
        if (sessions && sessions.generator && sessions.generator.active !== undefined) active = sessions.generator.active;
        $("activeSessions").textContent = safe(active);

        const ku = (keyauth.user && keyauth.user.username) ? keyauth.user.username : "-";
        $("keyauthUser").textContent = ku;

        const mongoEnabled = mongodb.enabled === true;
        const mongoSaved = mongodb.saved === true;
        if (!mongoEnabled) {
          $("mongoStatus").textContent = "disabled";
        } else if (mongoSaved) {
          $("mongoStatus").textContent = "saved";
        } else {
          $("mongoStatus").textContent = "enabled";
        }
        $("mongoUri").textContent = mongodb.uri_masked || (mongoEnabled ? "redacted" : "-");

        if (discord.connected && discord.user) {
          const name = discord.user.global_name || discord.user.username || discord.user.id;
          $("discordUser").textContent = safe(name);
          $("discordStatus").textContent = "connected";
          $("pfp").src = discord.user.avatar_url || "";
          $("pfp").style.visibility = "visible";
        } else {
          $("discordUser").textContent = "-";
          $("discordStatus").textContent = "not connected";
          $("pfp").removeAttribute("src");
          $("pfp").style.visibility = "hidden";
        }

        $("raw").textContent = JSON.stringify(data, null, 2);
        setStatus(true, "online");
      } catch (e) {}
    }

    function startPolling() {
      async function poll() {
        try {
          const res = await fetch("/stats", { cache: "no-store" });
          if (!res.ok) throw new Error("HTTP " + res.status);
          const data = await res.json();
          applyStats(data);
        } catch (e) {
          setStatus(false, "offline");
        }
      }
      poll();
      setInterval(poll, 1000);
    }

    if (window.EventSource) {
      const es = new EventSource("/stats/stream");
      es.addEventListener("stats", (ev) => {
        try {
          applyStats(JSON.parse(ev.data));
        } catch (e) {}
      });
      es.onerror = () => {
        setStatus(false, "offline");
      };
    } else {
      startPolling();
    }
  </script>
</body>
</html>"""

            return Response(html, mimetype="text/html")

        @self._app.get("/accounts/created/count")
        def _accounts_created_count():
            from flask import jsonify
            file_stats = _local_api_snapshot_files()
            return jsonify({"count": file_stats["accounts"]["created"]})

        @self._app.get("/accounts/valid/count")
        def _accounts_valid_count():
            from flask import jsonify
            file_stats = _local_api_snapshot_files()
            return jsonify({"count": file_stats["accounts"]["valid"]})

        @self._app.get("/accounts/invalid/count")
        def _accounts_invalid_count():
            from flask import jsonify
            file_stats = _local_api_snapshot_files()
            return jsonify({"count": file_stats["accounts"]["invalid"]})

        @self._app.get("/accounts/invalid")
        def _accounts_invalid():
            from flask import jsonify
            checked_invalid = _local_api_output_file("checked_invalid.txt")
            invalid = _local_api_output_file("invalid.txt")
            lines = _local_api_read_lines(checked_invalid)
            source = "checked_invalid.txt"
            if not lines:
                lines = _local_api_read_lines(invalid)
                source = "invalid.txt"
            return jsonify({"source": source, "items": lines, "count": len(lines)})

        @self._app.get("/sessions")
        def _sessions():
            from flask import jsonify
            with _local_api_lock:
                get_sessions = _local_api_get_sessions
            if get_sessions is None:
                return jsonify({"available": False})
            try:
                return jsonify({"available": True, "data": get_sessions()})
            except Exception as e:
                return jsonify({"available": True, "error": str(e)[:200]})

        @self._app.get("/keyauth/session")
        def _keyauth_session():
            from flask import jsonify
            return jsonify(_local_api_keyauth_session())

    def start(self):
        self._thread.start()
        self._bg_thread.start()

    def stop(self):
        try:
            self._stop_event.set()
            self._server.shutdown()
        except Exception:
            pass

    def _background_loop(self):
        while not self._stop_event.is_set():
            try:
                out, digest = _local_api_build_snapshot()
                with _snapshot_lock:
                    global _snapshot_last_digest, _snapshot_last_payload
                    if digest:
                        _snapshot_last_digest = digest
                    _snapshot_last_payload = out
            except Exception:
                pass
            time.sleep(0.5)


def start_local_api(host: str = "127.0.0.1", port: int = 18272) -> bool:
    global _local_api_server
    with _local_api_lock:
        if _local_api_server is not None:
            return True
        try:
            _local_api_server = _LocalAPIServer(host=host, port=port)
            _local_api_server.start()
            return True
        except Exception:
            _local_api_server = None
            return False


def stop_local_api() -> None:
    global _local_api_server
    with _local_api_lock:
        srv = _local_api_server
        _local_api_server = None
    if srv is not None:
        try:
            srv.stop()
        except Exception:
            pass
