"""Offline translations for LUGOWARE UI, layered over KlipperScreen gettext."""
import builtins
import gettext
import json
from pathlib import Path
import re


class Translations(gettext.NullTranslations):
    def __init__(self, upstream, language, directory=None):
        super().__init__()
        self.upstream = upstream
        directory = Path(directory) if directory else Path(__file__).with_name('lugoware_locales')
        self.catalog = {}
        language = {'ja': 'jp', 'sr': 'rs'}.get(language, language)
        # Only read a locale basename, never an arbitrary path from configuration.
        if re.fullmatch(r'[A-Za-z_]+', language or ''):
            path = directory / (language + '.json')
            if path.is_file():
                self.catalog = json.loads(path.read_text(encoding='utf-8'))

    def gettext(self, message):
        original = self.upstream.gettext(message)
        return original if original != message else self.catalog.get(message, original)

    def ngettext(self, singular, plural, n):
        return self.upstream.ngettext(singular, plural, n)


def with_translations(upstream, language):
    return Translations(upstream, language)


def translate_text(text):
    """Translate known UI payloads only; never alter G-code or user names."""
    tr = getattr(builtins, '_', lambda s: s)
    aliases = {'히터 테스트 완료': 'Heater test complete', '확인': 'Confirm',
               '정상 작동': 'Normal operation', '가열 불량': 'Heating failure'}
    stripped = text.strip()
    if stripped in aliases:
        return tr(aliases[stripped])
    match = re.fullmatch(r'히터 (\d+) \(([^)]+)\): (정상 작동|가열 불량)', stripped)
    if match:
        return tr('Heater {number} ({pin}): {result}').format(
            number=match[1], pin=match[2], result=tr(aliases[match[3]]))
    match = re.fullmatch(r'온도 (상승|변화): ([-+\d.]+)C', stripped)
    if match:
        key = 'Temperature rise: {value}°C' if match[1] == '상승' else 'Temperature change: {value}°C'
        return tr(key).format(value=match[2])
    return tr(text)


def translate_prompt(data):
    for prefix in ('prompt_begin ', 'prompt_text '):
        if data.startswith(prefix):
            return prefix + translate_text(data[len(prefix):])
    for prefix in ('prompt_button ', 'prompt_footer_button '):
        if data.startswith(prefix):
            label, separator, command = data[len(prefix):].partition('|')
            # A missing explicit action can use the label as G-code; leave it alone.
            if separator:
                return prefix + translate_text(label) + separator + command
    return data


def preheat_label(option):
    match = re.fullmatch(r'(?:Bed|베드)\s*:\s*(\d+)\s*(?:℃|°C)', option)
    if match:
        return getattr(builtins, '_', lambda s: s)('Bed') + ' : ' + match[1] + '°C'
    return option
