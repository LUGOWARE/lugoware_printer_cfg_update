"""Display only the scheduled screen restart notice; never issue printer commands."""
import json
import math
import time
from pathlib import Path
from gi.repository import GLib


def phase(deadline, now):
    left = deadline - now
    if 50 < left <= 60:
        return 'notice', 60
    if 0 < left <= 5:
        return 'countdown', math.ceil(left)
    return None


def install(screen):
    path = Path('/run/lugoware-screen-restart/notice.json')
    state = {'key': None, 'popup': None}

    def tick():
        try:
            data = json.loads(path.read_text())
            deadline = float(data['deadline'])
            current = phase(deadline, time.time())
        except (OSError, ValueError, KeyError, TypeError):
            current = None
            deadline = None
        key = (deadline, current)
        if key == state['key']:
            return True
        state['key'] = key
        if current is None:
            if state['popup'] is not None and screen.popup_message is state['popup']:
                screen.close_popup_message()
            state['popup'] = None
            return True
        from ks_includes.lugo_i18n import translate_text
        if current[0] == 'notice':
            message = translate_text('Screen restarts in one minute.')
        else:
            message = translate_text('Screen restart countdown: {seconds}').format(seconds=current[1])
        screen.show_popup_message(message, 1)
        state['popup'] = screen.popup_message
        return True

    GLib.timeout_add(100, tick)
