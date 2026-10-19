"""Tested October print UI and mesh recovery integration; preserve board settings."""
import json
import re
from pathlib import Path


def job(text, reverse=False):
    patches = json.loads(Path(__file__).with_name('print_features').joinpath('october_ui.json').read_text(encoding='utf-8'))
    for old, new in (reversed(patches) if reverse else patches):
        if reverse:
            if new in text:
                text = text.replace(new, old, 1)
        elif new not in text:
            if text.count(old) != 1:
                raise ValueError('Unsupported October UI anchor: ' + old[:120])
            text = text.replace(old, new, 1)
    return text


def insert(text, anchor, block):
    if block in text:
        return text
    if text.count(anchor) != 1:
        raise ValueError('Unsupported UI anchor: ' + anchor)
    return text.replace(anchor, anchor + block, 1)


def notification(text):
    for line in ('from time import monotonic', 'from gi.repository import GLib'):
        if line not in text:
            text = line + '\n' + text
    return insert(text, NOTIFICATION_ANCHOR, NOTIFICATION_BLOCK)


def popup(text):
    return insert(text, POPUP_ANCHOR, POPUP_BLOCK)


def config(text):
    # Restrict edits to preparation macros; never touch toolchange travel/pins.
    for prefix in ('DOCK_', 'PARK_'):
        for i in range(4):
            pattern = r'(?ms)^\[gcode_macro ' + prefix + str(i) + r'\]\n.*?(?=^\[|\Z)'
            match = re.search(pattern, text)
            if not match:
                continue
            block = match[0]
            guard = '{% if "x" not in printer.toolhead.homed_axes or "y" not in printer.toolhead.homed_axes or "z" not in printer.toolhead.homed_axes %}'
            if guard in block:
                continue
            move = re.search(r'(?m)^([ \t]*)G1 Z20 F1000$', block)
            if not move:
                raise ValueError('Unsupported preparation Z move: ' + prefix + str(i))
            indent = move[1]
            replacement = indent + guard + '\n' + indent + '    G1 Z20 F1000\n' + indent + '{% endif %}'
            block = block[:move.start()] + replacement + block[move.end():]
            text = text[:match.start()] + block + text[match.end():]
    for i in range(4):
        pattern = r'(?ms)^\[gcode_macro DOCK_TOOL_' + str(i) + r'\]\n.*?(?=^\[|\Z)'
        match = re.search(pattern, text)
        if match:
            block = match[0].replace('MSG="DOCKING T' + str(i) + '."', 'MSG="DOCKING T' + str(i+1) + '."')
            text = text[:match.start()] + block + text[match.end():]
    if '[gcode_macro SCREEN_LOWER_BED_10]' not in text:
        text = text.rstrip() + '\n' + LOWER_BED
    return text

NOTIFICATION_ANCHOR = '    def _gcode_response(self, data):\n'
NOTIFICATION_BLOCK = '        # Keep the second retry visible for at least two seconds, without\n        # delaying Klipper motion or closing a newer/unrelated notification.\n        if re.fullmatch(r"echo: Probe measurement error - redeploying probe \\([12]/2\\)", data.strip()):\n            self._screen.show_popup_message(data.strip()[6:], 1)\n            self._probe_recovery_popup = self._screen.popup_message\n            self._probe_recovery_until = monotonic() + (2.0 if data.strip().endswith("(2/2)") else 0.0)\n            return True\n        if data.strip() == "// PROBE_RECOVERY_SAMPLING":\n            popup = getattr(self, "_probe_recovery_popup", None)\n            if popup is not None:\n                def close_recovery():\n                    if getattr(self, "_probe_recovery_popup", None) is popup:\n                        if self._screen.popup_message is popup:\n                            self._screen.close_popup_message()\n                        self._probe_recovery_popup = None\n                    return False\n                remaining = getattr(self, "_probe_recovery_until", 0.0) - monotonic()\n                if remaining > 0:\n                    GLib.timeout_add(int(remaining * 1000) + 1, close_recovery)\n                else:\n                    close_recovery()\n            return True\n\n'
POPUP_ANCHOR = '    def show_popup_message(self, message, level=3, from_ws=False):\n'
POPUP_BLOCK = '        # Each bounded probe retry must update the popup, even within one second.\n        import re\n        if re.fullmatch(r"Probe measurement error - redeploying probe \\([12]/2\\)", str(message).strip()):\n            from_ws = False\n        # Counts remain visible in job status and the G-code console.\n        import re\n        if re.fullmatch(r"(?:echo:\\s*|//\\s*)?Toolchange\\s+\\d+(?:/\\d+)?", str(message).strip()):\n            return\n'
LOWER_BED = "\n[gcode_macro SCREEN_LOWER_BED_10]\ndescription: Lower the bed by up to 10 mm after a print\ngcode:\n    {% if printer.print_stats.state in ['printing', 'paused'] %}\n        {action_raise_error('Movement is unavailable during a print.')}\n    {% elif 'z' not in printer.toolhead.homed_axes %}\n        {action_raise_error('Must home axis first: Z')}\n    {% else %}\n        {% set distance = [10.0, printer.toolhead.axis_maximum.z|float - printer.toolhead.position.z|float]|min %}\n        {% if distance > 0 %}\n            SAVE_GCODE_STATE NAME=SCREEN_LOWER_BED_STATE\n            G91\n            G1 Z{distance} F600\n            RESTORE_GCODE_STATE NAME=SCREEN_LOWER_BED_STATE\n        {% endif %}\n    {% endif %}\n"
