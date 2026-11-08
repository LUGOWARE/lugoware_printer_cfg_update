"""Manual extrusion panel: volumetric flow in mm3/s, actual filament travel in mm."""
import math
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel


def extrusion_script(diameter, flow, distance, direction):
    if diameter not in (1.75, 2.85) or flow < 1 or distance < 1 or direction not in (-1, 1):
        raise ValueError('Invalid extrusion settings')
    feed = flow / (math.pi * (diameter / 2) ** 2) * 60
    return ('SAVE_GCODE_STATE NAME=LUGO_MANUAL_EXTRUDE\n'
            'M83\nM220 S100\nM221 S100\n'
            f'G1 E{direction * distance:g} F{feed:.6f}\nM400\n'
            'RESTORE_GCODE_STATE NAME=LUGO_MANUAL_EXTRUDE MOVE=0')


class Panel(ScreenPanel):
    _diameter_provider = None

    def __init__(self, screen, title):
        super().__init__(screen, title or _('Extrude'))
        self.diameter = 1.75
        self.flows = {1.75: 10, 2.85: 5}
        self.distance = 15
        self.busy = False
        self.actions = []
        self.diameter_buttons = {}
        self.content.get_style_context().add_class('lugo-extrusion')
        provider = Gtk.CssProvider()
        provider.load_from_data(b'\n            .lugo-extrusion button {\n                background-image: none; background-color: #252525;\n                 \n                box-shadow: none; text-shadow: none;\n              border-radius: .25em;  border: 1px solid #252525; }\n            .lugo-extrusion button label { color: #e2e2e2; }\n            .lugo-extrusion button:active,\n            .lugo-extrusion button.lugo-selected {\n                background-color: #424242; \n              border-radius: .25em;  border-color: #424242; }\n            .lugo-extrusion button.lugo-selected label { font-weight: bold; }\n            .lugo-extrusion button:disabled {\n                background-color: #252525; \n              border-radius: .25em;  border-color: #252525; }\n            .lugo-extrusion button:disabled label { color: #888888; }\n            .lugo-extrusion button.lugo-diameter {    border-radius: .25em;  border: 1px solid #252525; }\n            .lugo-extrusion button.lugo-diameter.lugo-selected {    border-radius: .25em;  border-color: #424242; }\n        \n.lugo-extrusion button, .lugo-extrusion button:active, .lugo-extrusion button:disabled,\n.lugo-extrusion button.button_active, .lugo-extrusion button.lugo-diameter,\n.lugo-extrusion button.lugo-selected, .lugo-extrusion button.lugo-diameter.lugo-selected { border: 0; }\n.lugo-extrusion button.lugo-inner-control { border: 1px solid #252525; }\n\n.fan_controls button,\n.fine-card button,\n.lugo-temperature-control button,\n.lugo-diagnostics .diagnostic-card button,\n.lugo-theme .frame-item button,\n.lugo-theme .tz-current button,\n.lugo-settings .frame-item button { background-color: #1f1f1f; }\n.fan_controls button:active,\n.fan_controls button:checked,\n.fan_controls button.selected,\n.fan_controls button.lugo-selected,\n.fan_controls button.button_active,\n.fan_controls button.lugo-tapped,\n.fine-card button:active,\n.fine-card button:checked,\n.fine-card button.selected,\n.fine-card button.lugo-selected,\n.fine-card button.button_active,\n.fine-card button.lugo-tapped,\n.lugo-temperature-control button:active,\n.lugo-temperature-control button:checked,\n.lugo-temperature-control button.selected,\n.lugo-temperature-control button.lugo-selected,\n.lugo-temperature-control button.button_active,\n.lugo-temperature-control button.lugo-tapped,\n.lugo-diagnostics .diagnostic-card button:active,\n.lugo-diagnostics .diagnostic-card button:checked,\n.lugo-diagnostics .diagnostic-card button.selected,\n.lugo-diagnostics .diagnostic-card button.lugo-selected,\n.lugo-diagnostics .diagnostic-card button.button_active,\n.lugo-diagnostics .diagnostic-card button.lugo-tapped,\n.lugo-theme .frame-item button:active,\n.lugo-theme .frame-item button:checked,\n.lugo-theme .frame-item button.selected,\n.lugo-theme .frame-item button.lugo-selected,\n.lugo-theme .frame-item button.button_active,\n.lugo-theme .frame-item button.lugo-tapped,\n.lugo-theme .tz-current button:active,\n.lugo-theme .tz-current button:checked,\n.lugo-theme .tz-current button.selected,\n.lugo-theme .tz-current button.lugo-selected,\n.lugo-theme .tz-current button.button_active,\n.lugo-theme .tz-current button.lugo-tapped,\n.lugo-settings .frame-item button:active,\n.lugo-settings .frame-item button:checked,\n.lugo-settings .frame-item button.selected,\n.lugo-settings .frame-item button.lugo-selected,\n.lugo-settings .frame-item button.button_active,\n.lugo-settings .frame-item button.lugo-tapped,\n.lugo-extrusion button.lugo-inner-control:active,\n.lugo-extrusion button.lugo-inner-control:checked,\n.lugo-extrusion button.lugo-inner-control.selected,\n.lugo-extrusion button.lugo-inner-control.lugo-selected,\n.lugo-extrusion button.lugo-inner-control.button_active,\n.lugo-extrusion button.lugo-inner-control.lugo-tapped { background-color: #424242; }\n')
        if Panel._diameter_provider is None:
            Panel._diameter_provider = provider
            Gtk.StyleContext.add_provider_for_screen(
                self.content.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        # Independent rows: one wrapped caption must not enlarge every row.
        layout = Gtk.Grid(column_homogeneous=True, row_homogeneous=False,
                          column_spacing=4, row_spacing=4, hexpand=True, vexpand=True)
        layout.set_margin_start(4)
        layout.set_margin_end(4)
        top = Gtk.Grid(column_homogeneous=True, row_homogeneous=True,
                       column_spacing=4, row_spacing=4, hexpand=True, vexpand=True)
        self.nozzle = self._gtk.Button('extruder', '— / — °C', 'color1')
        self.nozzle.set_can_focus(False)
        cover = Gtk.EventBox()
        cover.set_visible_window(False)
        cover.set_above_child(True)
        cover.add(self.nozzle)
        top.attach(cover, 0, 0, 1, 1)
        temp = self._gtk.Button('heat-up', _('Temperature'), 'color2')
        temp.connect('clicked', self.menu_item_clicked, {'panel': 'nozzle_temperature'})
        top.attach(temp, 1, 0, 1, 1)
        extrusion_actions = Gtk.Grid(column_homogeneous=True, column_spacing=4,
                                     hexpand=True, vexpand=True)
        for column, (icon, title, direction) in enumerate((('extrude', _('Extrude'), 1), ('retract', _('Retract'), -1))):
            button = self._gtk.Button(icon, title, 'color3')
            button.connect('clicked', self.move, direction)
            extrusion_actions.attach(button, column, 0, 1, 1)
            self.actions.append(button)
        layout.attach(top, 0, 0, 2, 1)
        choices = Gtk.Grid(column_homogeneous=True, column_spacing=4,
                           hexpand=True, vexpand=True)
        for column, diameter in enumerate((1.75, 2.85)):
            button = self._gtk.Button(label=f'{diameter} mm', style='color2')
            button.connect('clicked', self.select_diameter, diameter)
            self.diameter_buttons[diameter] = button
            button.get_style_context().add_class('lugo-diameter')
            choices.attach(button, column, 0, 1, 1)
        motor = self._gtk.Button('motor-off', _('Motor off'), 'color3', scale=0.6,
                                 position=Gtk.PositionType.TOP)
        motor.connect('clicked', self.motor_off)
        choices.attach(motor, 2, 0, 1, 1)
        self.actions.append(motor)
        self.motor_button = motor
        layout.attach(choices, 0, 1, 2, 1)
        self._row_sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
        for row in (top, choices, extrusion_actions):
            self._row_sizes.add_widget(row)
        adjust = Gtk.Grid(column_homogeneous=True, row_homogeneous=False,
                          column_spacing=4, row_spacing=4, hexpand=True, vexpand=False)
        self.values = {}
        for col, (key, caption) in enumerate((('flow', 'MVS (mm³/s)'), ('distance', _('Distance (mm)')))):
            heading = Gtk.Label(label=caption, vexpand=False)
            from ks_includes.lugo_layout import wrap_label
            wrap_label(heading, 14)
            heading.set_margin_top(6)
            heading.set_margin_bottom(2)
            adjust.attach(heading, col, 0, 1, 1)
            up = self._gtk.Button(label='▲', style='color1')
            up.get_style_context().add_class('lugo-inner-control')
            up.set_vexpand(False)
            up.set_size_request(-1, 48)
            up.connect('clicked', self.adjust, key, 1)
            adjust.attach(up, col, 1, 1, 1)
            value = Gtk.Label(vexpand=False)
            value.set_size_request(-1, 64)
            self.values[key] = value
            adjust.attach(value, col, 2, 1, 1)
            down = self._gtk.Button(label='▼', style='color1')
            down.get_style_context().add_class('lugo-inner-control')
            down.set_vexpand(False)
            down.set_size_request(-1, 48)
            down.connect('clicked', self.adjust, key, -1)
            adjust.attach(down, col, 3, 1, 1)
        layout.attach(adjust, 0, 2, 2, 1)
        layout.attach(extrusion_actions, 0, 3, 2, 1)
        # Constrain the panel's minimum height so the shared navigation stays visible.
        # Small displays / unusually large fonts can scroll inside this area only.
        viewport = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        viewport.set_overlay_scrolling(False)
        viewport.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        viewport.add(layout)
        self.content.add(viewport)
        self.render()

    def render(self):
        self.values['flow'].set_markup(f'<span size="xx-large">{self.flows[self.diameter]}</span>')
        self.values['distance'].set_markup(f'<span size="xx-large">{self.distance}</span>')
        for diameter, button in self.diameter_buttons.items():
            context = button.get_style_context()
            if diameter == self.diameter:
                button.set_label(f'✓ {diameter} mm')
                context.add_class('button_active')
                context.add_class('lugo-selected')
                context.add_class('horizontal_togglebuttons_active')
            else:
                button.set_label(f'{diameter} mm')
                context.remove_class('button_active')
                context.remove_class('lugo-selected')
                context.remove_class('horizontal_togglebuttons_active')

    def select_diameter(self, widget, diameter):
        self.diameter = diameter
        self.render()

    def adjust(self, widget, key, delta):
        if key == 'flow':
            self.flows[self.diameter] = max(1, self.flows[self.diameter] + delta)
        else:
            self.distance = max(1, self.distance + delta)
        self.render()

    def activate(self):
        # A fresh visit always starts with the requested defaults.
        self.diameter = 1.75
        self.flows = {1.75: 10, 2.85: 5}
        self.distance = 15
        self.render()
        self.update_state()

    def update_state(self):
        enabled = self._printer.state in ('ready', 'paused') and not self.busy
        for button in self.actions:
            button.set_sensitive(enabled)
        self.motor_button.set_sensitive(not self.busy and self.motor_allowed())
        heater = self._printer.get_stat('toolhead', 'extruder') or 'extruder'
        current = self._printer.get_stat(heater, 'temperature') or 0
        target = self._printer.get_stat(heater, 'target') or 0
        label = f'{current:.1f} / {target:.0f} °C'
        if self.nozzle.get_label() != label:
            self.nozzle.set_label(label)

    def process_update(self, action, data):
        if action == 'notify_status_update':
            self.update_state()

    def send(self, script):
        if self.busy or self._printer.state not in ('ready', 'paused'):
            return
        self.busy = True
        self.update_state()
        try:
            sent = self._screen._ws.send_method('printer.gcode.script', {'script': script}, self.done)
            if sent is False:
                self.done({'error': {'message': _('Failed to send command')}})
        except Exception:
            self.done({'error': {'message': _('Check printer connection.')}})

    def done(self, response, *args):
        self.busy = False
        self.update_state()
        if 'error' in response:
            self._screen.show_popup_message(response['error'].get('message', _('Command failed')))

    def move(self, widget, direction):
        self.send(extrusion_script(self.diameter, self.flows[self.diameter], self.distance, direction))

    def motor_allowed(self):
        return (self._printer.state == 'ready'
                and not self._printer.get_stat('pause_resume', 'is_paused')
                and self._printer.get_stat('print_stats', 'state') not in ('printing', 'paused'))

    def motor_off(self, widget):
        if not self.motor_allowed():
            self._screen.show_popup_message(_('Motors cannot be disabled while printing or paused.'))
            return
        self.send('M84')
