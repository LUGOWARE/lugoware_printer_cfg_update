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
        css.load_from_data(b'\n        .fan_controls { background-color: #252525; \n             padding: 12px;  border: 0; border-radius: .25em; }\n        .fan_controls button { min-height: 38px; min-width: 0; padding: 5px 8px;\n            background-image: none; background-color: #252525;\n              box-shadow: none;   border-radius: .25em;  border: 1px solid #505050; }\n        .fan_controls button label { color: #ffffff; }\n        .fan_controls button:active { background-color: #087da5;    border-radius: .25em;  border-color: #66dcff; }\n        .fan_controls scale trough { background-color: #111111; min-height: 10px;\n            border: 1px solid #484848; border-radius: 6px; }\n        .fan_controls scale highlight { background-color: #305730; border-radius: 6px; }\n        .fan_controls scale slider { background-image: none; background-color: #eeeeee;\n            border: 1px solid #bbbbbb; min-width: 34px; min-height: 34px; border-radius: 20px; }\n        .fan_controls scale { min-height: 30px; margin: 0; }\n        ')
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
                scale.connect('button-press-event', self.press, fan)
                scale.connect('button-release-event', self.release, fan)
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
        scroll.add(rows)
        self.content.add(scroll)

    def preview(self, scale, fan):
        self.devices[fan]['label'].set_text(f'{round(scale.get_value())}%')

    def press(self, widget, event, fan):
        self.devices[fan]['dragging'] = True
        return False

    def release(self, widget, event, fan):
        self.devices[fan]['dragging'] = False
        self.send(fan)
        return False

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
