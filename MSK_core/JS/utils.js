(() => {

    class DOMHelper {
        static query(selector, all = false) {
            return all ? [...document.querySelectorAll(selector)] : document.querySelector(selector);
        }

        static trigger(el, events = []) {
            if (!el) return;
            for (const evt of events) {
                el.dispatchEvent(new Event(evt, { bubbles: true }));
            }
        }

        static waitForElement(selector, interval = 20, timeout = 15000) {
            return new Promise((resolve) => {
                const start = Date.now();
                const timer = setInterval(() => {
                    const el = DOMHelper.query(selector);
                    if (el) {
                        clearInterval(timer);
                        resolve(el);
                    } else if (Date.now() - start > timeout) {
                        clearInterval(timer);
                        resolve(null);
                    }
                }, interval);
            });
        }

        static waitForCondition(fn, interval = 20, timeout = 15000) {
            return new Promise((resolve) => {
                const start = Date.now();
                const check = () => {
                    const result = fn();
                    if (result) {
                        resolve(result);
                    } else if (Date.now() - start > timeout) {
                        resolve(null);
                    } else {
                        setTimeout(check, interval);
                    }
                };
                check();
            });
        }
    }

    function setInput(selector, value) {
        const el = DOMHelper.query(selector);
        if (el) {
            el.value = value;
            DOMHelper.trigger(el, ['input', 'change']);
        }
    }

    function clickCheckbox(selector) {
        const el = DOMHelper.query(selector);
        if (el && el.getAttribute('aria-checked') === 'false') el.click();
    }

    function clickElement(selector) {
        const el = DOMHelper.query(selector);
        if (el) el.click();
    }

    function fireMouseEvents(el) {
        ['mousedown', 'mouseup', 'click'].forEach(type => {
            el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
        });
    }

    // Language variant tables for discord's birthday dropdowns
    const LABEL_TRANSLATIONS = {
        'Month': ['month', 'mois', 'mes', 'monat', 'mese', 'mês', 'måned', 'maand', 'kuukausi', 'měsíc', 'miesiąc', 'hónap', 'lună', 'месяц', '月'],
        'Day':   ['day',   'jour', 'día', 'tag',   'giorno', 'dia', 'dag', 'dag', 'päivä', 'den',  'dzień',  'nap',   'zi',   'день',   '日'],
        'Year':  ['year',  'année','año', 'jahr',  'anno',   'ano', 'år',  'jaar','vuosi', 'rok',  'rok',    'év',    'an',   'год',    '年'],
    };
    const DROPDOWN_ORDER = ['Month', 'Day', 'Year'];

    function _findBirthdayDropdowns() {
        // Discord birthday dropdowns: div[role="button"] elements that have an SVG arrow/caret
        // and are siblings of each other inside the date-of-birth section.
        const candidates = DOMHelper.query('[role="button"]', true).filter(btn => {
            return btn.querySelector('svg') !== null;
        });

        // If there are exactly 3 in the whole page, those are our dropdowns
        if (candidates.length === 3) return candidates;

        // Try to find a container that holds exactly 3 such buttons
        for (const btn of candidates) {
            const parent = btn.parentElement;
            if (!parent) continue;
            const siblings = [...parent.children].filter(c =>
                c.getAttribute && c.getAttribute('role') === 'button' && c.querySelector('svg')
            );
            if (siblings.length === 3) return siblings;
            // Check grandparent
            const gp = parent.parentElement;
            if (!gp) continue;
            const gpChildren = [...gp.querySelectorAll('[role="button"]')].filter(c => c.querySelector('svg'));
            if (gpChildren.length === 3) return gpChildren;
        }

        // Fallback: any [role="button"] with svg, take first 3
        return candidates.slice(0, 3);
    }

    async function setDropdown(label, value) {
        const variants = LABEL_TRANSLATIONS[label] || [label.toLowerCase()];
        const idx = DROPDOWN_ORDER.indexOf(label);

        let dropdown = null;

        // Method 1: find by aria-label containing a language variant
        const allBtns = DOMHelper.query('[role="button"]', true);
        for (const btn of allBtns) {
            const al = (btn.getAttribute('aria-label') || '').toLowerCase();
            const txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
            if (variants.some(v => al.includes(v) || txt === v)) {
                dropdown = btn;
                break;
            }
        }

        // Method 2: find by DOM position among birthday dropdowns
        if (!dropdown && idx >= 0) {
            const drops = _findBirthdayDropdowns();
            if (drops.length > idx) dropdown = drops[idx];
        }

        if (!dropdown) return false;

        fireMouseEvents(dropdown);

        // Wait for listbox to open
        const listbox = await DOMHelper.waitForCondition(
            () => DOMHelper.query('[role="listbox"]'),
            30, 8000
        );
        if (!listbox) return false;

        // Wait for at least one option to appear
        const firstOpts = await DOMHelper.waitForCondition(() => {
            const opts = DOMHelper.query('[role="option"]', true);
            return opts.length > 0 ? opts : null;
        }, 30, 8000);
        if (!firstOpts) return false;

        // IDX:N  → select by 1-based index (for month in any language)
        if (typeof value === 'string' && value.startsWith('IDX:')) {
            const targetIdx = parseInt(value.slice(4), 10) - 1;
            const opts = DOMHelper.query('[role="option"]', true);
            const target = opts[targetIdx] || null;
            if (target) {
                target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                await new Promise(r => setTimeout(r, 60));
                fireMouseEvents(target);
                return true;
            }
            return false;
        }

        // Text-based selection with scroll (for Day / Year — numeric, language-agnostic)
        const strVal = String(value);
        let match = firstOpts.find(opt => opt.textContent.trim() === strVal);
        if (match) {
            match.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            await new Promise(r => setTimeout(r, 60));
            fireMouseEvents(match);
            return true;
        }

        // Scroll through the list to find the target text
        let container = null;
        let el = firstOpts[0];
        while (el && el !== document.body) {
            const style = window.getComputedStyle(el);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll' ||
                style.overflow === 'auto' || style.overflow === 'scroll') {
                container = el;
                break;
            }
            el = el.parentElement;
        }

        if (container) {
            for (let i = 0; i < 120; i++) {
                const opts = DOMHelper.query('[role="option"]', true);
                match = opts.find(opt => opt.textContent.trim() === strVal);
                if (match) break;
                container.scrollTop += 200;
                await new Promise(r => setTimeout(r, 40));
            }
        }

        if (!match) return false;
        match.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        await new Promise(r => setTimeout(r, 60));
        fireMouseEvents(match);
        return true;
    }

    function clickAllCheckboxes() {
        // Standard HTML checkboxes
        DOMHelper.query('input[type="checkbox"]', true)
            .filter(cb => !cb.checked)
            .forEach(cb => {
                try { cb.click(); } catch(e) {}
            });

        // React / Discord custom checkboxes via role="checkbox"
        DOMHelper.query('[role="checkbox"]', true)
            .filter(cb => cb.getAttribute('aria-checked') !== 'true')
            .forEach(cb => {
                try { fireMouseEvents(cb); } catch(e) {}
            });

        // Discord wraps checkboxes in a label — click the label itself if unchecked
        DOMHelper.query('label', true).forEach(lbl => {
            const inp = lbl.querySelector('input[type="checkbox"]');
            if (inp && !inp.checked) {
                try { lbl.click(); } catch(e) {}
            }
        });
    }

    function isImageCaptcha() {
        const taskGrid = DOMHelper.query('.task-grid, .task-image, .challenge-container');
        if (taskGrid) return true;
        const promptText = DOMHelper.query('h2.prompt-text');
        if (promptText) {
            const text = promptText.innerText.toLowerCase();
            if (text.includes('select') || text.includes('click each') || text.includes('pattern')) {
                return true;
            }
        }
        const images = DOMHelper.query('.task-image img, .challenge-image', true);
        if (images && images.length > 2) return true;
        return false;
    }

    async function openAccessibilityChallenge() {
        const menuBtn = await DOMHelper.waitForElement('#menu-info', 20, 10000);
        if (!menuBtn) {
            return { success: false, reason: 'no_menu' };
        }
        menuBtn.click();

        const accBtn = await DOMHelper.waitForCondition(() => {
            const opts = DOMHelper.query('[role="menuitem"]', true);
            return opts.find(o =>
                /Display hCaptcha/i.test(o.innerText) ||
                /Accessibility Challenge/i.test(o.innerText)
            );
        }, 20, 10000);
        if (!accBtn) {
            return { success: false, reason: 'no_accessibility_option' };
        }
        accBtn.click();

        const captchaInput = await DOMHelper.waitForElement('input[name="captcha"]', 20, 10000);
        if (!captchaInput) {
            return { success: false, reason: 'no_captcha_input' };
        }

        return { success: true };
    }

    function answerAccessibilityQuestion(answer) {
        const input = DOMHelper.query('input[name="captcha"]');
        if (!input) return;

        input.focus();

        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(input, answer);

        input.dispatchEvent(new InputEvent('input', {
            bubbles: true,
            data: answer,
            inputType: 'insertText'
        }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.dispatchEvent(new Event('blur', { bubbles: true }));

        const submitButton = DOMHelper.query('.button-submit');
        if (submitButton) submitButton.click();
    }

    async function waitForDiscordToken(timeout = 8000) {
        function _readToken() {
            try {
                const raw = localStorage.getItem('token');
                if (raw) {
                    const t = raw.replace(/^"|"$/g, '').trim();
                    if (t.length > 50 && t.indexOf('.') > -1) return t;
                }
            } catch(e) {}

            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    let v = localStorage.getItem(k) || '';
                    v = v.replace(/^"|"$/g, '').trim();
                    if (v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1 && v.indexOf('<') === -1) {
                        return v;
                    }
                }
            } catch(e) {}

            try {
                function walkFiber(fiber, depth) {
                    if (!fiber || depth > 150) return null;
                    try {
                        let m = fiber.memoizedState;
                        while (m) {
                            const s = m.memoizedState;
                            if (typeof s === 'string' && s.length > 50 && s.indexOf('.') > -1 && s.indexOf('{') === -1) return s;
                            if (s && typeof s === 'object') {
                                const vals = Object.values(s);
                                for (const v of vals) {
                                    if (typeof v === 'string' && v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1) return v;
                                }
                            }
                            m = m.next;
                        }
                    } catch(e) {}
                    const r1 = fiber.child ? walkFiber(fiber.child, depth + 1) : null;
                    if (r1) return r1;
                    return fiber.sibling ? walkFiber(fiber.sibling, depth + 1) : null;
                }
                const root = document.getElementById('app-mount') || document.querySelector('[class^="app-"]');
                if (root) {
                    const fiberKey = Object.keys(root).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
                    if (fiberKey) {
                        const t = walkFiber(root[fiberKey], 0);
                        if (t) return t;
                    }
                }
            } catch(e) {}

            return null;
        }

        const existing = _readToken();
        if (existing) return existing;

        return new Promise((resolve) => {
            let resolved = false;

            function finish(token) {
                if (resolved) return;
                resolved = true;
                clearTimeout(timer);
                clearInterval(poller);
                resolve(token || null);
            }

            const poller = setInterval(() => {
                const t = _readToken();
                if (t) finish(t);
            }, 80);

            const timer = setTimeout(() => finish(null), timeout);
        });
    }

    function refreshCaptchaChallenge() {
        const refreshBtn = DOMHelper.query('.refresh.button, button.refresh, [aria-label="Get a new challenge"], [aria-label="Refresh challenge"]');
        if (refreshBtn) {
            refreshBtn.click();
            return { success: true, method: 'refresh_button' };
        }
        const closeBtn = DOMHelper.query('.close-button, [aria-label="Close"]');
        if (closeBtn) {
            closeBtn.click();
            return { success: true, method: 'close_button' };
        }
        return { success: false };
    }

    async function selectDropdownOption(value) {
        const firstOpts = await DOMHelper.waitForCondition(() => {
            const opts = DOMHelper.query('[role="option"]', true);
            return opts.length > 0 ? opts : null;
        }, 50, 10000);

        if (!firstOpts) return false;

        const strVal = String(value);
        let match = firstOpts.find(opt => opt.textContent.trim() === strVal);
        if (match) {
            match.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            await new Promise(r => setTimeout(r, 60));
            fireMouseEvents(match);
            return true;
        }

        let container = null;
        let el = firstOpts[0];
        while (el && el !== document.body) {
            const style = window.getComputedStyle(el);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll' ||
                style.overflow === 'auto' || style.overflow === 'scroll') {
                container = el;
                break;
            }
            el = el.parentElement;
        }

        if (!container) return false;

        for (let i = 0; i < 120; i++) {
            const opts = DOMHelper.query('[role="option"]', true);
            match = opts.find(opt => opt.textContent.trim() === strVal);
            if (match) break;
            container.scrollTop += 200;
            await new Promise(r => setTimeout(r, 50));
        }

        if (!match) return false;

        match.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        await new Promise(r => setTimeout(r, 60));
        fireMouseEvents(match);
        return true;
    }

    window.utils = {
        setInput,
        clickCheckbox,
        clickElement,
        setDropdown,
        selectDropdownOption,
        clickAllCheckboxes,
        openAccessibilityChallenge,
        answerAccessibilityQuestion,
        waitForDiscordToken,
        isImageCaptcha,
        refreshCaptchaChallenge
    };
})();
