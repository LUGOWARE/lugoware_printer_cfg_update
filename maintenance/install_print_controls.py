"""Install the M5P print controls without restarting or moving the printer."""
import argparse
import os
from pathlib import Path
import re
import shutil
from patch_print_controls import macros
from final_print_ui import job_status, notification, popup, temperature


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
            "printer.fast_cancel.request", {}, self._fast_cancel_response)
        if sent is False:
            self._fast_cancel_response({"error": {"message": _("Cancel request failed")}})

    def _fast_cancel_response(self, response, *args):
        if "error" in response:
            self._screen._lugo_cancel_pending = False
            self.enable_button("cancel")
            self._screen.show_popup_message(str(response["error"].get("message", _("Cancel failed"))))
''')
    text = text.replace('"message": "Cancel request failed"', '"message": _("Cancel request failed")')
    text = text.replace('get("message", "Cancel failed")', 'get("message", _("Cancel failed"))')
    if '_lugo_cancel_pending' not in text:
        raise ValueError('Incomplete cancellation panel patch')
    return text.replace("printer.lugo_fast_cancel.request", "printer.fast_cancel.request")


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
    text = re.sub(r'^\[lugo_fast_cancel\]\s*$', '[fast_cancel]', text, flags=re.M)
    headers = list(re.finditer(r'^\[fast_cancel\]\s*$', text, re.M))
    if len(headers) > 1:
        raise ValueError('Duplicate fast_cancel sections; inspect printer.cfg')
    if headers:
        return text
    marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
    if marker in text:
        return text.replace(marker, '[fast_cancel]\n\n' + marker, 1)
    return text.rstrip() + '\n\n[fast_cancel]\n'


def install(config, screen, klipper, backup, config_only=False):
    changes = {config/'printer.cfg': config_patch((config/'printer.cfg').read_text(encoding='utf-8'))}
    if os.environ.get('LUGOWARE_SYSTEM_ONLY') != '1':
        changes[config/'printer_base.cfg'] = macros((config/'printer_base.cfg').read_text(encoding='utf-8'))
    if not config_only:
        probe = (klipper/'klippy/extras/probe.py').read_text(encoding='utf-8')
        mesh = (klipper/'klippy/extras/bed_mesh.py').read_text(encoding='utf-8')
        for needle in ('class SampleAveragingHelper:', 'def _probe(self, gcmd):', 'self.hw_probe_session', 'def _invoke_callback(self, results):'):
            if needle not in probe:
                raise ValueError('Unsupported probe API: ' + needle)
        if 'self.probe_mgr = ProbeManager(' not in mesh:
            raise ValueError('Unsupported bed mesh API')
        changes[screen/'panels/temperature.py'] = temperature((screen/'panels/temperature.py').read_text(encoding='utf-8'))
        changes.update({screen/'screen.py': popup(screen_patch((screen/'screen.py').read_text(encoding='utf-8'))),
                        screen/'panels/job_status.py': job_status(panel_patch((screen/'panels/job_status.py').read_text(encoding='utf-8'))),
                        screen/'ks_includes/notification_handler.py': notification((screen/'ks_includes/notification_handler.py').read_text(encoding='utf-8')),
                        klipper/'klippy/extras/fast_cancel.py': Path(__file__).with_name('fast_cancel.py').read_text(encoding='utf-8')})
    if os.environ.get('LUGOWARE_SYSTEM_ONLY') == '1':
        changes.pop(config / 'printer_base.cfg', None)
        changes.pop(config / 'KlipperScreen.conf', None)
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
