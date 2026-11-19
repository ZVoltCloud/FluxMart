/* ═══════════════════ TOAST NOTIFICATION SYSTEM ═══════════════════ */

(function() {
    'use strict';

    // SVG icons for toast types (no emojis)
    const ICONS = {
        success: '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>',
        error: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    let container = null;
    const cleanupTimers = new WeakMap();

    function ensureContainer() {
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            container.id = 'toast-container';
            container.setAttribute('role', 'region');
            container.setAttribute('aria-label', 'Notifications');
            document.body.appendChild(container);
        }
        return container;
    }

    /**
     * Show a toast notification.
     * @param {string} title - Bold title text
     * @param {string} message - Body message
     * @param {'success'|'error'|'warning'|'info'} type - Toast variant
     * @param {number} duration - Auto-dismiss in ms (default 5000, 0 = manual)
     */
    function showToast(title, message, type, duration) {
        type = Object.prototype.hasOwnProperty.call(ICONS, type) ? type : 'info';
        duration = Number.isFinite(duration) && duration >= 0 ? duration : 5000;
        var c = ensureContainer();

        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
        toast.setAttribute('aria-atomic', 'true');

        var icon = ICONS[type] || ICONS.info;

        toast.innerHTML =
            '<div class="toast-icon" aria-hidden="true">' + icon + '</div>' +
            '<div class="toast-body">' +
                '<div class="toast-title">' + escapeHtml(title) + '</div>' +
                (message ? '<div class="toast-message">' + escapeHtml(message) + '</div>' : '') +
            '</div>' +
            '<button type="button" class="toast-close" aria-label="Dismiss notification" title="Dismiss">' +
                '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>' +
            '</button>';

        // Add progress bar if auto-dismiss
        if (duration > 0) {
            var progress = document.createElement('div');
            progress.className = 'toast-progress';
            progress.style.animationDuration = duration + 'ms';
            progress.setAttribute('aria-hidden', 'true');
            toast.appendChild(progress);
        }

        toast.querySelector('.toast-close').addEventListener('click', function() { removeToast(toast); });
        toast.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') removeToast(toast);
        });
        toast.addEventListener('mousedown', function(event) { event.stopPropagation(); });

        c.appendChild(toast);

        // Keep a short stack; overflow remains scrollable on smaller windows.
        var toasts = c.querySelectorAll('.toast:not(.removing)');
        if (toasts.length > 4) {
            removeToast(toasts[0]);
        }

        // Auto-dismiss
        if (duration > 0) {
            let remaining = duration;
            let started;
            let timer;
            const pauseReasons = new Set();
            const resume = function(reason) {
                pauseReasons.delete(reason);
                if (pauseReasons.size || toast.classList.contains('removing')) return;
                toast.classList.remove('paused');
                started = performance.now();
                timer = setTimeout(function() { removeToast(toast); }, remaining);
            };
            const pause = function(reason) {
                if (!pauseReasons.size) {
                    clearTimeout(timer);
                    remaining = Math.max(0, remaining - (performance.now() - started));
                    toast.classList.add('paused');
                }
                pauseReasons.add(reason);
            };
            toast.addEventListener('mouseenter', function() { pause('hover'); });
            toast.addEventListener('mouseleave', function() { resume('hover'); });
            toast.addEventListener('focusin', function() { pause('focus'); });
            toast.addEventListener('focusout', function(event) {
                if (!toast.contains(event.relatedTarget)) resume('focus');
            });
            cleanupTimers.set(toast, function() { clearTimeout(timer); });
            resume('initial');
        }

        c.scrollTop = c.scrollHeight;

        return toast;
    }

    function removeToast(toast) {
        if (!toast || toast.classList.contains('removing')) return;
        const cleanup = cleanupTimers.get(toast);
        if (cleanup) cleanup();
        cleanupTimers.delete(toast);
        toast.classList.add('removing');
        if (toast.contains(document.activeElement)) {
            const next = toast.nextElementSibling || toast.previousElementSibling;
            if (next) next.querySelector('.toast-close')?.focus();
        }
        setTimeout(function() {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 180);
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Expose globally
    window.mskToast = showToast;
    window.mskToastSuccess = function(title, msg, dur) { return showToast(title, msg, 'success', dur); };
    window.mskToastError = function(title, msg, dur) { return showToast(title, msg, 'error', dur); };
    window.mskToastWarning = function(title, msg, dur) { return showToast(title, msg, 'warning', dur); };
    window.mskToastInfo = function(title, msg, dur) { return showToast(title, msg, 'info', dur); };

    // Compatibility shim for existing window.toast.success() / .error() calls
    window.toast = {
        success: function(title, msg, dur) { return showToast(title, msg, 'success', dur); },
        error: function(title, msg, dur) { return showToast(title, msg, 'error', dur); },
        warning: function(title, msg, dur) { return showToast(title, msg, 'warning', dur); },
        info: function(title, msg, dur) { return showToast(title, msg, 'info', dur); }
    };

})();
