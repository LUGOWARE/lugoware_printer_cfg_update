"""Manual-test print temperature panel. One shared heater, four logical tools."""
import math
import logging
import time
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel



class TemperatureControl(Gtk.Box):
    _provider = None

    def __init__(self, gtk, callback, tool):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_hexpand(False)
        self.set_size_request(196, -1)
        self.get_style_context().add_class('lugo-temperature-control')
        provider = Gtk.CssProvider()
        provider.load_from_data(b'''
            .lugo-temperature-control { background-color: #242424; border-radius: 8px; }
            .lugo-temperature-control button { min-width: 0; min-height: 0;
                padding: 0; margin: 0; border: 1px solid #505050;
                border-radius: 7px; background-image: none; background-color: #303030; }
            .lugo-temperature-control button { box-shadow: none; text-shadow: none; transition: none; }
            .lugo-temperature-control button:active,
            .lugo-temperature-control button.lugo-tapped {
                background-color: #087da5; border-color: #66dcff; }
            .lugo-temperature-control button label { color: #ffffff; }
            .lugo-temperature-control:disabled { background-color: #1c1c1c; }
            .lugo-temperature-control:disabled label { color: #777777; }
            .lugo-temperature-control button:disabled { background-color: #202020; border-color: #303030; }
        ''')
        if TemperatureControl._provider is None:
            TemperatureControl._provider = provider
            Gtk.StyleContext.add_provider_for_screen(
                self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        up = gtk.Button(label='▲', style='color1')
        down = gtk.Button(label='▼', style='color1')
        for button in (up, down):
            button.set_hexpand(False)
            button.set_size_request(60, 42)
        up.connect('clicked', self.flash)
        down.connect('clicked', self.flash)
        up.connect('clicked', callback, tool, 1)
        down.connect('clicked', callback, tool, -1)
        self.value = Gtk.Label(label='—', hexpand=True)
        self.value.set_margin_start(10)
        self.value.set_margin_end(4)
        arrows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        arrows.set_hexpand(False)
        arrows.set_margin_top(6)
        arrows.set_margin_bottom(6)
        arrows.set_margin_end(6)
        arrows.set_homogeneous(True)
        arrows.pack_start(up, True, True, 0)
        arrows.pack_start(down, True, True, 0)
        self.pack_start(self.value, True, True, 0)
        self.pack_start(arrows, False, False, 0)

    def flash(self, button):
        previous = getattr(button, '_lugo_flash', None)
        if previous is not None:
            GLib.source_remove(previous)
        button.get_style_context().add_class('lugo-tapped')
        def clear():
            button.get_style_context().remove_class('lugo-tapped')
            button._lugo_flash = None
            return False
        button._lugo_flash = GLib.timeout_add(50, clear)

    def get_label(self):
        return self.value.get_text()

    def set_label(self, text):
        self.value.set_text(text)


class Panel(ScreenPanel):
    def __init__(self, screen, title, **kwargs):
        super().__init__(screen, title or '툴별 출력 온도')
        self.timer = None
        self.generation = 0
        self.pending = 0
        self.sending = False
        self.request_serial = 0
        self.sent_at = 0
        self.socket = None
        self.state = {}
        self.rows = []
        self.layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.layout.set_margin_start(4)
        self.layout.set_margin_end(4)
        self.status = Gtk.Label(label='프린터 상태 확인 중…')
        self.status.set_line_wrap(True)
        self.layout.pack_start(self.status, False, False, 0)
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, row_homogeneous=True)
        for tool in range(4):
            grid.attach(Gtk.Label(label=f'T{tool + 1}'), 0, tool, 1, 1)
            material = Gtk.Label(label='—', hexpand=True)
            material.set_line_wrap(True)
            material.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            material.set_max_width_chars(16)
            button = TemperatureControl(self._gtk, self.adjust_temperature, tool)
            button.set_sensitive(False)
            grid.attach(material, 1, tool, 1, 1)
            grid.attach(button, 2, tool, 1, 1)
            self.rows.append((material, button))
        grid.attach(Gtk.Label(label='베드'), 0, 4, 1, 1)
        self.bed_current = Gtk.Label(label='—', hexpand=True)
        self.bed_button = TemperatureControl(self._gtk, self.adjust_temperature, 'bed')
        self.bed_button.set_sensitive(False)
        grid.attach(self.bed_current, 1, 4, 1, 1)
        grid.attach(self.bed_button, 2, 4, 1, 1)
        self.bed_target = 0
        scroll = Gtk.ScrolledWindow()
        scroll.set_overlay_scrolling(False)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(grid)
        self.layout.pack_start(scroll, True, True, 0)
        self.content.add(self.layout)

    def activate(self):
        self.reset_request()
        self.generation += 1
        self.pending = 0
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self.query)
        self.query()

    def deactivate(self):
        self.reset_request()
        self.generation += 1
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def reset_request(self):
        self.request_serial += 1
        self.sending = False
        self.sent_at = 0
        self.last_status = 0
        self.pending = 0

    def query(self):
        socket = getattr(self._screen, '_ws', None)
        if socket is not self.socket:
            self.socket = socket
            self.generation += 1
            self.reset_request()
        if not socket or not getattr(socket, 'connected', False):
            self.generation += 1
            self.reset_request()
            return True
        now = time.monotonic()
        if self.sending and now - self.sent_at >= 5:
            logging.warning('Tool temperature response timed out; refreshing printer state')
            self.reset_request()
            self.status.set_text('온도 변경 응답 지연 · 현재 상태를 다시 확인합니다.')
        if self.pending and now - self.pending < 5:
            return True
        self.pending = now
        self._screen._ws.send_method('printer.objects.query', {'objects': {
            'lugo_tool_temperature': None, 'extruder': ['temperature', 'target'], 'heater_bed': ['temperature', 'target']}},
            self.received, self.generation)
        return True

    def received(self, response, method, params, generation):
        if generation != self.generation:
            return
        self.pending = 0
        self.last_status = time.monotonic()
        status = response.get('result', {}).get('status', {})
        self.state = status.get('lugo_tool_temperature', {})
        active = self.state.get('active', False)
        heater = status.get('extruder', {})
        message = (('' if active else '출력 시작 후 변경 가능 · ') +
                   f"{heater.get('temperature', 0):.1f} / {heater.get('target', 0):.0f} °C")
        if not self.state:
            message = '툴 온도 확장 연결을 확인하세요.'
        if self.status.get_text() != message:
            self.status.set_text(message)
        for tool, (material, button) in enumerate(self.rows):
            used = self.state.get('used', [None] * 4)[tool]
            name = self.state.get('materials', ['Unknown'] * 4)[tool]
            name = '없음' if used is False else ('알 수 없음' if name == 'Unknown' else name)
            if material.get_text() != name:
                material.set_text(name)
            value = self.state.get('temperatures', [None] * 4)[tool]
            override = self.state.get('overrides', [None] * 4)[tool]
            label = '—' if value is None else f'{value:g} °C' + (' *' if override is not None else '')
            if button.get_label() != label:
                button.set_label(label)
            enabled = active and used is not False and value is not None
            if button.get_sensitive() != enabled:
                button.set_sensitive(enabled)
        bed = status.get('heater_bed', {})
        self.bed_target = bed.get('target', 0)
        current = f"{bed.get('temperature', 0):.1f} °C" if bed else '—'
        bed_enabled = bool(bed) and self.state.get('bed_ready', False)
        target = f"{self.bed_target:g} °C" if bed_enabled else '준비 중' if active else '—'
        if self.bed_current.get_text() != current:
            self.bed_current.set_text(current)
        if self.bed_button.get_label() != target:
            self.bed_button.set_label(target)
        if self.bed_button.get_sensitive() != bed_enabled:
            self.bed_button.set_sensitive(bed_enabled)

    def adjust_temperature(self, widget, tool, delta):
        if self.sending or time.monotonic() - getattr(self, 'last_status', 0) > 5:
            return
        if tool == 'bed':
            if not self.state.get('bed_ready', False):
                return
            value = self.bed_target
        else:
            if not self.state.get('active') or self.state.get('used', [None] * 4)[tool] is False:
                return
            value = self.state.get('temperatures', [None] * 4)[tool]
        if value is None:
            return
        value = max(0 if tool == 'bed' else 1, value + delta)
        script = f'M140 S{value:g}' if tool == 'bed' else f'LUGO_SET_TOOL_TEMP TOOL={tool} TEMP={value:g}'
        self.sending = True
        self.request_serial += 1
        serial = self.request_serial
        self.sent_at = time.monotonic()
        self.generation += 1  # Ignore pre-command status responses.
        self.pending = 0
        try:
            if tool == 'bed' and self.state.get('live_bed_api'):
                sent = self._screen._ws.send_method(
                    'printer.lugo_tool_temperature.set_bed',
                    {'temperature': value}, self.saved, serial)
            elif tool == 'bed' and self.state.get('active'):
                self.saved({'error': {'message': '베드 온도 확장 업데이트 후 Klipper를 재시작하세요.'}}, serial=serial)
                return
            elif tool != 'bed' and self.state.get('live_api'):
                sent = self._screen._ws.send_method(
                    'printer.lugo_tool_temperature.set',
                    {'tool': tool, 'temperature': value}, self.saved, serial)
            else:
                sent = self._screen._ws.send_method('printer.gcode.script', {'script': script}, self.saved, serial)
            if sent is False:
                self.saved({'error': {'message': '명령 전송 실패'}}, serial=serial)
        except Exception:
            self.saved({'error': {'message': '프린터 연결을 확인하세요.'}}, serial=serial)

    def saved(self, response, method=None, params=None, serial=None):
        if serial != self.request_serial:
            return
        # Require a fresh target before accepting the next increment.
        self.last_status = 0
        self.sending = False
        if 'error' in response:
            self._screen.show_popup_message(str(response['error'].get('message', '온도 변경 실패')))
        if self.timer is not None:
            self.query()
