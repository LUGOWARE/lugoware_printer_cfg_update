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
