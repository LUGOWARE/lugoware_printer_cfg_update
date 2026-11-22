"""Preserve an already installed auxiliary paused-tool service across updates."""
import re

SUBSCRIPTION = '                "paused_tool_service": None,\n'
CANCEL_GUARD = (
    "        service = self.printer.lookup_object('paused_tool_service', None)\n"
    "        if service is not None and service.motion_locked():\n"
)
TEMP_GUARD = (
    "        if name in ('M104', 'M109') and not self.depth:\n"
    "            service = self.printer.lookup_object('paused_tool_service', None)\n"
    "            if service is not None and service.service_attached():\n"
    "                return service.manual_heat(cmd, self.original[name])\n"
)
RESUME_IF = '{% if printer.paused_tool_service.blocks_resume %}'
RESUME_ERROR = '{action_raise_error("Park the service tool before resuming.")}'
DOCK_IF = "{% if printer.fast_cancel.phase == 'dock_sensor_hold' %}"
DOCK_ELIF = DOCK_IF.replace(' if ', ' elif ')


def installed(home):
    return all((home / path).is_file() for path in (
        'klipper/klippy/extras/paused_tool_service.py',
        'KlipperScreen/panels/paused_tool_service.py',
    ))


def add_subscription(text):
    return insert(text, '                "fast_cancel": None,\n', SUBSCRIPTION)


def insert(text, anchor, addition):
    if addition in text:
        return text
    if text.count(anchor) != 1:
        raise ValueError('Missing paused-tool service anchor: ' + anchor.strip())
    return text.replace(anchor, anchor + addition, 1)


def strip_config(text):
    guard = (r'(?m)^([ \t]*)' + re.escape(RESUME_IF) + r'\n[ \t]+'
             + re.escape(RESUME_ERROR) + r'\n[ \t]*' + re.escape(DOCK_ELIF))
    text = re.sub(guard, lambda m: m[1] + DOCK_IF, text)
    return re.sub(r'(?m)^\[paused_tool_service\][ \t]*\n(?:[ \t]*\n)*', '', text)


def configure(text):
    guard = r'(?m)^([ \t]*)' + re.escape(DOCK_IF) + r'$'
    text, count = re.subn(guard, lambda m: '\n'.join(
        (m[1] + RESUME_IF, m[1] + '  ' + RESUME_ERROR, m[1] + DOCK_ELIF)), text)
    if count != 1:
        raise ValueError('Missing auxiliary RESUME guard for paused-tool service')
    return text.rstrip() + '\n\n[paused_tool_service]\n'


def menu(text, enabled):
    section = 'menu __print paused_tool_service'
    # KlipperScreen replaces its generated trailer when saving settings.
    marker = '#~# --- Do not edit below this line. This section is auto generated --- #~#'
    body, separator, saved = text.partition(marker)
    pattern = r'(?ms)^\[' + section + r'\][^\n]*\n.*?(?=^\[|^#~#|\Z)'
    body = re.sub(pattern, '', body)
    saved = re.sub(pattern, '', saved)  # Migrate releases that appended the menu below the marker.
    if not enabled:
        return body + separator + saved
    menu_text = (
        '[menu __print paused_tool_service]\n'
        'name: 툴 가져오기\n'
        'icon: extruder\n'
        'panel: paused_tool_service\n'
        "enable: {{ printer.pause_resume.is_paused and 'paused_tool_service' in printer.config_sections }}\n\n"
    )
    anchor = '[menu __print temperature]\n'
    if anchor in body:
        body = body.replace(anchor, menu_text + anchor, 1)
    else:
        body = body.rstrip() + '\n\n' + menu_text
    return body + separator + saved


def hooks(text, path, enabled):
    if path == 'KlipperScreen/screen.py':
        text = text.replace(SUBSCRIPTION, '')
        return add_subscription(text) if enabled else text
    if path == 'klipper/klippy/extras/lugo_tool_temperature.py':
        text = text.replace(TEMP_GUARD, '')
        return insert(text, '    def dispatch(self, name, cmd):\n', TEMP_GUARD) if enabled else text
    if path == 'klipper/klippy/extras/fast_cancel.py':
        for arg in ('request', 'cmd'):
            name = 'request' if arg == 'request' else 'cmd_cancel'
            guard = CANCEL_GUARD + "            raise %s.error('정비용 툴을 먼저 파킹해 주세요.')\n" % arg
            text = text.replace(guard, '')
            if enabled:
                text = insert(text, '    def %s(self, %s):\n' % (name, arg), guard)
    return text
