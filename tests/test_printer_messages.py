import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'maintenance'
sys.path.insert(0, str(ROOT))
from printer_messages import translate_printer_message


class PrinterMessages(unittest.TestCase):
    def test_all_catalogs_complete_and_preserve_dynamic_values(self):
        rules = json.loads((ROOT / 'message_rules.json').read_text(encoding='utf-8'))
        catalogs = list((ROOT / 'printer_locales').glob('*.json'))
        self.assertEqual(len(catalogs), 32)
        for path in catalogs:
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(set(data), set(rules['keys']), path.name)
            for key, value in data.items():
                self.assertTrue(value.strip(), (path.name, key))
                self.assertEqual(sorted(re.findall(r'\{\w+\}', key)),
                                 sorted(re.findall(r'\{\w+\}', value)), (path.name, key))
            for pattern, key in rules['patterns'].items():
                values = {name: ('1' if name in ('count', 'attempt') else '2' if name == 'total' else '12.5') for name in re.findall(r'\{(\w+)\}', key)}
                message = key.format(**values)
                if key == 'Tool change {count}':
                    message = 'Toolchange 1'
                result = translate_printer_message(message, lambda s: data.get(s, s))
                self.assertIsNotNone(result, (path.name, key))
                self.assertNotRegex(result, r'\{\w+\}')

    def test_unknown_filenames_and_gcode_are_not_translated(self):
        for text in ('My PLA.gcode', 'G1 X10 Y125', 'PLA custom 210', '42%'):
            self.assertIsNone(translate_printer_message(text, lambda s: 'translated'))

    def test_korean_dock_failure(self):
        data = json.loads((ROOT / 'printer_locales/ko.json').read_text(encoding='utf-8'))
        self.assertEqual(translate_printer_message('Tool-head is not in position.',
                         lambda s: data.get(s, s)), '툴헤드가 제 위치에 없습니다.')
