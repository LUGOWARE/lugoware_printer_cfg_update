/* Retry the native Mainsail reconnect control without relying on Vue internals. */
(() => {
    if (window.lugowareReconnectInstalled) return;
    window.lugowareReconnectInstalled = true;
    let nextAttempt = 0;
    window.setInterval(() => {
        if (!navigator.onLine || Date.now() < nextAttempt) return;
        // Scope to the connection-failed dialog, never printer selection or print controls.
        const dialog = document.querySelector('.v-dialog--active .the-connection-dialog');
        if (!dialog || !dialog.getClientRects().length) return;
        // Mainsail displays protocol/authentication errors separately from an ordinary outage.
        if (dialog.querySelector('.red--text') || dialog.querySelector('a[href*="connection-"]')) return;
        const button = dialog.querySelector('button.primary--text');
        if (!button || button.disabled || !button.getClientRects().length) return;
        nextAttempt = Date.now() + 10000;
        button.click();
    }, 2000);
})();
