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
    def __init__(self, screen, title):
        super().__init__(screen, title or 'Extrude')
        self.diameter = 1.75
        self.flows = {1.75: 10, 2.85: 5}
        self.distance = 15
        self.busy = False
        self.actions = []
        self.diameter_buttons = {}
        # One shared grid distributes height without gaps between nested boxes.
        layout = Gtk.Grid(column_homogeneous=True, row_homogeneous=True,
                          column_spacing=4, row_spacing=4, hexpand=True, vexpand=True)
        top = Gtk.Grid(column_homogeneous=True, row_homogeneous=True,
                       column_spacing=4, row_spacing=4, hexpand=True, vexpand=True)
        self.nozzle = self._gtk.Button('extruder', '— / — °C', 'color1')
        self.nozzle.set_can_focus(False)
        cover = Gtk.EventBox()
        cover.set_visible_window(False)
        cover.set_above_child(True)
        cover.add(self.nozzle)
        top.attach(cover, 0, 0, 1, 1)
        temp = self._gtk.Button('heat-up', 'Temperature', 'color2')
        temp.connect('clicked', self.menu_item_clicked, {'panel': 'nozzle_temperature'})
        top.attach(temp, 1, 0, 1, 1)
        extrusion_actions = Gtk.Grid(column_homogeneous=True, column_spacing=4,
                                     hexpand=True, vexpand=True)
        for column, (icon, title, direction) in enumerate((('extrude', 'Extrude', 1), ('retract', 'Retract', -1))):
            button = self._gtk.Button(icon, title, 'color3')
            button.connect('clicked', self.move, direction)
            extrusion_actions.attach(button, column, 0, 1, 1)
            self.actions.append(button)
        layout.attach(top, 0, 0, 2, 2)
        choices = Gtk.Grid(column_homogeneous=True, column_spacing=4,
                           hexpand=True, vexpand=True)
        for column, diameter in enumerate((1.75, 2.85)):
            button = self._gtk.Button(label=f'{diameter} mm', style='color2')
            button.connect('clicked', self.select_diameter, diameter)
            self.diameter_buttons[diameter] = button
            choices.attach(button, column, 0, 1, 1)
        motor = self._gtk.Button('motor-off', 'Motor off', 'color3', scale=0.6,
                                 position=Gtk.PositionType.TOP)
        motor.connect('clicked', self.motor_off)
        choices.attach(motor, 2, 0, 1, 1)
        self.actions.append(motor)
        layout.attach(choices, 0, 2, 2, 2)
        adjust = Gtk.Grid(column_homogeneous=True, row_homogeneous=False,
                          column_spacing=4, row_spacing=4, hexpand=True, vexpand=True)
        self.values = {}
        for col, (key, caption) in enumerate((('flow', 'MVS (mm³/s)'), ('distance', 'Distance (mm)'))):
            heading = Gtk.Label(label=caption, vexpand=False)
            heading.set_margin_top(6)
            heading.set_margin_bottom(2)
            adjust.attach(heading, col, 0, 1, 1)
            up = self._gtk.Button(label='▲', style='color1')
            up.connect('clicked', self.adjust, key, 1)
            adjust.attach(up, col, 1, 1, 1)
            value = Gtk.Label(vexpand=True)
            self.values[key] = value
            adjust.attach(value, col, 2, 1, 1)
            down = self._gtk.Button(label='▼', style='color1')
            down.connect('clicked', self.adjust, key, -1)
            adjust.attach(down, col, 3, 1, 1)
        layout.attach(adjust, 0, 4, 2, 4)
        layout.attach(extrusion_actions, 0, 8, 2, 2)
        self.content.add(layout)
        self.render()

    def render(self):
        self.values['flow'].set_markup(f'<span size="xx-large">{self.flows[self.diameter]}</span>')
        self.values['distance'].set_markup(f'<span size="xx-large">{self.distance}</span>')
        for diameter, button in self.diameter_buttons.items():
            context = button.get_style_context()
            if diameter == self.diameter:
                button.set_label(f'✓ {diameter} mm')
                context.add_class('button_active')
                context.add_class('horizontal_togglebuttons_active')
            else:
                button.set_label(f'{diameter} mm')
                context.remove_class('button_active')
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
                self.done({'error': {'message': 'Failed to send command'}})
        except Exception:
            self.done({'error': {'message': 'Check printer connection.'}})

    def done(self, response, *args):
        self.busy = False
        self.update_state()
        if 'error' in response:
            self._screen.show_popup_message(response['error'].get('message', 'Command failed'))

    def move(self, widget, direction):
        self.send(extrusion_script(self.diameter, self.flows[self.diameter], self.distance, direction))

    def motor_off(self, widget):
        self.send('M84')
