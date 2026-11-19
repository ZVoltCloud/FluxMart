document.addEventListener('DOMContentLoaded', () => {
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const tabId = btn.dataset.tab;
            const tabEl = document.getElementById(tabId + "-tab");
            if (tabEl) tabEl.classList.add("active");

            // Initialize Token Manager when its tab is opened
            if (tabId === 'humanizer' && typeof tmInit === 'function') {
                tmInit();
            }

            // Auto-refresh account info when account tab is opened
            if (tabId === 'account' && typeof refreshAccountInfo === 'function') {
                refreshAccountInfo(false);
            }

            // Auto-refresh installer status when installer tab is opened
            if (tabId === 'installer' && typeof instRefresh === 'function') {
                instRefresh();
            }
        });
    });
});

function tabsScroll(amount) {
    const bar = document.getElementById('tabsBar');
    if (bar) bar.scrollBy({ left: amount, behavior: 'smooth' });
}
