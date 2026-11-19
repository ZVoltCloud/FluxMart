async function addLog(message, type) {
    type = type || "info";
    const logContainer = document.getElementById("log-container");
    if (!logContainer) return;

    // Filter noisy internal status messages from the visible log panel
    const _stripped = message.replace(/\x1b\[[0-9;]*m/g, '').trim();
    if (_stripped.includes('Checking token status')) return;


    const now = new Date();
    const timeString = now.toTimeString().split(" ")[0];

    const ansiRegex = /\x1b\[([0-9;]+)m/g;
    const ansiToHtml = (msg) => {
        let openTags = [];
        return msg.replace(ansiRegex, (match, codes) => {
            const parts = codes.split(";");
            const first = parseInt(parts[0]);
            if (first === 0) {
                const closeTags = openTags.reverse().join("");
                openTags = [];
                return closeTags;
            }
            if (first === 38 && parts[1] === "2") {
                const [r, g, b] = parts.slice(2).map(Number);
                openTags.push("</span>");
                return '<span style="color:rgb(' + r + ',' + g + ',' + b + ')">';
            }
            const basicMap = {
                30: "black", 31: "red", 32: "green", 33: "yellow",
                34: "blue", 35: "magenta", 36: "cyan", 37: "white"
            };
            if (basicMap[first]) {
                openTags.push("</span>");
                return '<span style="color:' + basicMap[first] + '">';
            }
            return "";
        }) + openTags.reverse().join("");
    };

    const formatMskMessage = (msg) => {
        let formatted = ansiToHtml(msg);
        if (msg.startsWith("[Msk] ")) {
            const primary = "#dddddd";
            const dim = "#808080";
            const mskStyled = `<span style="color:${primary} !important;">[</span><span style="color:${dim} !important;">Msk</span><span style="color:${primary} !important;">]</span> `;
            formatted = mskStyled + ansiToHtml(msg.substring(6));
        }
        return formatted;
    };

    let formattedMessage = formatMskMessage(message);

    const logEntry = document.createElement("div");
    const typeClass = type === "error" ? "log-error" : type === "success" ? "log-success" : type === "warning" ? "log-warning" : "";
    logEntry.className = "log-entry " + typeClass;

    // Initial content (English/Raw)
    logEntry.innerHTML = '<span class="log-time">' + timeString + '</span><span class="log-message">' + formattedMessage + '</span>';
    // Use encodeURIComponent to safely store ANSI escape characters
    logEntry.setAttribute('data-raw-message', encodeURIComponent(message));
    logContainer.appendChild(logEntry);
    
    // Cap logs to prevent memory leaks and UI slowdown
    while (logContainer.children.length > 500) {
        logContainer.removeChild(logContainer.firstChild);
    }
    
    logContainer.scrollTop = logContainer.scrollHeight;

    // Async translate if needed
    if (window.mskSettings && window.mskSettings.language && window.mskSettings.language !== 'en' && window.translateString) {
        window.translateString(message, window.mskSettings.language).then(translated => {
            if (translated && translated !== message) {
                logEntry.querySelector('.log-message').innerHTML = formatMskMessage(translated);
            }
        }).catch(() => { });
    }
    return; // Don't need to return anything else
}

window.retranslateLogs = async function (langCode) {
    if (!window.translateString) return;
    const logContainer = document.getElementById("log-container");
    if (!logContainer) return;

    const entries = logContainer.querySelectorAll('.log-entry');
    for (const entry of entries) {
        const rawMessageEnc = entry.getAttribute('data-raw-message');
        if (rawMessageEnc) {
            let rawMessage = "";
            try {
                rawMessage = decodeURIComponent(rawMessageEnc);
            } catch (e) {
                rawMessage = rawMessageEnc;
            }

            // Re-apply formatting first in case we switch back to English
            // let formattedMessage = entry.querySelector('.log-message').innerHTML; // fallback - no longer needed here

            const ansiRegex = /\x1b\[([0-9;]+)m/g;
            const formatMskMessage = (msg) => {
                const ansiToHtml = (m) => {
                    let openTags = [];
                    return m.replace(ansiRegex, (match, codes) => {
                        const parts = codes.split(";");
                        const first = parseInt(parts[0]);
                        if (first === 0) return openTags.reverse().join("");
                        if (first === 38 && parts[1] === "2") {
                            const [r, g, b] = parts.slice(2).map(Number);
                            openTags.push("</span>");
                            return `<span style="color:rgb(${r},${g},${b})">`;
                        }
                        const basicMap = { 30: "black", 31: "red", 32: "green", 33: "yellow", 34: "blue", 35: "magenta", 36: "cyan", 37: "white" };
                        if (basicMap[first]) {
                            openTags.push("</span>");
                            return `<span style="color:${basicMap[first]}">`;
                        }
                        return "";
                    }) + openTags.reverse().join("");
                };
                let formatted = ansiToHtml(msg);
                if (msg.startsWith("[Msk] ")) {
                    const primary = "#dddddd";
                    const dim = "#808080";
                    formatted = `<span style="color:${primary} !important;">[</span><span style="color:${dim} !important;">Msk</span><span style="color:${primary} !important;">]</span> ` + ansiToHtml(msg.substring(6));
                }
                return formatted;
            };

            if (langCode === 'en') {
                entry.querySelector('.log-message').innerHTML = formatMskMessage(rawMessage);
            } else {
                window.translateString(rawMessage, langCode).then(translated => {
                    if (translated) {
                        entry.querySelector('.log-message').innerHTML = formatMskMessage(translated);
                    }
                }).catch(() => { });
            }
        }
    }
};

function clearLogs() {
    const logContainer = document.getElementById('log-container');
    if (logContainer) {
        logContainer.innerHTML = '';
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.clear_logs();
        }
        addLog("[Msk] Log cleared");
    }
}


window.addLog = addLog;

