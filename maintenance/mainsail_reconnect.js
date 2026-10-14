/* Continue Mainsail reconnect attempts after a previously connected server restarts. */
(() => {
    if (window.lugowareReconnectInstalled) return;
    window.lugowareReconnectInstalled = true;
    let previousUrl = null;
    let nextAttempt = 0;
    window.setInterval(() => {
        const app = document.getElementById('app')?.__vue__;
        const state = app?.$store?.state?.socket;
        const socket = app?.$socket;
        if (!state || !socket) return;
        if (state.isConnected) {
            previousUrl = socket.url;
            nextAttempt = 0;
            return;
        }
        // Do not interfere with printer selection, authorization failures or an active attempt.
        if (socket.url !== previousUrl || !state.connectingFailed || state.isConnecting ||
            state.connectionFailedMessage || !navigator.onLine || Date.now() < nextAttempt) return;
        nextAttempt = Date.now() + 10000;
        socket.reconnects = 0;
        app.$store.dispatch('socket/setData', { connectingFailed: false });
        socket.connect();
    }, 2000);
})();
