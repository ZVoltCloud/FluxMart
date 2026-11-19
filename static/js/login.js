function switchLoginTab(tab) {
    document.querySelectorAll('.login-tab-btn').forEach(b => b.classList.remove('active'));
    const loginBtn = document.querySelector('[data-login-tab="login"]');
    const registerBtn = document.querySelector('[data-login-tab="register"]');
    
    document.querySelector('[data-login-tab="' + tab + '"]').classList.add('active');

    const loginContent = document.getElementById('login-tab-content');
    const registerContent = document.getElementById('register-tab-content');

    if (tab === 'login') {
        loginContent.classList.add('active');
        registerContent.classList.remove('active');
        if (loginBtn) loginBtn.style.display = 'block';
        if (registerBtn) registerBtn.style.display = 'block';
    } else if (tab === 'register') {
        loginContent.classList.remove('active');
        registerContent.classList.add('active');
        if (loginBtn) loginBtn.style.display = 'block';
        if (registerBtn) registerBtn.style.display = 'block';
    }
}

function setLoginStatus(msg, type, tab) {
    const suffix = tab === 'register' ? '-register' : '-login';
    const el = document.getElementById('login-status' + suffix);
    if (el) {
        el.innerHTML = msg;
        el.className = 'login-status ' + (type || '');
    }
}

async function waitForApi() {
    for (let i = 0; i < 50; i++) {
        if (window.pywebview && window.pywebview.api) return true;
        await new Promise(r => setTimeout(r, 100));
    }
    return false;
}

async function doLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const remember = document.getElementById('login-remember').checked;

    if (!username || !password) {
        setLoginStatus('Please enter username and password', 'error', 'login');
        return;
    }

    setLoginButtonsDisabled(true);
    setLoginStatus('Authenticating...', '', 'login');

    const apiReady = await waitForApi();
    if (!apiReady) {
        setLoginStatus('Application not ready, please wait...', 'error', 'login');
        setLoginButtonsDisabled(false);
        return;
    }

    try {
        const result = await window.pywebview.api.auth_login(username, password, remember);
        if (result.success) {
            setLoginStatus('Login successful!', 'success', 'login');
            setTimeout(() => {
                proceedToLoading();
            }, 500);
        } else {
            setLoginStatus(result.error || 'Login failed!', 'error', 'login');
            setLoginButtonsDisabled(false);
        }
    } catch (e) {
        setLoginStatus('Error: ' + e.message, 'error', 'login');
        setLoginButtonsDisabled(false);
    }
}

async function doRegister() {
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value.trim();
    const license = document.getElementById('reg-license').value.trim();

    if (!username || !password || !license) {
        setLoginStatus('Please fill all fields', 'error', 'register');
        return;
    }

    setLoginButtonsDisabled(true);
    setLoginStatus('Registering...', '', 'register');

    const apiReady = await waitForApi();
    if (!apiReady) {
        setLoginStatus('Application not ready, please wait...', 'error', 'register');
        setLoginButtonsDisabled(false);
        return;
    }

    try {
        const result = await window.pywebview.api.auth_register(username, password, license);
        if (result.success) {
            // 1. Switch to login tab
            switchLoginTab('login');
            
            // 2. Populate login fields with new credentials
            document.getElementById('login-username').value = username;
            document.getElementById('login-password').value = password;
            
            // 3. Clear any existing error messages in login tab
            setLoginStatus('Registration successful! Please login.', 'success', 'login');
            
            // 4. Clear registration status and fields
            setLoginStatus('', '', 'register');
            setLoginButtonsDisabled(false);
            document.getElementById('reg-username').value = '';
            document.getElementById('reg-password').value = '';
            document.getElementById('reg-license').value = '';
            
            // Trigger eye icon visibility update for login password
            const loginPasswordInput = document.getElementById('login-password');
            const loginPasswordToggle = document.getElementById('login-password-toggle');
            if (loginPasswordInput && loginPasswordToggle) {
                if (loginPasswordInput.value.length > 0) {
                    loginPasswordToggle.classList.add('visible');
                }
            }
        } else {
            setLoginStatus(result.error || 'Registration failed!', 'error', 'register');
            setLoginButtonsDisabled(false);
        }
    } catch (e) {
        setLoginStatus('Error: ' + e.message, 'error', 'register');
        setLoginButtonsDisabled(false);
    }
}

function setLoginButtonsDisabled(disabled) {
    document.querySelectorAll('.login-btn').forEach(btn => {
        btn.disabled = disabled;
    });
    document.querySelectorAll('.login-tab-btn').forEach(btn => {
        btn.disabled = disabled;
        btn.style.opacity = disabled ? '0.5' : '1';
        btn.style.pointerEvents = disabled ? 'none' : 'auto';
    });
}

async function checkAutoLogin() {
    const loginOverlay = document.getElementById('login-overlay');
    if (!loginOverlay) return;

    const savedUsername = loginOverlay.getAttribute('data-saved-username');
    const autoLoginEnabled = loginOverlay.getAttribute('data-auto-login-enabled') === 'true';
    
    if (autoLoginEnabled && savedUsername) {
        const apiReady = await waitForApi();
        if (!apiReady) return;

        try {
            setLoginButtonsDisabled(true);
            setLoginStatus('Auto login authenticating...', '', 'login');
            const result = await window.pywebview.api.try_auto_login();
            if (result.success) {
                setLoginStatus('Auto login successful!', 'success', 'login');
                setTimeout(() => {
                    proceedToLoading();
                }, 300);
            } else {
                setLoginButtonsDisabled(false);
                setLoginStatus('Auto login failed, please login manually', 'error', 'login');
            }
        } catch (e) {
            setLoginButtonsDisabled(false);
        }
    }
}

