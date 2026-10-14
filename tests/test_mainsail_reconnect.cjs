const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let tick, calls = 0, now = 10000, connected = true, authError = false, connecting = false, visible = true;
const button = {disabled:false, getClientRects:()=>[{}], click:()=>{calls++; connecting=true;}};
const dialog = {getClientRects:()=>visible?[{}]:[], querySelector:selector=>{
 if(selector==='.red--text') return authError ? {} : null;
 if(selector.startsWith('a[')) return null;
 if(selector==='button.primary--text') return connecting ? null : button;
 throw Error(selector);
}};
const context = {window:{setInterval:fn=>{tick=fn;}}, document:{querySelector:selector=>{
 assert.equal(selector,'.v-dialog--active .the-connection-dialog');
 return connected ? null : dialog;
}}, navigator:{onLine:true}, Date:{now:()=>now}};
const source=fs.readFileSync(path.join(__dirname,'../maintenance/mainsail_reconnect.js'),'utf8');
vm.runInNewContext(source,context);
tick(); assert.equal(calls,0);
connected=false; tick(); assert.equal(calls,1);
connecting=false; now+=4999; tick(); assert.equal(calls,1);
now-=4999;
now+=5000; authError=true; tick(); assert.equal(calls,1);
authError=false; context.navigator.onLine=false; tick(); assert.equal(calls,1);
context.navigator.onLine=true; connecting=true; tick(); assert.equal(calls,1);
connecting=false; button.disabled=true; tick(); assert.equal(calls,1);
button.disabled=false; visible=false; tick(); assert.equal(calls,1);
visible=true; tick(); assert.equal(calls,2);
// Restarted pages already showing connection failure also recover, without Vue or a prior connection.
now+=5000; connecting=false; tick(); assert.equal(calls,3);
console.log('PASS DOM reconnect without Vue, initial failure, throttle, auth, offline, hidden, disabled and in-flight guards');
