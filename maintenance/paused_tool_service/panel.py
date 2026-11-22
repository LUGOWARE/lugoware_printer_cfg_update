from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.busy = False
        layout = Gtk.Grid(column_homogeneous=True, column_spacing=6, row_spacing=6,
                          hexpand=True, vexpand=True)
        self.status = Gtk.Label(wrap=True, hexpand=True)
        layout.attach(self.status, 0, 0, 2, 1)
        self.tools = []
        for slot in range(4):
            button = self._gtk.Button(label='T%d' % (slot + 1), style='color2')
            button.connect('clicked', self.move, 'PAUSED_TOOL_DOCK TOOL=%d' % slot)
            layout.attach(button, slot % 2, 1 + slot // 2, 1, 1)
            self.tools.append(button)
        self.heat = self._gtk.Button('heat-up', _('Temperature'), 'color3')
        self.heat.connect('clicked', self.menu_item_clicked, {'panel': 'temperature'})
        layout.attach(self.heat, 0, 3, 1, 1)
        self.extrude = self._gtk.Button('extrude', _('Extrude'), 'color3')
        self.extrude.connect('clicked', self.menu_item_clicked, {'panel': 'extrude'})
        layout.attach(self.extrude, 1, 3, 1, 1)
        self.park = self._gtk.Button(label='파킹', style='color1')
        self.park.connect('clicked', self.move, 'PAUSED_TOOL_PARK')
        layout.attach(self.park, 0, 4, 2, 1)
        self.content.add(layout)
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
        for b in self.tools:
            b.set_sensitive(bool(available and phase == 'idle'))
        for b in (self.heat, self.extrude, self.park):
            b.set_sensitive(bool(available and phase == 'attached'))
        if phase == 'fault' or hold:
            label = '툴 상태를 확인해 주세요. 출력은 일시정지 상태입니다.'
        elif phase == 'attached' and tool is not None:
            label = 'T%d · X0 Y125' % (tool + 1)
        elif self.busy or phase in ('docking', 'parking'):
            label = '툴 이동 중…'
        else:
            label = '정비할 툴을 선택하세요.'
        self.status.set_label(label)

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
