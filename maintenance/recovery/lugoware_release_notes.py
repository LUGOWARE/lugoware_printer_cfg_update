"""Customer-authored notes pinned to the exact revision reported by Moonraker."""
import json
from pathlib import Path
import re
import subprocess

CHANNELS = frozenset(('lugoware_config', 'lugoware_system'))
MAX_BYTES = 65536

def parse_notes(raw, channel, language):
    if channel not in CHANNELS or len(raw) > MAX_BYTES:
        return None
    try:
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get('schema') != 1:
            return None
        entry = document.get(channel)
        if not isinstance(entry, dict):
            return None
        version = entry.get('version', '')
        date = entry.get('date', '')
        notes = entry.get('notes', {})
        if not isinstance(version, str) or not isinstance(date, str) or not isinstance(notes, dict):
            return None
        language = language.replace('-', '_')
        choices = (language, language.split('_')[0], 'en', 'ko')
        lines = next((notes[key] for key in choices if notes.get(key)), [])
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            return None
        body = '\n'.join('• ' + line.strip() for line in lines if line.strip())
        if not body:
            return None
        if date:
            body = date + '\n\n' + body
        return {'version': version, 'body': body}
    except (ValueError, UnicodeError, TypeError):
        return None

def read_notes(home, channel, revision, language):
    if channel not in CHANNELS or not isinstance(revision, str) or not re.fullmatch(r'[0-9a-fA-F]{40,64}', revision):
        return None
    repo = Path(home)/channel
    git = ['git', '--no-pager', '-C', str(repo)]
    obj = revision + ':release_notes.json'
    try:
        size = subprocess.run(git + ['cat-file', '-s', obj], capture_output=True,
                              text=True, timeout=4)
        if size.returncode or not 0 < int(size.stdout.strip()) <= MAX_BYTES:
            return None
        result = subprocess.run(git + ['show', obj], capture_output=True, timeout=4)
        if result.returncode:
            return None
        return parse_notes(result.stdout, channel, language)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
