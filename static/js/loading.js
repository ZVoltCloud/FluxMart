function _updateLoadingProgress(progress, message) {
    const progressBar = document.getElementById("loading-progress");
    const progressText = document.getElementById("loading-status");
    const percentText = document.getElementById("loading-percent");
    if (progressBar) progressBar.style.width = progress + "%";
    if (progressText) progressText.textContent = message;
    if (percentText) percentText.textContent = Math.round(progress) + "%";
}

async function startLoading() {
    const progressBar = document.getElementById("loading-progress");
    const progressText = document.getElementById("loading-status");
    const percentText = document.getElementById("loading-percent");
    const overlay = document.getElementById("loading-overlay");
    const mainContainer = document.getElementById("main-container");

    if (!progressBar || !progressText || !overlay || !mainContainer) return;

    // Reset progress bar instantly (no animation) so it doesn't slide backward from 100%
    progressBar.style.transition = 'none';
    progressBar.style.width = '0%';
    if (progressText) progressText.textContent = 'Starting...';
    if (percentText) percentText.textContent = '0%';
    void progressBar.offsetWidth; // force reflow before restoring transition
    progressBar.style.transition = '';

    await new Promise(r => setTimeout(r, 200));

    const steps = [
        { progress: 10, message: "Initializing..." },
        { progress: 25, message: "Loading settings..." },
        { progress: 45, message: "Applying language..." },
        { progress: 65, message: "Loading modules..." },
        { progress: 80, message: "Loading account data..." },
        { progress: 92, message: "Almost ready..." },
        { progress: 100, message: "Ready!" },
    ];

    // Step 1: Initializing
    _updateLoadingProgress(steps[0].progress, steps[0].message);
    await new Promise(r => setTimeout(r, 200));

    // Step 2: Load settings
    _updateLoadingProgress(steps[1].progress, steps[1].message);
    try {
        if (window.pywebview && window.pywebview.api) {
            await loadSettingsFromBackend();
        }
    } catch (e) {
        console.error("Loading settings error:", e);
    }
    await new Promise(r => setTimeout(r, 200));

    // Step 3: Apply language
    const lang = (window.mskSettings && mskSettings.language) ? mskSettings.language : 'en';
    if (lang !== 'en') {
        _updateLoadingProgress(steps[2].progress, "Applying language...");
        try {
            await applyLanguage(lang, false, false);
        } catch (e) {
            console.error("Language error:", e);
        }
    } else {
        _updateLoadingProgress(steps[2].progress, steps[2].message);
    }
    await new Promise(r => setTimeout(r, 250));

    // Step 4: Load modules & Discord user
    _updateLoadingProgress(steps[3].progress, steps[3].message);
    try {
        if (window.pywebview && window.pywebview.api) {
            const discordUser = await window.pywebview.api.discord_get_cached_user();
            if (discordUser && discordUser.success && discordUser.user) {
                const u = discordUser.user;
                const displayName = u.username || u.global_name || '';
                if (u.avatar_url && displayName) {
                    const group = document.getElementById('header-discord-group');
                    const img = document.getElementById('header-avatar-img');
                    const nameEl = document.getElementById('header-username');
                    if (img) img.src = u.avatar_url;
                    if (nameEl) nameEl.textContent = displayName;
                    if (group) group.style.display = 'flex';
                }
            }
        }
    } catch (e) { /* silent */ }
    await new Promise(r => setTimeout(r, 200));

    // Step 5: Load account data and avatars
    _updateLoadingProgress(steps[4].progress, steps[4].message);
    try {
        if (window.pywebview && window.pywebview.api) {
            await Promise.all([
                loadAvatarsFromBackend().catch(() => {}),
                refreshAccountInfo(false).catch(() => {})
            ]);
        }
    } catch (e) { /* silent */ }
    await new Promise(r => setTimeout(r, 200));

    // Step 6: Almost ready
    _updateLoadingProgress(steps[5].progress, steps[5].message);
    await new Promise(r => setTimeout(r, 150));

    // Step 7: Done
    _updateLoadingProgress(steps[6].progress, steps[6].message);
    await new Promise(r => setTimeout(r, 450));

    // Show the main container invisibly BEFORE the overlay fades out so there
    // is never a black-screen gap between the two transitions.
    mainContainer.style.display = "flex";
    mainContainer.style.opacity = "0";
    void mainContainer.offsetWidth; // force reflow

    overlay.classList.add("animate-exit");
    setTimeout(() => {
        overlay.style.display = "none";
        overlay.classList.remove("animate-exit", "animate-enter");

        // Fade main container in (animate-enter takes it from opacity 0 → 1)
        mainContainer.style.opacity = "";
        void mainContainer.offsetWidth;
        mainContainer.classList.add("animate-enter");
        setTimeout(() => mainContainer.classList.remove("animate-enter"), 500);
    }, 300);

    // Re-translate existing log entries if non-English
    if (lang !== 'en' && window.translateString) {
        const existingEntries = document.querySelectorAll('.log-entry .log-message');
        for (const msgEl of existingEntries) {
            const rawText = msgEl.textContent;
            if (rawText) {
                try {
                    const isMsk = rawText.startsWith("[Msk] ");
                    const textToTranslate = isMsk ? rawText.substring(6) : rawText;
                    const translated = await translateString(textToTranslate, lang);
                    if (translated && translated !== textToTranslate) {
                        const finalTranslated = isMsk ? "[Msk] " + translated : translated;
                        if (typeof window.addLog === 'function') {
                            const primary = "#dddddd";
                            const dim = "#808080";
                            let formatted = finalTranslated;
                            if (isMsk) {
                                const mskStyled = `<span style="color:${primary} !important;">[</span><span style="color:${dim} !important;">Msk</span><span style="color:${primary} !important;">]</span> `;
                                formatted = mskStyled + finalTranslated.substring(6);
                            }
                            msgEl.innerHTML = formatted;
                        } else {
                            msgEl.textContent = finalTranslated;
                        }
                    }
                } catch (e) { /* silent */ }
            }
        }
    }

    try { addLog("[Msk] FluxMart initialized"); } catch(e) {}
}

window.startLoading = startLoading;
