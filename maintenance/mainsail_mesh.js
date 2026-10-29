/* .151 trial: add a bed mesh choice to Mainsail's existing confirmation dialog. */
(() => {
  if (window.lugoMeshChoiceInstalled) return;
  window.lugoMeshChoiceInstalled = true;
  const style = document.createElement('style');
  style.textContent = '[data-lugo-mesh] input{appearance:none!important;width:38px!important;height:22px!important;border-radius:12px;background:#666;position:relative;margin:0;flex-shrink:0}[data-lugo-mesh] input:before{content:"";position:absolute;width:18px;height:18px;top:2px;left:2px;border-radius:50%;background:white}[data-lugo-mesh] input:checked{background:#2196f3}[data-lugo-mesh] input:checked:before{left:18px}[data-lugo-mesh] input:focus-visible{outline:2px solid white;outline-offset:3px}';
  document.head.append(style);
  function findVm(el) {
    let vm = el.__vue__;
    for (let n = 0; vm && n < 15; n++, vm = vm.$parent) {
      if (typeof vm.startPrint === 'function' && vm.file && typeof vm.currentPath === 'string' && vm.$socket) return vm;
    }
    return null;
  }
  function install() {
    document.querySelectorAll('.v-dialog--active').forEach(dialog => {
      if (dialog.querySelector('[data-lugo-mesh]')) return;
      let vm = null;
      for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
        vm = findVm(el); if (vm) break;
      }
      if (!vm) return;
      const actions = dialog.querySelector('.v-card__actions');
      if (!actions) return;
      const locale = String(vm.$i18n?.locale || 'en').toLowerCase();
      const label = locale.startsWith('ko') ? '베드 메쉬' : locale.startsWith('zh') ? '床网格' : locale.startsWith('ja') || locale.startsWith('jp') ? 'ベッドメッシュ' : 'Bed mesh';
      const row = document.createElement('label'); row.dataset.lugoMesh = '1';
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:8px 24px;gap:16px;cursor:pointer';
      const caption = document.createElement('span'); caption.textContent = label;
      const input = document.createElement('input'); input.type = 'checkbox'; input.checked = true;
      input.setAttribute('role','switch'); input.setAttribute('aria-label', label);
      input.style.cssText = 'width:22px;height:22px;accent-color:#2196f3;cursor:pointer';
      row.append(caption,input); actions.before(row);
      vm.__lugoMeshInput = input;
      if (vm.__lugoMeshWrapped) return;
      vm.__lugoMeshWrapped = true;
      vm.startPrint = function(filename = '') {
        // Same authenticated websocket and native dashboard callback as Mainsail.
        const full = (this.currentPath + '/' + filename).substring(1);
        if (/[\r\n\x00]/.test(full)) return;
        const quoted = full.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const enabled = this.__lugoMeshInput?.checked !== false;
        this.closeDialog();
        this.$socket.emit('printer.gcode.script', {
          script: 'SCREEN_MESH_SELECT ENABLE=' + Number(enabled) + '\nSDCARD_PRINT_FILE FILENAME="' + quoted + '"'
        }, {action:'switchToDashboard'});
      };
    });
  }
  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; install(); });
  }).observe(document.documentElement, {childList:true,subtree:true});
  install();
})();