async function initialStartupLoading() {
    const progressBar = document.getElementById("loading-progress");
    const progressText = document.getElementById("loading-status");
    const loadingOverlay = document.getElementById("loading-overlay");
    const loginOverlay = document.getElementById("login-overlay");
    const loginContent = document.querySelector('.login-content');

    if (!progressBar || !progressText || !loadingOverlay) return;

    // Show loading overlay at startup with entrance animation
    loadingOverlay.style.display = 'flex';
    progressBar.style.width = "0%";
    progressText.textContent = "Starting...";

    document.documentElement.classList.add('animating');
    document.body.classList.add('animating');
    
    // Force reflow and add entrance animation
    void loadingOverlay.offsetWidth;
    loadingOverlay.classList.add('animate-enter');

    // Give the entrance animation a moment before starting the progress
    await new Promise(r => setTimeout(r, 200));

    const steps = [
        { progress: 10, message: "Initializing..." },
        { progress: 30, message: "Connecting to our servers..." },
        { progress: 55, message: "Authenticating..." },
        { progress: 80, message: "Securing connection..." },
        { progress: 100, message: "Connected!" }
    ];

    for (const step of steps) {
        progressBar.style.width = step.progress + "%";
        progressText.textContent = step.message;
        const percentEl = document.getElementById("loading-percent");
        if (percentEl) percentEl.textContent = Math.round(step.progress) + "%";
        if (step.progress < 100) {
            await new Promise(r => setTimeout(r, 200 + Math.random() * 200));
        }
    }

    // Wait for the 400ms CSS transition of the progress bar to finish its 100% reach
    await new Promise(r => setTimeout(r, 450));

    // Transition to Login
    loadingOverlay.classList.add("animate-exit");
    
    setTimeout(() => {
        loadingOverlay.style.display = "none";
        loadingOverlay.classList.remove("animate-exit");
        loadingOverlay.classList.remove("animate-enter"); // Clean up enter class
        
        if (loginOverlay) {
            loginOverlay.style.display = 'flex';
            // Force reflow
            void loginOverlay.offsetWidth;
            loginOverlay.classList.add('animate-enter');
            if (loginContent) loginContent.classList.add('animate-enter');
            
            setTimeout(() => {
                document.documentElement.classList.remove('animating');
                document.body.classList.remove('animating');
                
                // ONLY NOW check for auto-login after everything is visible
                checkAutoLogin();
            }, 300);
        }
    }, 300);
}

function proceedToLoading() {
    const loginOverlay = document.getElementById('login-overlay');
    const loadingOverlay = document.getElementById('loading-overlay');

    if (loginOverlay && loginOverlay.style.display !== 'none') {
        loginOverlay.classList.add('animate-exit');
        setTimeout(() => {
            loginOverlay.style.display = 'none';
            loginOverlay.classList.remove('animate-exit');
            loginOverlay.classList.remove('animate-enter');
            loadingOverlay.style.display = 'flex';
            void loadingOverlay.offsetWidth;
            loadingOverlay.classList.add('animate-enter');
            startLoading();
        }, 400);
    } else {
        loadingOverlay.style.display = 'flex';
        void loadingOverlay.offsetWidth;
        loadingOverlay.classList.add('animate-enter');
        startLoading();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Start initial loading sequence instead of showing login immediately
    initialStartupLoading();

    const loginPassword = document.getElementById('login-password');
    if (loginPassword) {
        loginPassword.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') doLogin();
        });
    }

    const regPassword = document.getElementById('reg-password');
    if (regPassword) {
        regPassword.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') doRegister();
        });
    }

    const regLicense = document.getElementById('reg-license');
    if (regLicense) {
        regLicense.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') doRegister();
        });
    }

    const loginPasswordInput = document.getElementById('login-password');
    const loginPasswordToggle = document.getElementById('login-password-toggle');
    const regPasswordInput = document.getElementById('reg-password');
    const regPasswordToggle = document.getElementById('reg-password-toggle');

    function setupPasswordToggle(input, toggle) {
        if (!input || !toggle) return;
        
        const wrapper = input.parentElement;
        if (!wrapper) return;

        function updateToggleVisibility() {
            if (input.value.length > 0) {
                toggle.classList.add('visible');
            } else {
                toggle.classList.remove('visible');
            }
        }

        wrapper.addEventListener('focusin', updateToggleVisibility);

        input.addEventListener('input', updateToggleVisibility);

        updateToggleVisibility();

        toggle.addEventListener('mousedown', (e) => {
            // e.preventDefault(); // Remove preventDefault to avoid cursor bugs in some webview versions
            e.stopPropagation(); // Prevents pywebview from dragging
            const eyeOpen = toggle.querySelector('.eye-open');
            const eyeClosed = toggle.querySelector('.eye-closed');

            if (input.type === 'password') {
                input.type = 'text';
                eyeOpen.style.display = 'block';
                eyeClosed.style.display = 'none';
            } else {
                input.type = 'password';
                eyeOpen.style.display = 'none';
                eyeClosed.style.display = 'block';
            }
        });

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    setupPasswordToggle(loginPasswordInput, loginPasswordToggle);
    setupPasswordToggle(regPasswordInput, regPasswordToggle);
});