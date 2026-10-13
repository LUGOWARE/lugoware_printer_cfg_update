"""Translate known printer messages at display time, never G-code or filenames."""
import json
import re
from pathlib import Path

_rules = json.loads(Path(__file__).with_name('message_rules.json').read_text(encoding='utf-8'))
_keys = set(_rules['keys'])
_patterns = [(re.compile(p), k) for p, k in _rules['patterns'].items()]
_values = {'NORMAL': 'Normal operation', 'FAIL': 'Heating failure',
           '정상 작동': 'Normal operation', '가열 불량': 'Heating failure',
           'printing': 'Printing', 'paused': 'Paused', 'standby': 'Standby',
           'complete': 'Complete', 'cancelled': 'Cancelled'}
_aliases = {'취소 요청 전송 실패': 'Cancel request failed', '취소 실패': 'Cancel failed'}

def translate_printer_message(text, tr):
    raw = str(text)
    value = raw.strip()
    if value in _aliases:
        return tr(_aliases[value])
    if value in _keys:
        return tr(value)
    for pattern, key in _patterns:
        match = pattern.fullmatch(value)
        if match:
            args = {k: tr(_values.get(v, v)) if v in _values or v in _keys else v
                    for k, v in match.groupdict().items()}
            try:
                return tr(key).format(**args)
            except (KeyError, ValueError):
                return key.format(**args)
    # Klipper adds an error wrapper to macro exceptions; translate only the payload.
    for prefix in ('!! ', 'echo: ', '// ', 'Klipper: '):
        if value.startswith(prefix):
            translated = translate_printer_message(value[len(prefix):], tr)
            if translated is not None:
                return prefix + translated
    if 'gcode.CommandError: ' in value:
        payload = value.rsplit('gcode.CommandError: ', 1)[1]
        translated = translate_printer_message(payload, tr)
        if translated is not None:
            return tr('Command failed') + '\n' + translated
    return None
