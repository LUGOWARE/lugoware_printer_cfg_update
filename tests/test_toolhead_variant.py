import configparser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import os
import stat
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'maintenance'))
spec = importlib.util.spec_from_file_location('variant', ROOT/'maintenance/install_toolhead_variant.py')
variant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(variant)


def profile():
    text = '[extruder]\nsensor_pin: PA1\n\n[filament_switch_sensor toolhead_sensor]\nswitch_pin: ^PC3\ndebounce_delay: 0.2\npause_on_runout: True\n'
    for n in range(4):
        text += ('\n[gcode_macro DOCK_TOOL_%d]\ngcode:\n    G1 X100\n'
                 '    FAST_CANCEL_WAIT P={(h_d * 1000)|int}\n' % n)
        for name in ('PARK_TOOL_', 'PARK_'):
            text += '\n[gcode_macro %s%d]\ngcode:\n    G1 X200\n' % (name, n)
    return text


class VariantTests(unittest.TestCase):
    def test_legacy_single_heater_retains_its_wiring_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LUGOWARE_VARIANT': ''}):
            home = Path(directory)
            marker = home / '.local/share/lugoware/variant.json'
            marker.parent.mkdir(parents=True)
            marker.write_text('{"variant":"toolhead"}', encoding='utf-8')
            config = home / 'printer_data/config'
            config.mkdir(parents=True)
            base = config / 'printer_base.cfg'
            base.write_text('[extruder]\nheater_pin: PC5  # nozzle\n', encoding='utf-8')
            auxiliary = config / 'toolhead_auxiliary.cfg'
            auxiliary.write_text('[heater_generic Toolhead]\nheater_pin: PA7\n', encoding='utf-8')
            self.assertEqual(variant.selected(home), 'toolhead_single')
            with patch.dict(os.environ, {'LUGOWARE_VARIANT': 'toolhead'}):
                self.assertEqual(variant.selected(home), 'toolhead')
            base.write_text('[extruder]\nheater_pin: multi_pin:dual_hotend_heater\n', encoding='utf-8')
            self.assertEqual(variant.selected(home), 'toolhead')

    def test_auxiliary_release_uses_published_tuning_and_preserves_device_settings(self):
        defaults = (Path(variant.__file__).parent / 'toolhead_variant/toolhead_auxiliary.cfg').read_text(encoding='utf-8')
        installed = defaults.replace('sync_manual_preheat: False', 'sync_manual_preheat: True')
        installed = installed.replace('max_temp: 300', 'max_temp: 285\npwm_cycle_time: 0.015')
        installed += '\n[gcode_macro LOCAL_AUX_SERVICE]\ngcode: M400\n'
        released = defaults.replace('prime_timeout: 60', 'prime_timeout: 55')
        released = released.replace('pid_kp: 37.681', 'pid_kp: 37.690')
        result = variant.merge_auxiliary_release(installed, released)
        self.assertIn('sync_manual_preheat: True', result)
        self.assertIn('max_temp: 285', result)
        self.assertIn('pwm_cycle_time: 0.015', result)
        self.assertIn('[gcode_macro LOCAL_AUX_SERVICE]', result)
        self.assertEqual(variant.merge_auxiliary_release(result, released), result)
        fresh = variant.merge_auxiliary_release(None, released)
        self.assertIn('prime_timeout: 55', fresh)
        self.assertIn('max_temp: 300', fresh)
        self.assertIn('prime_timeout: 55', result)
        self.assertIn('pid_kp: 37.690', result)

    def test_prepare_extrusion_upgrade_changes_one_stock_move(self):
        old = 'G1 E{10.0 * factor} F{8.0 * 60 / (3.141592653589793 * (dia / 2) ** 2)}'
        cfg = ('[gcode_macro PREPARE_ACTION]\ngcode:\n    ' + old
               + '\n[gcode_macro OTHER]\ngcode:\n    ' + old + '\n')
        updated = variant.prepare_extrusion_distance(cfg)
        self.assertEqual(updated.count('G1 E{20.0 * factor}'), 1)
        self.assertTrue(updated.endswith('    ' + old + '\n'))
        self.assertEqual(variant.prepare_extrusion_distance(updated), updated)
        custom = cfg.replace('10.0 * factor', '17.5 * factor')
        self.assertEqual(variant.prepare_extrusion_distance(custom), custom)

    def test_paused_tool_menu_remains_above_saved_screen_settings(self):
        menu = '[menu __print paused_tool_service]'
        marker = '#~# --- Do not edit below this line. This section is auto generated --- #~#'
        saved = marker + '\n#~# [main]\n#~# language = en\n'
        existing = '[menu __print temperature]\nname: Temperature\n\n' + saved
        legacy = existing + '\n' + menu + '\nname: Load tool\n'
        updated = variant.paused_tools.menu(legacy, True)
        self.assertLess(updated.index(menu), updated.index(marker))
        self.assertEqual(updated.count(menu), 1)
        self.assertTrue(updated[updated.index(marker):].startswith(saved))
        self.assertEqual(variant.paused_tools.menu(updated, True), updated)
        self.assertNotIn(menu, variant.paused_tools.menu(updated, False))

    @unittest.skipUnless(os.name == 'posix', 'Linux permissions required')
    def test_common_web_helpers_repair_permissions(self):
        for helper, filename in [('reconnect','lugoware-reconnect.js'),('mesh','lugoware-mesh.js')]:
            with self.subTest(helper=helper), tempfile.TemporaryDirectory() as d:
                root=Path(d);web=root/'mainsail';web.mkdir();index=web/'index.html'
                index.write_text('<html><head></head><body></body></html>');index.chmod(0o600)
                env=dict(os.environ,MAINSAIL_DIR=str(web),BACKUP_DIR=str(root/'backup'))
                subprocess.run([sys.executable,str(ROOT/'maintenance'/('install_mainsail_'+helper+'.py'))],
                               check=True,env=env,capture_output=True,preexec_fn=lambda:os.umask(0o077))
                for p in (index,web/filename):self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o644)

    @unittest.skipUnless(os.name == 'posix', 'Linux permissions required')
    def test_web_assets_readable_under_private_umask(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); web=root/'mainsail'; web.mkdir()
            index=web/'index.html'; index.write_bytes(b'unchanged'); index.chmod(0o600)
            script=web/'lugoware-toolhead-temperature.js'
            secret=root/'private.json'; secret.write_bytes(b'old');secret.chmod(0o600)
            old=os.umask(0o077)
            try:
                variant.commit({index:b'unchanged',script:b'public',secret:b'new'},root/'backup')
                self.assertEqual(os.umask(0o077),0o077)
            finally:os.umask(old)
            for path in (index,script):self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE((root/'backup'/'0').stat().st_mode),0o600)

    @unittest.skipUnless(os.name == 'posix', 'Linux permissions required')
    def test_failed_transaction_restores_mode(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);web=root/'mainsail';web.mkdir();index=web/'index.html'
            index.write_bytes(b'original');index.chmod(0o600)
            blocker=root/'block';blocker.write_bytes(b'block')
            with self.assertRaises(OSError):variant.commit({index:b'new',blocker/'bad':b'x'},root/'backup')
            self.assertEqual(index.read_bytes(),b'original')
            self.assertEqual(stat.S_IMODE(index.stat().st_mode),0o600)

    def test_atomic_staging_is_outside_watched_config(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); config = root/'config'; config.mkdir()
            target = config/'printer.cfg'; target.write_bytes(b'old')
            backup = root/'backups'/'update'
            replace = variant.os.replace
            observed = []
            def record(src, dst):
                observed.append((src, dst)); replace(src, dst)
            with patch.object(variant.os, 'replace', side_effect=record):
                variant.commit({target: b'new'}, backup)
            self.assertEqual(observed, [(backup/'.variant-stage-0', target)])
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual((backup/'0').read_bytes(), b'old')
            self.assertEqual(list(config.iterdir()), [target])

    def test_unchanged_file_does_not_emit_replace(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); target = root/'printer.cfg'; target.write_bytes(b'same')
            with patch.object(variant.os, 'replace') as replace:
                variant.commit({target:b'same'},root/'backup')
                replace.assert_not_called()

    def test_release_pid_overrides_old_saved_aux_pid(self):
        old = '[heater_generic Toolhead]\nheater_pin: PB7\npid_kp = 1\npid_ki: 2\npid_kd: 3\n'
        new = variant.pid_profile(old, 'heater_generic Toolhead', variant.TOOLHEAD_PID)
        self.assertIn('pid_kp: 37.681', new)
        self.assertIn('pid_ki: 9.191', new)
        self.assertIn('pid_kd: 38.623', new)
        self.assertIn('heater_pin: PB7', new)
        saved = '#*# [heater_generic Toolhead]\n#*# pid_kp = 1\n#*# pid_ki = 2\n#*# pid_kd = 3\n'
        saved = variant.nozzle_header_profile(saved, 'toolhead')
        self.assertIn('#*# pid_kp: 37.681', saved)
        self.assertIn('#*# pid_kd: 38.623', saved)

    def test_auxiliary_pt1000_and_standard_restoration(self):
        original = profile().replace('sensor_pin: PA1', 'sensor_type: pt1000_cal\nsensor_pin: PA1\ncontrol: pid\npid_kp: 24.053')
        aux = variant.base_profile(original, 'toolhead')
        self.assertIn('sensor_type: PT1000\n', aux)
        self.assertIn('pid_kp: 13.953', aux)
        self.assertEqual(aux, variant.base_profile(aux, 'toolhead'))
        restored = variant.base_profile(aux, 'standard')
        self.assertIn('sensor_type: pt1000_cal\n', restored)
        self.assertNotIn('lugoware_standard_sensor_type', restored)
        self.assertEqual(original, variant.base_profile(original, 'standard'))

    def test_header_and_save_config_sensor_override(self):
        original = '[extruder]\nsensor_type: pt1000_cal\n\n#*# [extruder]\n#*# sensor_type: pt1000_cal\n#*# pid_kp: 24.053\n'
        aux = variant.nozzle_header_profile(original, 'toolhead')
        self.assertEqual(aux.count('sensor_type: PT1000\n'), 2)
        self.assertIn('#*# pid_kp: 13.953', aux)
        self.assertEqual(aux, variant.nozzle_header_profile(aux, 'toolhead'))
        self.assertEqual(original, variant.nozzle_header_profile(aux, 'standard'))

    def test_round_trip_and_idempotence(self):
        original = profile()
        aux = variant.base_profile(original, 'toolhead')
        self.assertEqual(aux.count('TOOLHEAD_DOCK_HEAT TEMP='), 4)
        self.assertEqual(aux.count('    TOOLHEAD_PARK_OFF'), 8)
        self.assertEqual(aux, variant.base_profile(aux, 'toolhead'))
        standard = variant.base_profile(aux, 'standard')
        self.assertNotIn('TOOLHEAD_PARK_OFF', standard)
        self.assertIn('switch_pin: ^PC3', standard)
        self.assertIn('debounce_delay: 0.2', standard)
        moves = lambda s: [l for l in s.splitlines() if 'G1 ' in l]
        self.assertEqual(moves(original), moves(aux))
        self.assertEqual(moves(original), moves(standard))

    def test_pin_conflict_blocks(self):
        with self.assertRaises(ValueError):
            variant.base_profile(profile()+'\n[output_pin other]\npin: PB7\n', 'toolhead')

    def test_release_tuning_replaces_only_managed_options(self):
        defaults = (ROOT/'maintenance/toolhead_variant/toolhead_auxiliary.cfg').read_text(encoding='utf-8')
        installed = (
            '[toolhead_auxiliary]\nsensor_pin: PA2\npullup_resistor: 5000\n'
            'prime_temperature_margin = 18\nprime_timeout: 40\n'
            'nozzle_temperature_offset: 30\nnozzle_offset_threshold: 150\nnozzle_offset_max_temp: 320\n'
            'park_nozzle_preheat_offset: 2\n\n[heater_generic Toolhead]\nmax_temp: 295\n'
        )
        for original in (installed, installed.split('prime_temperature_margin')[0], defaults):
            updated = variant.apply_release_tuning(original, defaults)
            self.assertEqual(variant.apply_release_tuning(updated, defaults), updated)
            for line in ('prime_temperature_margin: 5', 'prime_timeout: 60',
                         'park_nozzle_preheat_offset: 25'):
                self.assertEqual(updated.count(line), 1)
        updated = variant.apply_release_tuning(installed, defaults)
        self.assertIn('pullup_resistor: 5000  # 센서 풀업 저항(Ω) / Sensor pull-up resistance (ohms)\n', updated)
        self.assertIn('max_temp: 295\n', updated)
        self.assertNotIn('prime_timeout: 40', updated)
        for key in variant.LEGACY_NOZZLE_OFFSETS:
            self.assertNotIn(key, updated)
        self.assertIn('sync_manual_preheat: False', updated)

        for saved, expected in (('True', True), ('on', True), ('False', False)):
            previous = installed.replace('sensor_pin: PA2', 'sensor_pin: PA6\n'
                                         + f'sync_manual_preheat = {saved}  ; previous comment')
            updated = variant.apply_release_tuning(previous, defaults)
            self.assertEqual(variant.apply_release_tuning(updated, defaults), updated)
            parser = configparser.RawConfigParser(inline_comment_prefixes=(';', '#'))
            parser.read_string(updated)
            sensor = parser['toolhead_auxiliary']
            self.assertIs(sensor.getboolean('sync_manual_preheat'), expected)
            self.assertEqual(sensor['sensor_pin'], 'PA6')
            self.assertEqual(sensor.getint('pullup_resistor'), 5000)
            self.assertEqual(sensor.getint('prime_timeout'), 60)
            self.assertIn(f'sync_manual_preheat: {saved}  # 대기 중', updated)

    def test_legacy_and_cfg_toolchange_macros_round_trip(self):
        assets = ROOT/'maintenance/toolhead_variant'
        patches = json.loads((assets/'dock_wait_patches.json').read_text(encoding='utf-8'))
        standard = ''.join('[gcode_macro ' + name + ']\ngcode:\n' +
                           ''.join(before for before, _ in edits)
                           for name, edits in patches.items())
        auxiliary = variant.dock_wait_profile(standard, patches, 'toolhead')
        self.assertEqual(auxiliary.count('TOOLHEAD_WAIT_FOR_PRIME TARGET={slicer_temp}\n'), 4)
        offset_ref = 'printer.toolhead_auxiliary.park_nozzle_preheat_offset'
        old_ref = 'printer.toolhead_temperature_test.park_nozzle_preheat_offset'
        self.assertEqual(auxiliary.count(offset_ref), 4)
        previous_release = auxiliary.replace(offset_ref, old_ref)
        self.assertEqual(variant.dock_wait_profile(previous_release, patches, 'toolhead'), auxiliary)
        self.assertEqual(variant.dock_wait_profile(previous_release, patches, 'standard'), standard)
        for offset in (5, 25, 40):
            legacy = auxiliary.replace('TARGET={slicer_temp}\n', 'TARGET={slicer_temp} TIMEOUT=60\n')
            legacy = legacy.replace(offset_ref, str(offset))
            self.assertEqual(variant.dock_wait_profile(legacy, patches, 'toolhead'), auxiliary)
            self.assertEqual(variant.dock_wait_profile(legacy, patches, 'standard'), standard)
        self.assertEqual(variant.dock_wait_profile(auxiliary, patches, 'standard'), standard)

    def test_legacy_section_migrates_and_keeps_sensor_settings(self):
        legacy = '[toolhead_temperature_test]\nsensor_pin: PA2\npullup_resistor: 5000\n\n'
        new = '[toolhead_auxiliary]\nsensor_pin: PA2\npullup_resistor: 5000\n\n'
        self.assertEqual(variant.migrate_auxiliary_section(legacy), new)
        self.assertEqual(variant.migrate_auxiliary_section(new + legacy), new)
        self.assertEqual(variant.migrate_auxiliary_section(legacy + new), new)

    def test_header_grouping_keeps_saved_bytes_and_custom_settings(self):
        head = ('[include toolhead_auxiliary.cfg]\n# MCU settings\n\n'
                '[include mainsail.cfg]\n[include printer_base.cfg]\n'
                '[include printer_custom.cfg]\n[exclude_tool_guard]\n\n'
                '[probe_auto_recovery]\nattempts: 2\n\n[mcu]\ncanbus_uuid: aabbcc\n\n'
                '[lugo_recovery]\n\n[lugo_preanalysis]\n\n[custom]\nvalue: one\n\n')
        marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
        saved = marker + '\r\n#*# [probe]\r\n#*# z_offset = 0.321\r\n'
        organized = variant.organize_printer_header(head + saved)
        self.assertTrue(organized.startswith('# MCU settings\n'))
        self.assertIn('[exclude_tool_guard]\n[include toolhead_auxiliary.cfg]\n'
                      '[lugo_recovery]\n[lugo_preanalysis]\n\n[probe_auto_recovery]', organized)
        self.assertIn('[mcu]\ncanbus_uuid: aabbcc\n\n[custom]\nvalue: one\n', organized)
        self.assertEqual(organized[organized.index(marker):], saved)
        self.assertEqual(variant.organize_printer_header(organized), organized)
        standard = head.replace('[include toolhead_auxiliary.cfg]\n', '')
        self.assertNotIn('toolhead_auxiliary.cfg', variant.organize_printer_header(standard))

    def test_header_layout_orders_model_and_keeps_device_blocks(self):
        saved = '#*# <---------------------- SAVE_CONFIG ---------------------->\r\n#*# z_offset = 0.123\r\n'
        names = [name for name in variant.HEADER_ORDER if name != variant.AUXILIARY_INCLUDE]
        for profile in ('standard', 'toolhead'):
            order = variant.HEADER_ORDER if profile == 'toolhead' else names
            for model in 'MLW':
                with self.subTest(profile=profile, model=model):
                    template = '\n'.join(f'[{name}]' for name in order) + f'\nmodel: {model}\n'
                    preferred, model_code = variant.header_layout(f'# FLEX4_{model}_V3.5.1\n', profile, template)
                    config = {
                        'mcu': 'canbus_uuid: aabbcc\nrestart_method: command',
                        'virtual_sdcard': 'path: /custom/gcodes',
                        'screen_mesh': 'path: /custom/mesh.json',
                        'probe_auto_recovery': 'attempts: 3',
                        'lugo_diagnostics': 'model: X\nxy_speed: 123\nz_speed: 4',
                    }
                    body = '\n\n'.join(f'[{name}]\n{config.get(name, "")}' for name in reversed(order))
                    organized = variant.organize_printer_header(body + '\n\n' + saved, preferred, model_code)
                    resolved = [name[1] for name in variant.HEADER_SECTION.finditer(organized)]
                    self.assertEqual(resolved, list(order))
                    self.assertIn(f'model: {model}\nxy_speed: 123\nz_speed: 4', organized)
                    self.assertIn('canbus_uuid: aabbcc\nrestart_method: command', organized)
                    self.assertIn('attempts: 3', organized)
                    self.assertIn('path: /custom/gcodes', organized)
                    self.assertIn('path: /custom/mesh.json', organized)
                    self.assertTrue(organized.endswith(saved))
                    self.assertEqual(variant.organize_printer_header(organized, preferred, model_code), organized)
                    other_model = next(code for code in 'MLW' if code != model)
                    with self.assertRaisesRegex(ValueError, 'selected model'):
                        variant.header_layout(f'# FLEX4_{other_model}_V3.5.1\n', profile, template)

    def test_legacy_embedded_config_is_captured_before_header_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            cfg = home/'printer_data/config'
            cfg.mkdir(parents=True)
            legacy = ('[toolhead_temperature_test]\nsensor_pin: PA2\n\n'
                      '[heater_generic Toolhead]\nheater_pin: PB7\n')
            (cfg/'printer.cfg').write_text(legacy)
            variant.capture(home, home/'backup')
            self.assertEqual((cfg/'toolhead_auxiliary.cfg').read_text(),
                             legacy.replace('[toolhead_temperature_test]', '[toolhead_auxiliary]'))
            self.assertEqual(variant.selected(home), 'toolhead')

    def test_missing_macro_blocks(self):
        with self.assertRaises(ValueError):
            variant.base_profile(profile().replace('[gcode_macro PARK_2]', '[gcode_macro OTHER]'), 'toolhead')

    def test_ui_patch_roundtrip(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        for edits in patches.values():
            for old, new in edits:
                self.assertEqual(variant.patch_ui(old, [(old, new)], 'toolhead'), new)
                self.assertEqual(variant.patch_ui(new, [(old, new)], 'toolhead'), new)
                self.assertEqual(variant.patch_ui(new, [(old, new)], 'standard'), old)

    def test_existing_double_quote_translation(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        edits = patches['KlipperScreen/ks_includes/screen_panel.py']
        before, after = edits[0]
        installed = after.replace("_('Not attached')", '_("Not attached")')
        self.assertEqual(variant.patch_ui(installed, edits, 'toolhead'), after)
        self.assertEqual(variant.patch_ui(installed, edits, 'standard'), before)

    def test_legacy_korean_label_and_partial_upgrade(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        edits = patches['KlipperScreen/ks_includes/screen_panel.py']
        before, after = edits[0]
        for literal in ('"미부착"', "'미부착'"):
            legacy = after.replace("_('Not attached')", literal)
            self.assertEqual(variant.patch_ui(legacy, edits, 'toolhead'), after)
            self.assertEqual(variant.patch_ui(legacy, edits, 'standard'), before)

    def test_unknown_ui_preserved(self):
        with self.assertRaises(ValueError):
            variant.patch_ui('unknown', [('a', 'b')], 'toolhead')

    def test_preflight_does_not_block_old_screen_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home/'printer_data/config'
            config.mkdir(parents=True)
            (config/'printer.cfg').write_text('[mcu]\nserial: test\n')
            assets = ROOT/'maintenance/toolhead_variant'
            variant.preflight(home, 'toolhead', assets, screen_upgrade_pending=True)
            with self.assertRaisesRegex(ValueError, 'Missing UI file'):
                variant.preflight(home, 'toolhead', assets, screen_upgrade_pending=False)
            self.assertEqual((config/'printer.cfg').read_text(), '[mcu]\nserial: test\n')

    def test_standard_preflight_does_not_require_auxiliary_ui(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home/'printer_data/config'
            config.mkdir(parents=True)
            (config/'printer.cfg').write_text('[mcu]\nserial: test\n')
            variant.preflight(home, 'standard', ROOT/'maintenance/toolhead_variant')
            self.assertFalse((home/'.local/share/lugoware/variant.json').exists())

    def test_atomic_write_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);a=root/'a';a.write_bytes(b'old')
            blocked=root/'not-directory';blocked.write_bytes(b'block')
            with self.assertRaises(OSError):
                variant.commit({a:b'new', blocked/'b':b'new'}, root/'backup')
            self.assertEqual(a.read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
