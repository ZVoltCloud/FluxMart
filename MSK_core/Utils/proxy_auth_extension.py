import os
import json
import tempfile
from typing import Optional


def create_proxy_auth_extension(username: str, password: str) -> str:
    """Generate a lightweight unpacked Chrome/Brave extension that automatically
    answers HTTP 407 proxy authentication challenges on startup and for every
    subsequent request, completely eliminating the native 'Sign in' popup dialog.

    Uses MV2 webRequestBlocking for broad compatibility (Chrome <121, all Brave).
    The CDP Fetch.AuthRequired handler in _create_browser is the primary auth path;
    this extension is the fallback for edge cases where CDP auth fires too late.
    """
    ext_dir = tempfile.mkdtemp(prefix="msk_proxy_auth_")

    # MV2 manifest -- widest compatibility across Brave + Chrome versions.
    # webRequestBlocking is still supported in MV2 extensions even in Chrome 130+.
    # Do NOT use MV3 declarativeNetRequest for proxy auth -- it cannot inject credentials.
    manifest = {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "MSK Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"],
            "persistent": True
        },
        # Do NOT include minimum_chrome_version -- it causes "version not supported"
        # on Brave builds whose reported version string doesn't match numeric ordering.
    }

    u_json = json.dumps(str(username))
    p_json = json.dumps(str(password))

    # background.js:
    # - Handles proxy 407 challenges (blocking mode -- required for credential injection).
    # - Skips non-proxy auth challenges (server 401) to avoid breaking site logins.
    # - Registers early so it handles the very first request (persistent: true).
    bg_js = f"""// MSK Proxy Auth -- auto-authenticate all proxy 407 challenges
(function() {{
    var _u = {u_json};
    var _p = {p_json};

    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            // Only handle proxy auth (407), not server auth (401)
            if (details.isProxy) {{
                return {{
                    authCredentials: {{
                        username: _u,
                        password: _p
                    }}
                }};
            }}
            // Let server auth challenges pass through unchanged
            return {{}};
        }},
        {{ urls: ["<all_urls>"] }},
        ["blocking"]
    );
}})();
"""

    with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(ext_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(bg_js)

    return os.path.normpath(ext_dir)
