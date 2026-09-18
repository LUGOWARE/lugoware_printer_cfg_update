"""Copy and checksum a new production binary; does not publish to GitHub."""
import hashlib
from pathlib import Path
import sys
from verify_firmware import inspect

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r'C:\Users\nns30\screen\LugoWare Cfg Update\firmware.bin')
data = source.read_bytes()
identity = inspect(data)
folder = Path(__file__).resolve().parents[1] / 'firmware'
folder.mkdir(exist_ok=True)
(folder / 'firmware.bin').write_bytes(data)
(folder / 'firmware.sha256').write_text(
    hashlib.sha256(data).hexdigest() + '  firmware.bin\n', encoding='ascii')
print('Prepared: ' + identity['version'])
print('Commit and push firmware/ to main to publish this version.')
