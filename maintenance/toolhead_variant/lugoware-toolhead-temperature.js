// Read-only detachable sensor row. Never sends printer commands or invents 0C.
(() => {
  'use strict';
  const absent = {"en": "Not attached", "ko": "미부착", "zh_CN": "未安装", "zh_TW": "未安裝", "jp": "未装着", "de": "Nicht angebracht", "de_formal": "Nicht angebracht", "fr": "Non installé", "es": "No instalado", "it": "Non montato", "pt": "Não instalado", "pt_BR": "Não instalado", "ru": "Не установлен", "uk": "Не встановлено", "pl": "Nie zamontowano", "cs": "Nepřipojeno", "sk": "Nepripojené", "sl": "Ni nameščeno", "hr": "Nije postavljeno", "rs": "Није постављено", "bg": "Не е монтирано", "nl": "Niet geplaatst", "da": "Ikke monteret", "sv": "Inte monterad", "et": "Paigaldamata", "lt": "Nepritvirtinta", "hu": "Nincs felszerelve", "tr": "Takılı değil", "vi": "Chưa gắn", "ar": "غير مركّب", "fa": "نصب نشده", "he": "לא מותקן"};
  function language() {
    const app = document.getElementById('app');
    const i18n = app?.__vue__?.$i18n || app?.__vue_app__?.config?.globalProperties?.$i18n;
    let raw = i18n?.locale;
    raw = raw?.value || raw;
    if (typeof raw !== 'string') raw = navigator.language || 'en';
    raw = raw.replace('-', '_');
    if (/^zh/i.test(raw)) return /TW|HK|Hant/i.test(raw) ? 'zh_TW' : 'zh_CN';
    if (/^ja/i.test(raw)) return 'jp';
    if (/^sr/i.test(raw)) return 'rs';
    return absent[raw] ? raw : raw.split('_')[0];
  }
  function label(key) {
    const lang = language();
    if (key === 'absent') return absent[lang] || absent.en;
    const other = {ko:['확인 중','센서 오류','연결 확인 중'],zh_CN:['正在检查','传感器错误','正在检查连接'],zh_TW:['正在檢查','感測器錯誤','正在檢查連線']};
    return (other[lang] || ['Checking','Sensor error','Checking connection'])[key];
  }

  const notices = /* LUGOWARE_NOTICE_DATA */ null;
  const noticePatterns = notices?.patterns.map(([pattern, kind, suffix = '']) =>
    [new RegExp('^(?:' + pattern + ')$', 'u'), kind, suffix]) || [];
  const notificationSelector = '[role="alert"], .v-snack__content, .v-alert__content';
  function displayNotice(value, lang) {
    if (!notices) return null;
    lang = Object.hasOwn(notices.locales, lang) ? lang : 'en';
    const detail = notices.detail[lang];
    if (detail && Object.hasOwn(detail, value)) return detail[value];
    if (lang === 'en' && /^[\x00-\x7f]+$/.test(value)) return null;
    const row = notices.locales[lang];
    const paused = kind => (kind === 12 ? row[1] : row[4]) + ' · ' + row[2];
    if (Object.hasOwn(notices.exact, value)) {
      const kind = notices.exact[value];
      return kind === 12 || kind === 13 ? paused(kind) : row[kind];
    }
    for (const [pattern, kind, suffix] of noticePatterns) {
      const match = pattern.exec(value);
      if (!match) continue;
      const numbers = match.slice(1).join(' / ');
      if (kind === 10 || kind === 11)
        return 'T' + numbers + ' · ' + row[kind === 10 ? 0 : 7];
      if (kind === 12) return paused(kind);
      const label = kind < row.length ? row[kind] : notices.extra[lang][kind - 14];
      return label + (numbers ? ' · ' + numbers + suffix : '');
    }
    return null;
  }
  function translateNotificationText(node, lang) {
    const original = node.nodeValue;
    if (!original?.trim()) return;
    const lines = original.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const parts = /^(\s*)((?:!! |echo: |\/\/ |Klipper: )?)(.*?)(\s*)$/.exec(lines[i]);
      if (!parts) continue;
      const translated = displayNotice(parts[3], lang);
      if (translated) lines[i] = parts[1] + parts[2] + translated + parts[4];
    }
    const displayed = lines.join('\n');
    if (displayed !== original) node.nodeValue = displayed;
  }
  function observeNotifications() {
    const app = document.getElementById('app');
    if (!app || !notices) return;
    const dirty = new Set();
    let queued = false;
    const mark = node => {
      if (node instanceof Element) {
        const alert = node.closest(notificationSelector);
        if (alert) dirty.add(alert);
        node.querySelectorAll(notificationSelector).forEach(alert => dirty.add(alert));
      }
    };
    const observer = new MutationObserver(records => {
      for (const record of records) {
        const target = record.target.nodeType === Node.TEXT_NODE ? record.target.parentElement : record.target;
        const alert = target?.closest?.(notificationSelector);
        if (alert) dirty.add(alert);
        record.addedNodes.forEach(mark);
      }
      if (!dirty.size || queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        const lang = language();
        const pending = [...dirty];
        dirty.clear();
        for (const alert of pending) {
          if (!alert.isConnected) continue;
          const nodes = document.createTreeWalker(alert, NodeFilter.SHOW_TEXT);
          while (nodes.nextNode()) translateNotificationText(nodes.currentNode, lang);
        }
      });
    });
    observer.observe(app, {subtree: true, childList: true, characterData: true});
  }
  observeNotifications();

  function valueText(status) {
    if (status?.state === 'connected' && Number.isFinite(status.temperature))
      return status.temperature.toFixed(1) + '°C';
    if (status?.state === 'disconnected') return label('absent');
    if (status?.state === 'checking') return label(0);
    if (['short_circuit', 'invalid'].includes(status?.state)) return label(1);
    return label(2);
  }
  function row() {
    return [...document.querySelectorAll('tr')].find(r =>
      r.querySelector('td.name')?.textContent.trim() === 'Toolhead' && r.querySelector('td.current')) || null;
  }
  function hideToolheadPowerCurve() {
    const store = document.getElementById('app')?.__vue__?.$store;
    const settings = store?.state?.gui?.view?.tempchart?.datasetSettings;
    if (!settings || settings['heater_generic Toolhead']?.power === false) return;
    // Session-only display override: no saved preference or printer command.
    // Removing this auxiliary script restores standard-profile behavior.
    store.commit('gui/setChartDatasetStatus', {
      objectName: 'heater_generic Toolhead', dataset: 'power', value: false
    });
  }
  async function update() {
    try {
      if (document.hidden) return;
      hideToolheadPowerCurve();
      const target = row();
      if (!target) return;
      const abort = new AbortController();
      const timeout = setTimeout(() => abort.abort(), 3000);
      try {
        const response = await fetch('/printer/objects/query?toolhead_auxiliary',
          {cache: 'no-store', signal: abort.signal});
        if (!response.ok) throw new Error('Sensor unavailable');
        const data = await response.json();
        const status = data.result?.status?.toolhead_auxiliary;
        const cell = target.querySelector('td.current');
        const label = cell.querySelector('span') || cell;
        const text = valueText(status);
        if (label.textContent !== text) label.textContent = text;
      } catch (_) {
        const cell = target.querySelector('td.current');
        (cell.querySelector('span') || cell).textContent = label(2);
      } finally { clearTimeout(timeout); }
    } finally { setTimeout(update, 400); }
  }
  update();
})();
