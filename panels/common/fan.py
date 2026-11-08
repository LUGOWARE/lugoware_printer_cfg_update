import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _('Fan'))
        self.devices = {}
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       hexpand=True, vexpand=True, valign=Gtk.Align.FILL, homogeneous=True)
        rows.set_margin_start(10)
        rows.set_margin_end(10)
        css = Gtk.CssProvider()
        css.load_from_data(b'\n        .fan_controls { background-color: #252525; \n             padding: 12px;  border: 0; border-radius: .25em; }\n        .fan_controls button { min-height: 38px; min-width: 0; padding: 5px 8px;\n            background-image: none; background-color: #252525;\n              box-shadow: none;   border-radius: .25em;  border: 1px solid #252525; }\n        .fan_controls button label { color: #e2e2e2; }\n        .fan_controls button:active { background-color: #424242;    border-radius: .25em;  border-color: #424242; }\n        .fan_controls scale trough { background-color: #1c1c1c; min-height: 10px;\n            border: 1px solid #282828; border-radius: 6px; }\n        .fan_controls scale highlight { background-color: #2f5631; border-radius: 6px; }\n        .fan_controls scale slider { background-image: none; background-color: #e2e2e2;\n            border: 1px solid #a2a2a2; min-width: 34px; min-height: 34px; border-radius: 20px; }\n        .fan_controls scale { min-height: 30px; margin: 0; }\n        \n.fan_controls button,\n.fine-card button,\n.lugo-temperature-control button,\n.lugo-diagnostics .diagnostic-card button,\n.lugo-theme .frame-item button,\n.lugo-theme .tz-current button,\n.lugo-settings .frame-item button { background-color: #1f1f1f; }\n.fan_controls button:active,\n.fan_controls button:checked,\n.fan_controls button.selected,\n.fan_controls button.lugo-selected,\n.fan_controls button.button_active,\n.fan_controls button.lugo-tapped,\n.fine-card button:active,\n.fine-card button:checked,\n.fine-card button.selected,\n.fine-card button.lugo-selected,\n.fine-card button.button_active,\n.fine-card button.lugo-tapped,\n.lugo-temperature-control button:active,\n.lugo-temperature-control button:checked,\n.lugo-temperature-control button.selected,\n.lugo-temperature-control button.lugo-selected,\n.lugo-temperature-control button.button_active,\n.lugo-temperature-control button.lugo-tapped,\n.lugo-diagnostics .diagnostic-card button:active,\n.lugo-diagnostics .diagnostic-card button:checked,\n.lugo-diagnostics .diagnostic-card button.selected,\n.lugo-diagnostics .diagnostic-card button.lugo-selected,\n.lugo-diagnostics .diagnostic-card button.button_active,\n.lugo-diagnostics .diagnostic-card button.lugo-tapped,\n.lugo-theme .frame-item button:active,\n.lugo-theme .frame-item button:checked,\n.lugo-theme .frame-item button.selected,\n.lugo-theme .frame-item button.lugo-selected,\n.lugo-theme .frame-item button.button_active,\n.lugo-theme .frame-item button.lugo-tapped,\n.lugo-theme .tz-current button:active,\n.lugo-theme .tz-current button:checked,\n.lugo-theme .tz-current button.selected,\n.lugo-theme .tz-current button.lugo-selected,\n.lugo-theme .tz-current button.button_active,\n.lugo-theme .tz-current button.lugo-tapped,\n.lugo-settings .frame-item button:active,\n.lugo-settings .frame-item button:checked,\n.lugo-settings .frame-item button.selected,\n.lugo-settings .frame-item button.lugo-selected,\n.lugo-settings .frame-item button.button_active,\n.lugo-settings .frame-item button.lugo-tapped,\n.lugo-extrusion button.lugo-inner-control:active,\n.lugo-extrusion button.lugo-inner-control:checked,\n.lugo-extrusion button.lugo-inner-control.selected,\n.lugo-extrusion button.lugo-inner-control.lugo-selected,\n.lugo-extrusion button.lugo-inner-control.button_active,\n.lugo-extrusion button.lugo-inner-control.lugo-tapped { background-color: #424242; }\n')
        fans = sorted(self._printer.get_fans(), key=lambda f: (f != 'fan', 'chamber' not in f.lower(), f))
        for fan in fans:
            kind, separator, name = fan.partition(' ')
            if name.startswith('_'):
                continue
            label = (_('Part cooling fan') if kind == 'fan' else
                     _('Chamber filter fan') if name.lower() == 'chamber_fan' else
                     _('Nozzle cooling fan') if name.lower() == 'hotend_fan' else name)
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            row.get_style_context().add_class('fan_controls')
            header = Gtk.Box(spacing=8)
            header.pack_start(Gtk.Label(label=label, xalign=0, wrap=True), True, True, 0)
            value = Gtk.Label(label='0%', xalign=1)
            header.pack_end(value, False, False, 0)
            row.pack_start(header, False, False, 0)
            changeable = kind in ('fan', 'fan_generic')
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            scale.set_sensitive(changeable)
            row.pack_start(scale, True, True, 0)
            self.devices[fan] = dict(scale=scale, label=value, dragging=False, until=0,
                                     changeable=changeable)
            if changeable:
                gesture = Gtk.GestureDrag.new(scale)
                gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                gesture.connect('drag-begin', self.drag_begin, fan)
                gesture.connect('drag-update', self.drag_update, fan)
                gesture.connect('drag-end', self.drag_end, fan)
                gesture.connect('cancel', self.drag_cancel, fan)
                self.devices[fan]['gesture'] = gesture
                scale.connect('value-changed', self.preview, fan)
                buttons = Gtk.Box(spacing=6, homogeneous=True)
                for text, amount, absolute in [(_('Off'), 0, True), ('− 5%', -5, False),
                                                ('+ 5%', 5, False), (_('Max'), 100, True)]:
                    button = Gtk.Button(label=text)
                    if absolute:
                        button.get_style_context().add_class('fan_off' if amount == 0 else 'fan_max')
                    button.connect('clicked', self.adjust, fan, amount, absolute)
                    buttons.pack_start(button, True, True, 0)
                row.pack_start(buttons, False, False, 0)
            else:
                row.pack_start(Gtk.Label(label=_('Automatic'), xalign=1), False, False, 0)
            rows.pack_start(row, True, True, 0)
            self.refresh(fan)
        def style(widget):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    style(child)
        style(rows)
        scroll = self._gtk.ScrolledWindow()
        scroll.set_kinetic_scrolling(False)
        scroll.add(rows)
        self.content.add(scroll)

    def preview(self, scale, fan):
        self.devices[fan]['label'].set_text(f'{round(scale.get_value())}%')

    def drag_value(self, fan, x):
        scale = self.devices[fan]['scale']
        rect = scale.get_range_rect()
        start, end = scale.get_slider_range()
        half = max(0, end - start) / 2
        fraction = (x - rect.x - half) / max(1, rect.width - 2 * half)
        if scale.get_inverted() ^ (scale.get_flippable() and scale.get_direction() == Gtk.TextDirection.RTL):
            fraction = 1 - fraction
        scale.set_value(max(0, min(100, fraction * 100)))

    def drag_begin(self, gesture, x, y, fan):
        device = self.devices[fan]
        device['dragging'] = True
        device['drag_start'] = x
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.drag_value(fan, x)

    def drag_update(self, gesture, x, y, fan):
        if self.devices[fan]['dragging']:
            self.drag_value(fan, self.devices[fan]['drag_start'] + x)

    def drag_end(self, gesture, x, y, fan):
        if self.devices[fan]['dragging']:
            self.drag_value(fan, self.devices[fan]['drag_start'] + x)
            self.devices[fan]['dragging'] = False
            self.send(fan)

    def drag_cancel(self, gesture, sequence, fan):
        self.devices[fan]['dragging'] = False
        self.refresh(fan)

    def adjust(self, button, fan, amount, absolute):
        scale = self.devices[fan]['scale']
        scale.set_value(max(0, min(100, amount if absolute else scale.get_value() + amount)))
        self.send(fan)

    def send(self, fan):
        device = self.devices[fan]
        value = round(device['scale'].get_value())
        device['until'] = time.monotonic() + 1
        command = (f'M106 S{round(value * 255 / 100)}' if fan == 'fan' else
                   f'SET_FAN_SPEED FAN={fan.split()[1]} SPEED={value / 100:.2f}')
        self._screen._ws.api.gcode_script(command)
        GLib.timeout_add(1200, self.refresh, fan)

    def refresh(self, fan):
        device = self.devices[fan]
        if device['dragging'] or time.monotonic() < device['until']:
            return False
        value = round(float(self._printer.get_fan_speed(fan)) * 100)
        device['scale'].set_value(value)
        device['label'].set_text(f'{value}%')
        return False

    def process_update(self, action, data):
        if action == 'notify_status_update':
            for fan in self.devices:
                if fan in data and 'speed' in data[fan]:
                    self.refresh(fan)
