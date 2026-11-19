/* ═══════════════════ SIDEBAR NAVIGATION + KEYBOARD SHORTCUTS ═══════════════════ */

(function() {
    'use strict';

    // Map data-tab → readable display name for the header label
    var TAB_LABELS = {
        'generator':       'Generator',
        'token-things':    'Tokens Things',
        'humanizer':       'Token Manager',
        'phone-verify':    'Phone Verify',
        'terminal':        'Terminal',
        'settings':        'Settings',
        'version-history': 'Version History',
        'account':         'Account',
        'installer':       'Installer'
    };

    var sidebar = null;
    var navItems = [];
    var tabContents = [];

    function updateHeaderLabel(tabId) {
        var label = document.getElementById('header-tab-label');
        if (label) {
            label.textContent = TAB_LABELS[tabId] || tabId;
        }
    }

    function init() {
        sidebar = document.getElementById('app-sidebar');
        if (!sidebar) return;

        navItems = Array.prototype.slice.call(sidebar.querySelectorAll('.nav-item[data-tab]'));
        tabContents = Array.prototype.slice.call(document.querySelectorAll('.tab-content'));

        // Nav click handlers
        navItems.forEach(function(item) {
            item.addEventListener('click', function() {
                switchTab(item.getAttribute('data-tab'));
            });
        });

        // Collapse toggle
        var toggleBtn = document.getElementById('sidebar-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function() {
                sidebar.classList.toggle('collapsed');
                // Update status bar position
                document.body.classList.toggle('sidebar-collapsed', sidebar.classList.contains('collapsed'));
                // Save preference
                try { localStorage.setItem('msk_sidebar_collapsed', sidebar.classList.contains('collapsed')); } catch(e) {}
            });
        }

        // Restore collapsed state
        try {
            if (localStorage.getItem('msk_sidebar_collapsed') === 'true') {
                sidebar.classList.add('collapsed');
                document.body.classList.add('sidebar-collapsed');
            }
        } catch(e) {}

        // Set initial header label to whichever tab is active
        var activeNav = sidebar.querySelector('.nav-item.active');
        if (activeNav) {
            updateHeaderLabel(activeNav.getAttribute('data-tab'));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            // Don't trigger when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

            // Ctrl+1 through Ctrl+7 for tabs
            if (e.ctrlKey && !e.shiftKey && !e.altKey) {
                var num = parseInt(e.key);
                if (num >= 1 && num <= navItems.length) {
                    e.preventDefault();
                    var targetTab = navItems[num - 1].getAttribute('data-tab');
                    switchTab(targetTab);
                }
            }

            // Ctrl+G to start generation
            if (e.ctrlKey && e.key.toLowerCase() === 'g' && !e.shiftKey) {
                e.preventDefault();
                var startBtn = document.getElementById('gen-start-btn');
                if (startBtn && !startBtn.disabled) {
                    startBtn.click();
                }
            }

            // Ctrl+B to toggle sidebar
            if (e.ctrlKey && e.key.toLowerCase() === 'b' && !e.shiftKey) {
                e.preventDefault();
                if (toggleBtn) toggleBtn.click();
            }
        });
    }

    function switchTab(tabId) {
        // Update nav items
        navItems.forEach(function(item) {
            if (item.getAttribute('data-tab') === tabId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // Update tab contents
        tabContents.forEach(function(content) {
            content.classList.remove('active');
        });

        var tabEl = document.getElementById(tabId + '-tab');
        if (tabEl) tabEl.classList.add('active');

        // Update header breadcrumb label
        updateHeaderLabel(tabId);

        // Special init hooks
        if (tabId === 'humanizer' && typeof tmInit === 'function') {
            tmInit();
        }
        if (tabId === 'account' && typeof refreshAccountInfo === 'function') {
            refreshAccountInfo(false);
        }
        if (tabId === 'installer' && typeof instRefresh === 'function') {
            instRefresh();
        }
    }

    // Expose
    window.mskSwitchTab = switchTab;

    // Init on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
