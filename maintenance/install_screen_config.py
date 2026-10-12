"""Merge managed menus without overwriting the user's language or saved settings."""
import argparse
from pathlib import Path
import re
import shutil

TITLES = {
    'menu __main more print_status': 'Print Status',
    'menu __main prepare_preview': 'Prepare',
    'menu __main more heater_test': 'Nozzle heater test',
    'menu __main more heater_test auto_test': 'Automatic heater test',
    'menu __main more heater_test heater_off': 'Stop heater test',
    'menu __print temperature': 'Tool temperature control',
}
SAVED = '#~# --- Do not edit below this line. This section is auto generated --- #~#'


def blocks(text):
    return list(re.finditer(r'(?ms)^\[([^\]\n]+)\][^\n]*\n.*?(?=^\[|\Z)', text))


def merge(existing, template):
    body, marker, saved = existing.partition(SAVED)
    template = template.partition(SAVED)[0]
    for match in blocks(template):
        section = match[1]
        # Language/main/printer connection options always belong to the user.
        if not (section.startswith('menu ') or section.startswith('preheat ')):
            continue
        pattern = r'(?ms)^\['+re.escape(section)+r'\][^\n]*\n.*?(?=^\[|\Z)'
        replacement = match[0].rstrip()+'\n\n'
        if re.search(pattern, body):
            body = re.sub(pattern, lambda m: replacement, body)
        else:
            body = body.rstrip()+'\n\n'+replacement
    # First installation: keep printer defaults, discard template language choice.
    if not existing.strip():
        prefix = ''.join(m[0] for m in blocks(template) if m[1].startswith('printer '))
        body = prefix + body.lstrip()
    for section, title in TITLES.items():
        pattern = r'(?ms)^\['+re.escape(section)+r'\][^\n]*\n.*?(?=^\[|\Z)'
        match = re.search(pattern,body)
        if not match:
            continue
        value = "name: {{ _('"+title+"') }}"
        block = match[0]
        block = re.sub(r'(?m)^\s*name\s*[:=].*$',lambda m:value,block) if re.search(r'(?m)^\s*name\s*[:=]',block) else block.rstrip()+'\n'+value+'\n\n'
        body=body[:match.start()]+block+body[match.end():]
    return body + marker + saved


def install(template, target, backup):
    previous = target.read_text(encoding='utf-8') if target.exists() else ''
    updated = merge(previous, template.read_text(encoding='utf-8'))
    if previous == updated:
        print('[건너뜀] KlipperScreen 설정: 동일함 / 선택 언어 유지')
        return
    backup.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and not backup.exists():
        shutil.copy2(target,backup)
    target.write_text(updated,encoding='utf-8')
    print('[완료] 다국어 메뉴 설정 / 기존 언어·사용자 저장 설정 유지')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('template',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('backup',type=Path)
    args=parser.parse_args()
    install(args.template,args.target,args.backup)
