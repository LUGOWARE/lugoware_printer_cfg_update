/* .151: recovery-only ETA. No motion commands and no changes to normal jobs. */
(() => {
  if (window.lugoRecoveryEtaInstalled) return;
  window.lugoRecoveryEtaInstalled = true;
  let store, pending = false;
  function install() {
    const app = document.querySelector('#app');
    const candidate = app && app.__vue__ && app.__vue__.$store;
    const module = candidate && candidate._modulesNamespaceMap['printer/'];
    if (!module) return false;
    store = candidate;
    store.registerModule('lugoRecoveryEta', {namespaced:true,
      state: {eta:null,received:0}, mutations:{set(s,v){s.eta=v;s.received=Date.now();}}});
    const original = module._rawModule.getters;
    const getters = {...original};
    const active = root => {
      const data = root.lugoRecoveryEta;
      const eta = data.eta, stats = root.printer.print_stats;
      return eta && eta.active && stats && eta.filename === stats.filename &&
        ['printing','paused'].includes(stats.state) && Date.now()-data.received<15000 ? eta : null;
    };
    const remaining = (eta,root) => eta.remaining == null ? 0 : Math.max(0,
      eta.remaining - Math.max(0, root.printer.print_stats.print_duration-eta.elapsed));
    for (const name of ['getEstimatedTimeFile','getEstimatedTimeFilament',
                        'getEstimatedTimeSlicer','getEstimatedTimeAvg','getEstimatedTimeETA']) {
      if (typeof original[name] !== 'function') continue;
      getters[name] = (s,g,r,rg) => {
        const eta=active(r);
        if (!eta) return original[name](s,g,r,rg);
        const left=remaining(eta,r);
        return name==='getEstimatedTimeETA' ? (left>0 ? Date.now()+left*1000 : 0) : left;
      };
    }
    store.hotUpdate({modules:{printer:{namespaced:true,getters}}});
    return true;
  }
  async function poll() {
    if (!store && !install()) return;
    if (pending) return;
    pending=true;
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),4000);
    try {
      const response=await fetch('/printer/objects/query?lugo_recovery',
        {cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('status unavailable');
      const result=await response.json();
      store.commit('lugoRecoveryEta/set',result.result.status.lugo_recovery.eta || null);
    } catch (_) { store.commit('lugoRecoveryEta/set',null); }
    finally {clearTimeout(timeout);pending=false;}
  }
  setInterval(poll,5000);
  poll();
})();
