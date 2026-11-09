"""Install recovery and factory tooling; never reset data or start recovery."""
from pathlib import Path
import ast
import json
import os
import re
import shutil


def patch_ui(source, name, assets):
    for old, new in json.loads((assets/'ui_patches.json').read_text(encoding='utf-8'))[name]:
        if new in source:
            continue
        if source.count(old) != 1:
            raise ValueError('Unsupported recovery UI anchor: '+name+' '+old[:80])
        source=source.replace(old,new,1)
    compile(source,name,'exec')
    return source


def header(source):
    if re.search(r'^\[lugo_recovery\]\s*(?:#.*)?$',source,re.M):
        return source
    marker='#*# <---------------------- SAVE_CONFIG ---------------------->'
    block='\n[lugo_recovery]\n\n'
    if marker in source:return source.replace(marker,block+marker,1)
    return source.rstrip()+'\n'+block


def install(home, screen, klipper, backup, assets=None):
    home,screen,klipper,backup=map(Path,(home,screen,klipper,backup))
    assets=Path(assets) if assets else Path(__file__).with_name('recovery')
    changes={}
    for name in ('lugo_recovery','recovery_execution','recovery_index','recovery_objects','recovery_eta'):
        changes[klipper/'klippy/extras'/(name+'.py')]=(assets/(name+'.py')).read_bytes()
    for name in ('recovery','recovery_progress','first_run'):
        changes[screen/'panels'/(name+'.py')]=(assets/(name+'.py')).read_bytes()
    for name in ('recovery_files','recovery_notice','recovery_eta_ui','first_run_state'):
        changes[screen/'ks_includes'/(name+'.py')]=(assets/(name+'.py')).read_bytes()
    for name,relative in [('screen.py','screen.py'),('gcodes.py','panels/gcodes.py'),('job_status.py','panels/job_status.py')]:
        path=screen/relative
        changes[path]=patch_ui(path.read_text(encoding='utf-8'),name,assets).encode('utf-8')
    path=home/'printer_data/config/printer.cfg'
    changes[path]=header(path.read_text(encoding='utf-8')).encode('utf-8')
    path=home/'printer_data/config/KlipperScreen.conf'
    if path.exists():
        source=path.read_text(encoding='utf-8')
        # Recovery is reached only from the interrupted file's badge.
        source=re.sub(r'(?ms)^\[menu __main more recovery\][^\n]*\n.*?(?=^\[|^#~#|\Z)',
                      '[menu __main more recovery]\nenable: False\n\n',source)
        changes[path]=source.encode('utf-8')
    path=home/'.local/share/lugoware/factory_reset.py'
    changes[path]=(assets/'factory_reset.py').read_bytes()
    wrapper=home/'lugoware-factory-reset'
    changes[wrapper]=b'#!/bin/sh\nexec python3 "$HOME/.local/share/lugoware/factory_reset.py" "$@"\n'
    mainsail=home/'mainsail'
    if (mainsail/'index.html').exists():
        changes[mainsail/'lugoware-recovery-eta.js']=(assets/'lugoware-recovery-eta.js').read_bytes()
        source=(mainsail/'index.html').read_text(encoding='utf-8')
        if 'lugoware-recovery-eta.js' not in source:
            if '</body>' not in source:raise ValueError('Unsupported Mainsail index.html')
            source=source.replace('</body>','<script src="./lugoware-recovery-eta.js?v=20261109"></script></body>')
        changes[mainsail/'index.html']=source.encode('utf-8')
    # Validate everything before any writes. No journal, wizard state or user data is modified.
    for path,data in changes.items():
        if path.suffix=='.py':ast.parse(data,filename=str(path))
    for path,data in changes.items():
        if path.exists() and path.read_bytes()==data:continue
        saved=backup/path.relative_to(home)
        if path.exists() and not saved.exists():
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    wrapper.chmod(0o700)
    print('Installed interrupted-print recovery and factory tools. Existing data and first-run state preserved.')


if __name__=='__main__':
    import subprocess
    privacy_assets=Path(__file__).with_name('recovery')
    helper=Path('/usr/local/libexec/lugoware-factory-privacy')
    if not helper.exists() or helper.read_bytes()!=(privacy_assets/'factory_privacy.py').read_bytes():
        if os.environ.get('LUGOWARE_SYSTEM_ONLY')=='1':
            print('[출고 초기화] Wi-Fi/시스템 로그 정리 권한은 최신 SSH 설치 명령을 한 번 실행해야 적용됩니다. / Factory privacy cleanup requires one SSH installer run.')
        else:
            subprocess.run(['sudo','-n','python3',str(privacy_assets/'install_factory_privacy.py')],check=True)
    home=Path.home()
    install(home,Path(os.environ.get('KLIPPERSCREEN_DIR',home/'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR',home/'klipper')),
            Path(os.environ['BACKUP_DIR'])/'recovery-factory')
