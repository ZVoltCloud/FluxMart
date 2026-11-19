// ─── Installer Tab ─────────────────────────────────────────────────────────

const DEP_LABELS = {
    vcredist:    "Visual C++ Redistributable x64",
    camoufox:    "camoufox",
    truedriver:  "truedriver",
    browserforge:"browserforge",
    curl_cffi:   "curl_cffi",
    greenlet:    "greenlet",
    tls_client:  "tls_client",
    requests:    "requests",
    brave:       "Brave Browser",
    chromium:    "Chrome / Chromium",
};

const DEP_NOTES = {
    vcredist:    "Required by Camoufox & TrueDriver. Missing = broken fingerprints & locked tokens.",
    camoufox:    "Stealth browser engine for account creation.",
    truedriver:  "WebDriver for Brave / Chromium / TrueDriver methods.",
    browserforge:"Fingerprint library for Camoufox.",
    curl_cffi:   "HTTP client that mimics Discord desktop TLS (Request Based API).",
    greenlet:    "Coroutine backend for Camoufox / Playwright.",
    tls_client:  "TLS fingerprinting client.",
    requests:    "Standard HTTP library.",
    brave:       "Brave browser binary — only needed for the Brave method.",
    chromium:    "Chrome/Chromium browser binary — only needed for the Chromium method.",
};

let _instLoading  = false;
let _aiHistory    = [];
let _aiThinking   = false;
let _aiPendingImg = "";   // full data-URL while waiting to send

// ─── Dependency rendering ───────────────────────────────────────────────────

function instRenderDeps(deps) {
    const list = document.getElementById("inst-dep-list");
    if (!list) return;
    if (!deps || !Object.keys(deps).length) {
        list.innerHTML = '<div class="inst-dep-row"><span style="color:var(--text-light);font-size:12px;">No data.</span></div>';
        return;
    }

    const rows = Object.entries(deps).map(([key, info]) => {
        const ok    = info.ok;
        const label = DEP_LABELS[key] || key;
        const note  = DEP_NOTES[key]  || "";
        const ver   = ok && info.version ? `<span class="inst-dep-ver">${info.version}</span>` : "";
        const path  = ok && info.path && info.path !== "Not found"
            ? `<span class="inst-dep-ver" style="color:#555;word-break:break-all;">${info.path}</span>` : "";

        let actionHtml = "";
        if (!ok && key !== "brave" && key !== "chromium") {
            actionHtml = `<div class="inst-dep-action"><button class="inst-btn inst-btn-ghost" onclick="instFix('${key}')">Install</button></div>`;
        } else if (!ok && key === "brave") {
            actionHtml = `<div class="inst-dep-action"><a href="https://brave.com/download" target="_blank" class="inst-btn inst-btn-admin" style="text-decoration:none;">Download</a></div>`;
        } else if (!ok && key === "chromium") {
            actionHtml = `<div class="inst-dep-action"><a href="https://google.com/chrome" target="_blank" class="inst-btn inst-btn-admin" style="text-decoration:none;">Download</a></div>`;
        }

        return `
        <div class="inst-dep-row">
            <span class="inst-dep-dot ${ok ? 'ok' : 'fail'}"></span>
            <div class="inst-dep-info">
                <div class="inst-dep-name ${ok ? '' : 'missing'}">${label} ${ver} ${path}</div>
                <div class="inst-dep-note">${note}</div>
            </div>
            ${actionHtml}
        </div>`;
    });

    list.innerHTML = rows.join("");
}

// ─── Refresh ───────────────────────────────────────────────────────────────

async function instRefresh() {
    if (_instLoading) return;
    _instLoading = true;
    const btn  = document.getElementById("inst-refresh-btn");
    const list = document.getElementById("inst-dep-list");
    if (btn) btn.disabled = true;
    if (list) list.innerHTML = '<div class="inst-dep-row"><span style="color:var(--text-light);font-size:12px;">Checking...</span></div>';

    try {
        const res = await window.pywebview?.api?.get_installer_status?.() ?? {};
        if (res.app_version) {
            const el = document.getElementById("inst-app-version");
            if (el) el.textContent = `Version: ${res.app_version}`;
        }
        instRenderDeps(res.deps || {});
    } catch (e) {
        if (list) list.innerHTML = `<div class="inst-dep-row"><span style="color:var(--error);font-size:12px;">Error: ${e}</span></div>`;
    }

    _instLoading = false;
    if (btn) btn.disabled = false;
}

// ─── Log helpers ───────────────────────────────────────────────────────────

