"""Install the M5P print controls without restarting or moving the printer."""
import argparse
import os
from pathlib import Path
import re
import shutil
from patch_print_controls import macros, prepare_macros


def replace_once(text, old, new):
    if new in text:
        return text
    if text.count(old) != 1:
        raise ValueError('Unsupported print controls source: ' + old)
    return text.replace(old, new, 1)


def panel_patch(text):
    if 'def _fast_cancel_response(' not in text:
        text = replace_once(text, '        self._screen._ws.api.print_cancel()', '''        self._screen._lugo_cancel_pending = True
        sent = self._screen._ws.send_method(
            "printer.lugo_fast_cancel.request", {}, self._fast_cancel_response)
        if sent is False:
            self._fast_cancel_response({"error": {"message": "Cancel request failed"}})

    def _fast_cancel_response(self, response, *args):
        if "error" in response:
            self._screen._lugo_cancel_pending = False
            self.enable_button("cancel")
            self._screen.show_popup_message(str(response["error"].get("message", "Cancel failed")))
''')
    if '_lugo_cancel_pending' not in text:
        raise ValueError('Incomplete cancellation panel patch')
    return text


MHZ_PATTERN = r"(?i)(?:Klipper:\s*)?(?://\s*)?MCU '[^'\n]+' configured for \d+(?:\.\d+)?MHz but running at \d+(?:\.\d+)?MHz!"


def screen_patch(text):
    text = replace_once(text, '    def state_paused(self):\n        self.state_printing()\n',
                        '    def state_paused(self):\n        self.state_printing()\n        if getattr(self, "_lugo_cancel_pending", False):\n            return\n')
    text = replace_once(text, '    def state_ready(self, wait=True):\n',
                        '    def state_ready(self, wait=True):\n        self._lugo_cancel_pending = False\n')
    marker = '        # LUGO: suppress only MCU clock mismatch popups.'
    if marker in text:
        # Upgrade the original case-sensitive filter on already-patched screens.
        text = text.replace(repr(MHZ_PATTERN[4:]), repr(MHZ_PATTERN))
        if repr(MHZ_PATTERN) not in text:
            raise ValueError('Unrecognized existing MCU clock popup filter')
    if marker not in text:
        anchor = '    def show_popup_message(self, message, level=3, from_ws=False):\n'
        text = replace_once(text, anchor, anchor + marker + '\n        import re\n'
                            + f'        if re.fullmatch({MHZ_PATTERN!r}, " ".join(str(message).split())):\n'
                            + '            logging.info("Suppressed MCU clock popup: %s", message)\n            return\n')
    return text


def config_patch(text):
    if re.search(r'^\[lugo_fast_cancel\]\s*$', text, re.M):
        return text
    marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
    if marker in text:
        return text.replace(marker, '[lugo_fast_cancel]\n\n' + marker, 1)
    return text.rstrip() + '\n\n[lugo_fast_cancel]\n'


def install(config, screen, klipper, backup, config_only=False):
    changes = {config/'printer_base.cfg': macros(prepare_macros((config/'printer_base.cfg').read_text(encoding='utf-8'))),
               config/'printer.cfg': config_patch((config/'printer.cfg').read_text(encoding='utf-8'))}
    if not config_only:
        probe = (klipper/'klippy/extras/probe.py').read_text(encoding='utf-8')
        mesh = (klipper/'klippy/extras/bed_mesh.py').read_text(encoding='utf-8')
        for needle in ('class SampleAveragingHelper:', 'def _probe(self, gcmd):', 'self.hw_probe_session', 'def _invoke_callback(self, results):'):
            if needle not in probe:
                raise ValueError('Unsupported probe API: ' + needle)
        if 'self.probe_mgr = ProbeManager(' not in mesh:
            raise ValueError('Unsupported bed mesh API')
        changes.update({screen/'screen.py': screen_patch((screen/'screen.py').read_text(encoding='utf-8')),
                        screen/'panels/job_status.py': panel_patch((screen/'panels/job_status.py').read_text(encoding='utf-8')),
                        klipper/'klippy/extras/lugo_fast_cancel.py': Path(__file__).with_name('lugo_fast_cancel.py').read_text(encoding='utf-8')})
    for path, text in changes.items():
        if path.suffix == '.py':
            compile(text, str(path), 'exec')
    for path, text in changes.items():
        if path.exists() and path.read_text(encoding='utf-8') == text:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        if path.exists() and not (backup/path.name).exists():
            shutil.copy2(path, backup/path.name)
        path.write_text(text, encoding='utf-8')
    print('[확인 완료] 준비 툴 이동 확인 / 빠른 정상 취소·메쉬 취소 / MHz 팝업 숨김')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-only', action='store_true')
    args = parser.parse_args()
    home = Path.home()
    install(home/'printer_data/config', Path(os.environ.get('KLIPPERSCREEN_DIR', home/'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR', home/'klipper')),
            Path(os.environ.get('BACKUP_DIR', home/'lugoware_backups/print-controls'))/'print-controls', args.config_only)
