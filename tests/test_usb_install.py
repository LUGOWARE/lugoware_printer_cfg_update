import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'maintenance/usb'
spec = importlib.util.spec_from_file_location('usb_check', SOURCE / 'check_install.py')
usb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb)


class UsbInstallTests(unittest.TestCase):
    def test_missing_stale_and_matching_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(usb.current(SOURCE, root))
            for name, dest in usb.FILES.items():
                target = root / dest.lstrip('/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((SOURCE / name).read_bytes())
            self.assertTrue(usb.current(SOURCE, root))
            legacy = root / 'etc/udev/rules.d/15-udev.rules'
            legacy.write_text('# old usb-mount@ rule\n')
            self.assertTrue(usb.current(SOURCE, root))
            legacy.write_text('RUN+="systemctl start usb-mount@%k.service"\n')
            self.assertFalse(usb.current(SOURCE, root))
            legacy.unlink()
            (root / 'boot/scripts/usb_udev.sh').write_text('old handler')
            self.assertFalse(usb.current(SOURCE, root))

    def test_mainsail_does_not_request_new_root_permission(self):
        source = (ROOT / 'install.sh').read_text(encoding='utf-8')
        self.assertIn('if (( SYSTEM_ONLY )); then\n    python3 "$COMMON_REPO/maintenance/usb/check_install.py"\nelse\n    sudo bash "$COMMON_REPO/maintenance/usb/install.sh" "$BACKUP_DIR/usb"\nfi', source)
