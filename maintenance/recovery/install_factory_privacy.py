"""Install fixed-scope root helper; does NOT perform any cleanup."""
import ast
import os
from pathlib import Path
import subprocess

def install():
    if os.geteuid() != 0:
        raise RuntimeError('Run installer with sudo')
    source = Path(__file__).with_name('factory_privacy.py').read_bytes()
    ast.parse(source)
    folder = Path('/usr/local/libexec')
    if folder.is_symlink():
        raise RuntimeError('Unexpected libexec symlink')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'lugoware-factory-privacy'
    temp = folder/'lugoware-factory-privacy.new'
    temp.unlink(missing_ok=True)
    with temp.open('xb') as f:
        f.write(source)
    os.chown(temp,0,0);temp.chmod(0o755);temp.replace(target)
    rules = Path('/etc/sudoers.d/lugoware-factory-privacy')
    draft = Path('/etc/sudoers.d/.lugoware-factory-privacy.new')
    draft.unlink(missing_ok=True)
    text = 'biqu ALL=(root) NOPASSWD: ' + ', '.join(
        str(target)+' '+action for action in ('--check','--clean','--schedule'))+'\n'
    with draft.open('x') as f:f.write(text)
    os.chown(draft,0,0);draft.chmod(0o440)
    subprocess.run(['/usr/sbin/visudo','-cf',str(draft)],check=True)
    draft.replace(rules)
    print('Factory privacy helper installed; no data deleted.')

if __name__ == '__main__':install()
