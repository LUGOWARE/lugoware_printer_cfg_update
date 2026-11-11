"""Install explicit-model, user-started diagnostics; never run physical tests."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil

LEGACY = {'gcode_macro '+n for n in ('_HEATER_TEST_STATE','HEATER_TEST','HEATER_TEST_OFF','HEATER_TEST_POPUP_CLOSE')}
LEGACY |= {'delayed_gcode '+n for n in ('heater_test_stage1','heater_test_start2','heater_test_stage2')}
SAVED = '#*# <---------------------- SAVE_CONFIG ---------------------->'

def strip_legacy(text):
    body,mark,tail=text.partition(SAVED)
    body=re.sub(r'(?ms)^\[([^]\n]+)\][^\n]*\n.*?(?=^\[|\Z)',
                lambda m:'' if m[1].strip() in LEGACY else m[0],body)
    return body+mark+tail

def screen_menu(text):
    marker='#~# --- Do not edit below this line. This section is auto generated --- #~#'
    body,sep,tail=text.partition(marker)
    body=re.sub(r'(?ms)^\[menu __main more diagnostics\][^\n]*\n.*?(?=^\[|\Z)','',body)
    def hide(m):
        block=re.sub(r'(?m)^enable\s*[:=].*\n?','',m[0])
        first,rest=block.split('\n',1)
        return first+'\nenable: False\n'+rest
    body=re.sub(r'(?ms)^\[menu __main more heater_test\][^\n]*\n.*?(?=^\[|\Z)',hide,body)
    body=body.rstrip()+"\n\n[menu __main more diagnostics]\nname: {{ _('Diagnostics') }}\nicon: diagnostics-check\npanel: diagnostics\n\n"
    return body+sep+tail

def header(text,model):
    if model not in ('M','L','W'):raise ValueError('Explicit M/L/W diagnostic model required')
    body,mark,tail=text.partition(SAVED)
    block='[lugo_diagnostics]\nmodel: '+model+'\nxy_speed: 200\nz_speed: 5\n\n'
    pattern=r'(?ms)^\[lugo_diagnostics\][^\n]*\n.*?(?=^\[|\Z)'
    if re.search(pattern,body):body=re.sub(pattern,lambda m:block,body)
    else:body=body.rstrip()+'\n\n'+block
    return body+mark+tail

def install(config,screen,klipper,backup,model):
    assets=Path(__file__).with_name('diagnostics')
    changes={screen/'panels/diagnostics.py':(assets/'diagnostics.py').read_text(encoding='utf-8'),
             klipper/'klippy/extras/lugo_diagnostics.py':(assets/'lugo_diagnostics.py').read_text(encoding='utf-8'),
             klipper/'klippy/extras/lugo_factory_qc.py':(assets/'lugo_factory_qc.py').read_text(encoding='utf-8')}
    p=config/'printer_base.cfg';changes[p]=strip_legacy(p.read_text(encoding='utf-8'))
    p=config/'printer.cfg';changes[p]=header(strip_legacy(p.read_text(encoding='utf-8')),model)
    p=config/'KlipperScreen.conf';changes[p]=screen_menu(p.read_text(encoding='utf-8'))
    for lang,entries in json.loads((assets/'locales.json').read_text(encoding='utf-8')).items():
        p=screen/'ks_includes/lugoware_locales'/(lang+'.json')
        data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        data.update(entries);changes[p]=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    styles={screen/'styles/material-darker/images',screen/'styles/material/images'}
    styles.update(p/'images' for p in (screen/'styles').glob('*') if (p/'images').is_dir())
    for folder in styles:changes[folder/'diagnostics-check.svg']=(assets/'diagnostics-check.svg').read_text(encoding='utf-8')
    for p,text in changes.items():
        if p.suffix=='.py':ast.parse(text)
    for p,text in changes.items():
        if p.exists() and p.read_text(encoding='utf-8')==text:continue
        # Keep hierarchy across config / screen / Klipper backup roots.
        group,root=next((g,r) for g,r in [('config',config),('screen',screen),('klipper',klipper)] if p.is_relative_to(r))
        saved=backup/group/p.relative_to(root);saved.parent.mkdir(parents=True,exist_ok=True)
        if p.exists() and not saved.exists():shutil.copy2(p,saved)
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    print('Installed diagnostics for FLEX4 '+model+'; no motion or heating started.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=['M','L','W']);args=parser.parse_args()
    home=Path.home()
    install(home/'printer_data/config',Path(os.environ.get('KLIPPERSCREEN_DIR',home/'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR',home/'klipper')),Path(os.environ['BACKUP_DIR'])/'diagnostics',args.model)
