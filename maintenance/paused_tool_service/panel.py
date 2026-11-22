from math import isfinite

from gi.repository import Gtk

from ks_includes.lugo_tool_cards import ToolCard, install_style, neutral
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.busy = False
        install_style(self.content)
        layout = Gtk.Grid(column_homogeneous=True, column_spacing=6, row_spacing=6,
                          margin=5, hexpand=True, vexpand=True)
        self.status = Gtk.Label(wrap=True, hexpand=True)
        self.status.set_size_request(-1, 48)
        self.hint = Gtk.Label(wrap=True)
        self.hint.get_style_context().add_class("printing-status-label")
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        heading.pack_start(self.status, False, False, 0)
        heading.pack_start(self.hint, False, False, 0)
        layout.attach(heading, 0, 0, 4, 1)
        self.tools = []
        image_height = max(44, min(192, round(self._gtk.height * .24), round(self._gtk.width * .4)))
        for slot in range(4):
            button = ToolCard(slot, image_height)
            button.set_vexpand(True)
            button.connect('clicked', self.move, 'PAUSED_TOOL_DOCK TOOL=%d' % slot)
            layout.attach(button, slot, 1, 1, 1)
            self.tools.append(button)
        self.heat = neutral(self._gtk.Button('heat-up', _('Temperature'), scale=.65))
        self.heat.connect('clicked', self.menu_item_clicked, {'panel': 'temperature'})
        layout.attach(self.heat, 0, 2, 2, 1)
        self.extrude = neutral(self._gtk.Button('extrude', _('Extrude'), scale=.65))
        self.extrude.connect('clicked', self.menu_item_clicked, {'panel': 'extrude'})
        layout.attach(self.extrude, 2, 2, 2, 1)
        self.park = neutral(self._gtk.Button(label=_('Park')))
        self.park.connect('clicked', self.move, 'PAUSED_TOOL_PARK')
        layout.attach(self.park, 0, 3, 4, 1)
        viewport = self._gtk.ScrolledWindow()
        viewport.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        viewport.add(layout)
        self.content.add(viewport)
        self.update_buttons()

    def activate(self):
        self.update_buttons()

    def process_update(self, action, _data):
        if action == 'notify_status_update':
            self.update_buttons()

    def update_buttons(self):
        state = self._printer.get_stat('paused_tool_service') or {}
        phase = state.get('phase', 'idle')
        tool = state.get('tool')
        paused = (self._printer.get_stat('print_stats', 'state') == 'paused'
                  and self._printer.get_stat('pause_resume', 'is_paused'))
        hold = self._printer.get_stat('fast_cancel', 'phase') == 'dock_sensor_hold'
        available = paused and not self.busy and not hold
        for slot, card in enumerate(self.tools):
            mounted = phase == 'attached' and tool == slot
            moving = phase in ('docking', 'parking') and tool == slot
            text = _('Changing tools') if moving else _('Docked') if mounted else _('Parked')
            card.update(text, mounted, self.tool_temperature() if mounted else '—')
            card.set_sensitive(bool(available and phase == 'idle'))
        for b in (self.heat, self.extrude, self.park):
            b.set_sensitive(bool(available and phase == 'attached'))
        if phase == 'fault' or hold:
            label = '툴 상태를 확인해 주세요. 출력은 일시정지 상태입니다.'
            hint = ''
        elif phase == 'attached' and tool is not None:
            label = 'T%d · %s' % (tool + 1, _('Docked'))
            hint = _('Paused')
        elif self.busy or phase in ('docking', 'parking'):
            label = '툴 이동 중…'
            hint = ''
        else:
            label = '정비할 툴을 선택하세요.'
            hint = '툴을 누르면 바로 가져옵니다.' if available else ''
        self.status.set_label(label)
        self.hint.set_label(hint)

    def tool_temperature(self):
        heater = 'heater_generic Toolhead' if self._printer.get_config_section('heater_generic Toolhead') else 'extruder'
        current = self._printer.get_stat(heater, 'temperature')
        target = self._printer.get_stat(heater, 'target')
        if not isinstance(current, (int, float)) or not isfinite(current):
            return '—'
        text = f'{current:.0f}'
        return f'{text} / {target:.0f} °C' if isinstance(target, (int, float)) and isfinite(target) else f'{text} °C'

    def move(self, _widget, command):
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        try:
            sent = self._screen._ws.send_method('printer.gcode.script', {'script': command}, self.done)
        except Exception:
            sent = False
        if sent is False:
            self.done({'error': {'message': _('Failed to send command')}})

    def done(self, response, *_args):
        self.busy = False
        self.update_buttons()
        if 'error' in response:
            self._screen.show_popup_message(str(response['error'].get('message', _('Command failed'))))