function instLog(msg, type = "inf") {
    const wrap = document.getElementById("inst-log-wrap");
    const log  = document.getElementById("inst-log");
    if (!wrap || !log) return;
    wrap.style.display = "";
    const line = document.createElement("div");
    line.className = `inst-log-line ${type}`;
    line.textContent = msg;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

function instClearLog() {
    const log = document.getElementById("inst-log");
    if (log) log.innerHTML = "";
    const wrap = document.getElementById("inst-log-wrap");
    if (wrap) wrap.style.display = "none";
}

// ─── Install single dep ─────────────────────────────────────────────────────

async function instFix(dep) {
    instClearLog();
    instLog(`Installing ${dep}...`);
    try {
        const res = await window.pywebview?.api?.install_dependency?.(dep) ?? {};
        instLog(res.success ? `[OK] ${res.msg || "done"}` : `[FAIL] ${res.msg || "error"}`,
                res.success ? "ok" : "err");
    } catch (e) {
        instLog(`[ERROR] ${e}`, "err");
    }
    await instRefresh();
}

// ─── Fix All Missing ────────────────────────────────────────────────────────

async function instFixAll() {
    instClearLog();
    instLog("Opening Administrator Command Prompt to install all missing dependencies...");
    const btn = document.getElementById("inst-fix-all-btn");
    if (btn) btn.disabled = true;
    try {
        const res = await window.pywebview?.api?.install_all_dependencies?.() ?? {};
        if (res.success) {
            instLog("Please check the opened command prompt.", "ok");
            instLog("After the installation completes, close the CMD and click 'Refresh' to verify.", "ok");
        } else {
            instLog(`[FAIL] ${res.msg || "Could not open admin CMD"}`, "err");
        }
    } catch (e) {
        instLog(`[ERROR] ${e}`, "err");
    }
    setTimeout(() => { if (btn) btn.disabled = false; }, 3000);
}

// ─── Update Camoufox ────────────────────────────────────────────────────────

async function instUpdateCamoufox() {
    instClearLog();
    instLog("Fetching latest Camoufox browser data (30–60 seconds)...");
    const btn = document.getElementById("inst-update-camoufox-btn");
    if (btn) btn.disabled = true;
    try {
        const res = await window.pywebview?.api?.update_camoufox?.() ?? {};
        instLog(res.success ? `[OK] ${res.msg}` : `[FAIL] ${res.msg}`,
                res.success ? "ok" : "err");
    } catch (e) {
        instLog(`[ERROR] ${e}`, "err");
    }
    if (btn) btn.disabled = false;
}


// ─── AI Chat ────────────────────────────────────────────────────────────────

// Image pick → base64 data-URL
function instAiImagePicked(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        _aiPendingImg = e.target.result;   // full data-URL
        const thumb = document.getElementById("inst-ai-img-thumb");
        const prev  = document.getElementById("inst-ai-img-preview");
        if (thumb) thumb.src = _aiPendingImg;
        if (prev)  prev.style.display = "";
    };
    reader.readAsDataURL(file);
    event.target.value = "";   // allow re-selecting same file
}

function instAiClearImage() {
    _aiPendingImg = "";
    const prev = document.getElementById("inst-ai-img-preview");
    if (prev) prev.style.display = "none";
    const thumb = document.getElementById("inst-ai-img-thumb");
    if (thumb) thumb.src = "";
}

function instAiAppendMsg(role, text, imgDataUrl = "") {
    const box = document.getElementById("inst-ai-messages");
    if (!box) return;

    const wrap = document.createElement("div");
    wrap.className = `inst-ai-msg ${role}`;

    const who = document.createElement("span");
    who.className = "inst-ai-who";
    who.textContent = role === "user" ? "You" : "MSK AI";
    wrap.appendChild(who);

    // Show image thumbnail above text if provided
    if (imgDataUrl) {
        const imgEl = document.createElement("img");
        imgEl.src = imgDataUrl;
        imgEl.style.cssText = "max-width:160px;max-height:100px;border-radius:6px;border:1px solid var(--border);object-fit:cover;margin-bottom:4px;";
        wrap.appendChild(imgEl);
    }

    if (text) {
        const bubble = document.createElement("div");
        bubble.className = "inst-ai-bubble";
        bubble.textContent = text;
        wrap.appendChild(bubble);
    }

    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
    return wrap;
}

function instAiShowTyping() {
    const box = document.getElementById("inst-ai-messages");
    if (!box) return null;
    const wrap = document.createElement("div");
    wrap.className = "inst-ai-msg ai";
    wrap.id = "inst-ai-typing";
    wrap.innerHTML = `<span class="inst-ai-who">MSK AI</span><div class="inst-ai-bubble inst-ai-typing"><span></span><span></span><span></span></div>`;
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
    return wrap;
}

async function instAiSend() {
    if (_aiThinking) return;
    const input   = document.getElementById("inst-ai-input");
    const sendBtn = document.getElementById("inst-ai-send-btn");
    if (!input) return;

    const msg = input.value.trim();
    const img = _aiPendingImg;

    if (!msg && !img) return;

    input.value = "";
    input.style.height = "";
    const sentImg = img;
    instAiClearImage();

    _aiThinking = true;
    if (sendBtn) sendBtn.disabled = true;

    // Show user message (with optional image thumbnail)
    instAiAppendMsg("user", msg, sentImg);
    const typingEl = instAiShowTyping();

    try {
        const res = await window.pywebview?.api?.ai_chat?.(msg, _aiHistory, sentImg) ?? {};
        if (typingEl) typingEl.remove();

        if (res.success) {
            instAiAppendMsg("ai", res.reply);
            _aiHistory.push({ role: "user", content: msg || "(image)" });
            _aiHistory.push({ role: "assistant", content: res.reply });
            if (_aiHistory.length > 30) _aiHistory = _aiHistory.slice(-30);
        } else {
            instAiAppendMsg("ai", `Sorry, I couldn't reach the server. ${res.msg || ""}`);
        }
    } catch (e) {
        if (typingEl) typingEl.remove();
        instAiAppendMsg("ai", `Error: ${e}`);
    }

    _aiThinking = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
}
