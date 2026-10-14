import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from filament_details import rows


class FilamentDetailsTests(unittest.TestCase):
    def test_multiple_presets_keep_order_and_zero_usage(self):
        self.assertEqual(rows({'filament_name': '["PLA", "PLA", "TPU"]',
                               'filament_weights': [4.87, 0, 2]}),
                         [('1', 'PLA', '4.87 g'), ('2', 'PLA', '0 g'), ('3', 'TPU', '2 g')])

    def test_missing_usage_is_not_zero_or_total_per_filament(self):
        self.assertEqual(rows({'filament_name': 'A;B', 'filament_weight_total': 10}),
                         [('1', 'A', '—'), ('2', 'B', '—')])
        self.assertEqual(rows({'filament_name': 'A', 'filament_weight_total': 10}),
                         [('1', 'A', '10 g')])

    def test_invalid_values_and_literal_names(self):
        self.assertEqual(rows({'filament_name': ['A < B & C', 'TPU'],
                               'filament_weights': [float('nan'), -1]}),
                         [('1', 'A < B & C', '—'), ('2', 'TPU', '—')])

    def test_usage_translation_coverage(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / 'translations').glob('*.json'):
            data = json.loads((root / 'maintenance/screen_locales' / path.name).read_text(encoding='utf-8'))
            self.assertTrue(data['Material usage'])
