"""Translate known printer messages at display time, never G-code or filenames."""
import json
import re
from pathlib import Path
from functools import lru_cache

_rules = json.loads(Path(__file__).with_name('message_rules.json').read_text(encoding='utf-8'))
_keys = set(_rules['keys'])
_patterns = [(re.compile(p), k) for p, k in _rules['patterns'].items()]
_values = {'NORMAL': 'Normal operation', 'FAIL': 'Heating failure',
           '정상 작동': 'Normal operation', '가열 불량': 'Heating failure',
           'printing': 'Printing', 'paused': 'Paused', 'standby': 'Standby',
           'complete': 'Complete', 'cancelled': 'Cancelled'}
_aliases = {'취소 요청 전송 실패': 'Cancel request failed', '취소 실패': 'Cancel failed'}

@lru_cache(maxsize=1)
def toolhead_notice_catalog():
    path = Path(__file__).with_name('toolhead_notices.json')
    if not path.is_file():
        path = path.parent / 'toolhead_variant' / 'notice_locales.json'
    if not path.is_file():
        return {}, []
    data = json.loads(path.read_text(encoding='utf-8'))
    return data, [(re.compile(row[0]), *row[1:]) for row in data['patterns']]


def translate_toolhead_notice(text, language):
    data, patterns = toolhead_notice_catalog()
    if not data or not isinstance(text, str):
        return None
    value = text.strip()
    for prefix in ('!! ', 'echo: ', '// ', 'Klipper: '):
        if value.startswith(prefix):
            translated = translate_toolhead_notice(value[len(prefix):], language)
            return prefix + translated if translated else None
    if '\n' in value:
        first, rest = value.split('\n', 1)
        translated = translate_toolhead_notice(first, language)
        return translated + '\n' + rest if translated else None
    language = language if language in data['locales'] else 'en'
    direct = data['detail'].get(language, {}).get(value)
    if direct:
        return direct
    row = data['locales'][language]
    kind = data['exact'].get(value)
    if kind is not None and (language != 'en' or not value.isascii()):
        return row[1] + ' · ' + row[2] if kind == 12 else (
            row[4] + ' · ' + row[2] if kind == 13 else row[kind])
    for pattern, kind, *suffix in patterns:
        match = pattern.fullmatch(value)
        if not match or (language == 'en' and value.isascii()):
            continue
        numbers = ' / '.join(match.groups())
        if kind == 10:
            return 'T' + numbers + ' · ' + row[0]
        if kind == 11:
            return 'T' + numbers + ' · ' + row[7]
        if kind == 12:
            return row[1] + ' · ' + row[2]
        label = row[kind] if kind < len(row) else data['extra'][language][kind - 14]
        return label + (' · ' + numbers + (suffix[0] if suffix else '') if numbers else '')
    return None


def translate_printer_message(text, tr):
    raw = str(text)
    value = raw.strip()
    localized = tr(value)
    if value not in _keys and localized != value:
        return localized
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
