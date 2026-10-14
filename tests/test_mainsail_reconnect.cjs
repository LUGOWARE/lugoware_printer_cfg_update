const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let tick, calls = 0, now = 10000;
const state = { isConnected: true, isConnecting: false, connectingFailed: false };
const app = {
  $store: { state: { socket: state }, dispatch: (_, data) => Object.assign(state, data) },
  $socket: { url: 'ws://printer/websocket', reconnects: 5, connect: () => { calls++; } }
};
const context = { window: { setInterval: fn => { tick = fn; } }, document: { getElementById: () => ({__vue__: app}) }, navigator: {onLine: true}, Date: {now: () => now} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../maintenance/mainsail_reconnect.js'), 'utf8'), context);
tick(); state.isConnected = false; state.connectingFailed = true; tick();
assert.equal(calls, 1); assert.equal(app.$socket.reconnects, 0);
state.connectingFailed = true; tick(); assert.equal(calls, 1);
now += 11000; state.connectionFailedMessage = 'UNAUTHORIZED'; tick(); assert.equal(calls, 1);
state.connectionFailedMessage = null; app.$socket.url = 'ws://different/websocket'; tick(); assert.equal(calls, 1);
app.$socket.url = 'ws://printer/websocket'; state.isConnecting = true; tick(); assert.equal(calls, 1);
state.isConnecting = false; tick(); assert.equal(calls, 2);
console.log('PASS reconnect, throttle, authorization, printer switch and in-flight guards');
