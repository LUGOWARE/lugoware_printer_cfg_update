"""Install offline UI catalogs and bind them to KlipperScreen language changes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import re


def insert(text, anchor, replacement):
    if replacement in text:
        return text
    if text.count(anchor)!=1:
        raise ValueError('Unsupported KlipperScreen i18n anchor: '+anchor)
    return text.replace(anchor,replacement,1)


def patch_config(text):
    anchor='        self.lang = self.langs[lang]\n'
    return insert(text,anchor,anchor+'        from ks_includes.lugo_i18n import with_translations\n        self.lang = with_translations(self.lang, lang)\n')


def patch_screen(text):
    if '        message = translate_text(message)\n' in text:
        return text
    anchor='    def show_popup_message(self, message, level=3, from_ws=False):\n'
    return insert(text,anchor,anchor+'        from ks_includes.lugo_i18n import translate_text\n        message = translate_text(message)\n')


def patch_prompts(text):
    anchor='    def decode(self, data):\n'
    return insert(text,anchor,anchor+'        from ks_includes.lugo_i18n import translate_prompt\n        data = translate_prompt(data)\n')


def patch_temperature(text):
    if 'from ks_includes.lugo_i18n import preheat_label' not in text:
        text='from ks_includes.lugo_i18n import preheat_label\n'+text
    return insert(text,'label=option,','label=preheat_label(option),')


def patch_gtk(text):
    if 'from ks_includes.lugo_layout import format_button' in text:
        return text
    pattern = r'(?ms)^def format_label\(widget, lines=2\):\n.*?(?=^class KlippyGtk:)'
    replacement = ('def format_label(widget, lines=2):\n'
                   '    from ks_includes.lugo_layout import format_button\n'
                   '    format_button(widget, lines)\n\n\n')
    result, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError('Unsupported KlippyGtk label formatting')
    # Keep intentional line breaks in translations.
    return result.replace('label.replace("\\n", " ")', 'label')


def patch_title(text):
    anchor = '        self.control["time"] = Gtk.Label('
    old = ('        from ks_includes.lugo_layout import wrap_label\n'
           '        wrap_label(self.titlelbl, 20)\n\n')
    code = ('        from ks_includes.lugo_layout import fit_title\n'
            '        fit_title(self.titlelbl)\n\n')
    text = text.replace(old, code)
    if code in text:
        return text
    return insert(text, anchor, code+anchor)


def patch_network(text):
    anchor = '            self.labels["interface"] = Gtk.ComboBoxText()'
    replacement = ('            from ks_includes.lugo_interface_selector import InterfaceSelector\n'
                   '            self.labels["interface"] = InterfaceSelector()')
    return insert(text, anchor, replacement)


def install(screen, backup, check=False):
    root=Path(__file__).resolve().parents[1]
    pairs={'ks_includes/config.py':patch_config,'screen.py':patch_screen,
           'ks_includes/widgets/prompts.py':patch_prompts,'panels/temperature.py':patch_temperature,
           'ks_includes/KlippyGtk.py':patch_gtk,'panels/base_panel.py':patch_title,
           'panels/network.py':patch_network}
    changes={screen/name:fn((screen/name).read_text(encoding='utf-8')) for name,fn in pairs.items()}
    changes[screen/'ks_includes/lugo_i18n.py']=Path(__file__).with_name('lugo_i18n.py').read_text(encoding='utf-8')
    changes[screen/'ks_includes/lugo_layout.py']=Path(__file__).with_name('lugo_layout.py').read_text(encoding='utf-8')
    changes[screen/'ks_includes/lugo_interface_selector.py']=Path(__file__).with_name('lugo_interface_selector.py').read_text(encoding='utf-8')
    catalog_dir=root/'translations'
    for path in catalog_dir.glob('*.json'):
        text=path.read_text(encoding='utf-8'); json.loads(text)
        changes[screen/'ks_includes/lugoware_locales'/path.name]=text
    for path,text in changes.items():
        if path.suffix=='.py': compile(text,str(path),'exec')
    if check: return
    for path,text in changes.items():
        if path.exists() and path.read_text(encoding='utf-8')==text: continue
        saved=backup/path.relative_to(screen)
        if path.exists() and not saved.exists():
            saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,saved)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')
    print('[확인 완료] KlipperScreen 언어 설정 연동 / 오프라인 다국어 패널·메뉴·히터 테스트')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    home=Path.home()
    install(Path(os.environ.get('KLIPPERSCREEN_DIR',home/'KlipperScreen')),
            Path(os.environ.get('BACKUP_DIR',home/'lugoware_backups'))/'i18n',args.check)
