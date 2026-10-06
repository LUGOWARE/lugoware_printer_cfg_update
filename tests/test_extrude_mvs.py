import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest


class MvsTests(unittest.TestCase):
    def test_languages_flow_distance_and_state_restoration(self):
        for lang in ('ko', 'en'):
            source = (Path(__file__).resolve().parents[1] / 'panels' / lang / 'extrude.py').read_text(encoding='utf-8')
            tree = ast.parse(source)
            func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'extrusion_script')
            scope = {'math': math}
            exec(compile(ast.Module(body=[func], type_ignores=[]), 'extrude', 'exec'), scope)
            for diameter, flow in ((1.75, 10), (2.85, 5)):
                for direction in (-1, 1):
                    script = scope['extrusion_script'](diameter, flow, 15, direction)
                    move = next(line for line in script.splitlines() if line.startswith('G1 '))
                    feed = float(move.split(' F')[1])
                    self.assertAlmostEqual(feed / 60 * math.pi * (diameter / 2) ** 2, flow, places=6)
                    self.assertIn(f'E{direction * 15}', move)
                    self.assertTrue(script.startswith('SAVE_GCODE_STATE'))
                    self.assertIn('M400\nRESTORE_GCODE_STATE', script)
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
            adjust = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'adjust')
            exec(compile(ast.Module(body=[adjust], type_ignores=[]), 'adjust', 'exec'), scope)
            state = SimpleNamespace(diameter=1.75, flows={1.75: 10, 2.85: 5}, distance=1, render=lambda: None)
            scope['adjust'](state, None, 'flow', 1)
            scope['adjust'](state, None, 'distance', -1)
            self.assertEqual(state.flows, {1.75: 11, 2.85: 5})
            self.assertEqual(state.distance, 1)
