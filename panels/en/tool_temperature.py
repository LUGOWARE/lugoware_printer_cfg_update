"""Manual-test print temperature panel. One shared heater, four logical tools."""
import math
import time
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.keypad import Keypad


class Panel(ScreenPanel):
    def __init__(self, screen, title, **kwargs):
        super().__init__(screen, title or 'Tool temperatures')
        self.timer = None
        self.generation = 0
        self.pending = 0
        self.selected = None
        self.state = {}
        self.rows = []
        self.layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.status = Gtk.Label(label='Checking printer status…')
        self.status.set_line_wrap(True)
        self.layout.pack_start(self.status, False, False, 0)
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, row_homogeneous=True)
        for tool in range(4):
            grid.attach(Gtk.Label(label=f'T{tool + 1}'), 0, tool, 1, 1)
            material = Gtk.Label(label='—', hexpand=True)
            material.set_line_wrap(True)
            material.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            material.set_max_width_chars(16)
            button = self._gtk.Button(label='—', style='color1')
            button.set_sensitive(False)
            button.connect('clicked', self.edit, tool)
            grid.attach(material, 1, tool, 1, 1)
            grid.attach(button, 2, tool, 1, 1)
            self.rows.append((material, button))
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(grid)
        self.layout.pack_start(scroll, True, True, 0)
        self.pad = Keypad(self._screen, self.save, self.close)
        self.entry = self.pad.entry
        self.pad.set_no_show_all(True)
        self.layout.pack_start(self.pad, True, True, 0)
        self.content.add(self.layout)

    def activate(self):
        self.generation += 1
        self.pending = 0
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self.query)
        self.query()

    def deactivate(self):
        self.generation += 1
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def query(self):
        now = time.monotonic()
        if self.pending and now - self.pending < 5:
            return True
        self.pending = now
        self._screen._ws.send_method('printer.objects.query', {'objects': {
            'lugo_tool_temperature': None, 'extruder': ['temperature', 'target']}},
            self.received, self.generation)
        return True

    def received(self, response, method, params, generation):
        if generation != self.generation:
            return
        self.pending = 0
        status = response.get('result', {}).get('status', {})
        self.state = status.get('lugo_tool_temperature', {})
        active = self.state.get('active', False)
        heater = status.get('extruder', {})
        message = (('' if active else 'Available during printing · ') +
                   f"{heater.get('temperature', 0):.1f} / {heater.get('target', 0):.0f} °C")
        if active and self.selected is not None:
            message = f'T{self.selected + 1} print temperature'
        if not self.state:
            message = 'Check tool temperature extension connection.'
        if self.status.get_text() != message:
            self.status.set_text(message)
        for tool, (material, button) in enumerate(self.rows):
            name = self.state.get('materials', ['Unknown'] * 4)[tool]
            name = 'Unknown' if name == 'Unknown' else name
            if material.get_text() != name:
                material.set_text(name)
            value = self.state.get('temperatures', [None] * 4)[tool]
            override = self.state.get('overrides', [None] * 4)[tool]
            label = '—' if value is None else f'{value:g} °C' + (' *' if override is not None else '')
            if button.get_label() != label:
                button.set_label(label)
            if button.get_sensitive() != active:
                button.set_sensitive(active)
        if not active and self.selected is not None:
            self.close()

    def edit(self, widget, tool):
        self.selected = tool
        value = self.state.get('temperatures', [None] * 4)[tool]
        self.entry.set_text('' if value is None else f'{value:g}')
        self.status.set_text(f'T{tool + 1} print temperature')
        self.pad.set_no_show_all(False)
        self.pad.show_all()
        # set_text() leaves the cursor at the start; backspace there is a no-op.
        # Focus after showing the keypad, then clear auto-selection and move to end.
        self.entry.grab_focus()
        self.entry.select_region(-1, -1)
        self.entry.set_position(-1)

    def close(self, *args):
        self.selected = None
        self.pad.hide()
        self.pad.set_no_show_all(True)

    def save(self, value):
        try:
            value = float(value)
            if not math.isfinite(value) or value <= 0 or self.selected is None:
                raise ValueError()
        except ValueError:
            self._screen.show_popup_message('Enter a valid temperature.')
            return
        self._screen._ws.send_method('printer.gcode.script', {'script':
            f'LUGO_SET_TOOL_TEMP TOOL={self.selected} TEMP={value:g}'}, self.saved)
        self.close()

    def saved(self, response, *args):
        if 'error' in response:
            self._screen.show_popup_message(str(response['error'].get('message', 'Temperature change failed')))
        self.query()
