import os
import sys
import warnings

sys.dont_write_bytecode = True

# Suppress the noisy urllib3/chardet version mismatch warning from requests
try:
    from requests.packages.urllib3.exceptions import RequestsDependencyWarning
    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except Exception:
    pass
warnings.filterwarnings("ignore", message=".*urllib3.*", category=Warning)
warnings.filterwarnings("ignore", message=".*chardet.*", category=Warning)

# ── Use canonical environment detection ──
from MSK_core.Utils.env import is_frozen as _is_frozen, get_base_path as _find_base_path, init_exe_environment

_NO_WINDOW: int = 0x08000000 if sys.platform == 'win32' else 0

if sys.platform == 'win32' and _NO_WINDOW:
    import subprocess as _subprocess
    _original_popen = _subprocess.Popen

    class _NoWindowPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            if kwargs.get('creationflags', 0) == 0:
                kwargs['creationflags'] = _NO_WINDOW
            super().__init__(*args, **kwargs)

    _subprocess.Popen = _NoWindowPopen

import time
import threading
import hashlib

init_exe_environment()

from flask import Flask, send_from_directory, render_template
import webview

from MSK_core.gui_controller import GUIController, _kill_gen_browsers_only
from MSK_core.Utils.auto_login import AutoLogin


def get_base_path():
    return _find_base_path()


base_path = get_base_path()

app = Flask(
    __name__,
    template_folder=os.path.join(base_path, 'templates'),
    static_folder=os.path.join(base_path, 'static')
)

# Ensure Flask uses UTF-8 encoding for JSON responses
app.config['JSON_AS_ASCII'] = False
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'


@app.route('/')
def index():
    try:
        auto_login = AutoLogin()
        saved = {}
        if auto_login.has_saved_credentials():
            credentials = auto_login.load_credentials()
            if credentials:
                saved = {
                    "username": credentials.get("username", ""),
                    "password": credentials.get("password", ""),
                    "auto_login_enabled": auto_login.is_enabled()
                }
        return render_template('index.html', saved=saved)
    except:
        return render_template('index.html', saved={})


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(os.path.join(base_path, 'static'), filename)


@app.route('/favicon.ico')
def favicon():
    # Uses your app's base_path + already-imported send_from_directory (EXE-safe!)
    return send_from_directory(base_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')


def run_flask():
    app.run(debug=False, port=3000, use_reloader=False, threaded=True)


if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()

    try:
        from MSK_core.Utils.anticrack import init_anticrack
        init_anticrack()
    except:
        pass

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    controller = GUIController()

    main_window = webview.create_window(
        title="FluxMart",
        url="http://127.0.0.1:3000",
        js_api=controller,
        width=1000,
        height=685,
        frameless=True,
        easy_drag=True,
        min_size=(800, 500),
        background_color='#000000',
        hidden=True
    )
    
    controller.set_window(main_window)

    def show_window():
        main_window.events.loaded.wait()
        main_window.show()

    def on_closed():
        _kill_gen_browsers_only()
        os._exit(0)

    main_window.events.closed += on_closed

    # Fixed to also point to your root favicon.ico if static/img/icon.ico doesn't exist
    icon_path = os.path.join(base_path, "favicon.ico")
    if os.path.exists(icon_path):
        webview.start(show_window, debug=False, icon=icon_path)
    else:
        webview.start(show_window, debug=False)
