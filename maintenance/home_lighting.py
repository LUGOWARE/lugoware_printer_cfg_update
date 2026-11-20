"""Install the common home layout and migrate the former chamber fan output."""
import re


TOGGLE = 'TOGGLE_CHAMBER_LED'


def replace_sections(text, replacements):
    pattern = re.compile(r'(?ms)^\[([^\]\n]+)\][^\n]*\n.*?(?=^\[|\Z)')
    def replace(match):
        name = match[1].strip()
        return replacements.pop(name) if name in replacements else match[0]
    body = pattern.sub(replace, text)
    if replacements:
        body = body.rstrip() + '\n\n' + ''.join(replacements.values())
    return body


def printer_config(text):
    body, marker, saved = text.partition('#*# <---------------------- SAVE_CONFIG')
    def get_pin(name):
        section = re.search(r'(?ms)^\[' + re.escape(name) + r'\][^\n]*\n(.*?)(?=^\[|\Z)', body)
        if section is None:
            return None
        pin = re.search(r'(?m)^\s*pin\s*[:=]\s*([^#;\s]+)', section[1])
        if pin is None:
            raise ValueError('Missing output pin in ' + name)
        return pin[1]

    old_names = ('fan_generic chamber_fan', 'output_pin chamber_fan', 'output_pin LED')
    existing = get_pin('output_pin chamber_led')
    # M8P already has a dedicated case-light output. M5P reuses its fan switch.
    pin = existing or get_pin('output_pin LED') or get_pin(old_names[0]) or get_pin(old_names[1])
    if pin is None:
        return text
    if existing and f'[gcode_macro {TOGGLE}]' in body and not any(
            f'[{name}]' in body for name in (*old_names, 'delayed_gcode chamber_fan_auto_on')):
        return text
    retired = (*old_names, 'delayed_gcode chamber_fan_auto_on',
               'output_pin chamber_led', f'gcode_macro {TOGGLE}')
    block = f'''[output_pin chamber_led]
pin: {pin}
pwm: False
value: 0
shutdown_value: 0

[gcode_macro {TOGGLE}]
description: Toggle the chamber LED
gcode:
    {{% set lit = printer["output_pin chamber_led"].value|float > 0.5 %}}
    SET_PIN PIN=chamber_led VALUE={{0 if lit else 1}}

'''
    replacements = {name: '' for name in retired if f'[{name}]' in body}
    target = next(name for name in ('output_pin chamber_led', 'output_pin LED', *old_names)
                  if f'[{name}]' in body)
    replacements[target] = block
    return replace_sections(body, replacements) + marker + saved


def screen_config(text):
    body, marker, saved = text.partition('#~# --- Do not edit below this line.')
    sections = {
        'menu __main network': "name: {{ gettext('Network') }}\nicon: network\npanel: network\n",
        'menu __main led': ('name: LED\nicon: light\nmethod: printer.gcode.script\n'
                            f'params: {{"script": "{TOGGLE}"}}\n'
                            "enable: {{ 'output_pin chamber_led' in printer.config_sections }}\n"),
        'menu __main more network': 'enable: False\n',
        'menu __main more led': 'enable: False\n',
    }
    return replace_sections(body, {name: f'[{name}]\n{content}\n' for name, content in sections.items()}) + marker + saved


def home_panel(source):
    if '    def create_home_buttons(self, items):' in source and '("print", 1, 2, 2)' in source:
        return source

    def edit(pattern, replacement, expected=1):
        nonlocal source
        source, count = re.subn(pattern, replacement, source, flags=re.M)
        if count != expected:
            raise ValueError('Unsupported home menu source: ' + pattern)

    edit(r'^from gi.repository import GLib, Gtk$', 'from gi.repository import Gtk')
    edit(r'^from ks_includes.widgets.heatergraph import HeaterGraph\n', '')
    edit(r'^        self.graph_update = None\n', '')
    edit(r'(?s)^    def update_graph_visibility\(.*?(?=^    def add_device\()', '''    def activate(self):
        pass

    def deactivate(self):
        if self.active_heater is not None:
            self.hide_numpad()

''')
    edit(r'^            dev_type = "[a-z]+"\n', '', 5)
    edit(r'(?s)^        rgb = .*?(?=^        name = self\._gtk\.Button\()',
         '        can_target = self._printer.device_has_target(device)\n\n')
    edit(r'^        name.connect\("clicked", self.toggle_visibility, device\)\n', '')
    edit(r'(?s)^        visible = .*?(?=^        temp = self\._gtk\.Button\()',
         '        name.get_style_context().add_class("graph_label")\n\n')
    edit(r'^            "visible": visible,\n', '')
    edit(r'(?s)^        (?:# Keep the graph data[^\n]*\n        if device != .*?\n|devices = sorted\(self.devices\)\n).*?(?=^        return True$)', '''        if device in ("extruder", "heater_bed"):
            for button in (name, temp):
                button.set_vexpand(True)
                button.set_margin_top(5)
                button.set_margin_bottom(5)
        if device != "heater_generic Toolhead":
            devices = sorted(key for key in self.devices if key != "heater_generic Toolhead")
            pos = devices.index(device) + 1
            self.labels["devices"].insert_row(pos)
            self.labels["devices"].attach(name, 0, pos, 1, 1)
            self.labels["devices"].attach(temp, 1, pos, 1, 1)
            self.labels["devices"].show_all()
''')
    edit(r'(?s)^    def toggle_visibility\(.*?(?=^    def change_target_temp\()', '')
    edit(r'^        self.labels\["da"\] = HeaterGraph[^\n]+\n\n', '')
    edit(r'Gtk.Grid\(vexpand=False\)', 'Gtk.Grid(vexpand=True)')
    edit(r'^        scroll.add\(self.labels\["devices"\]\)',
         '        scroll.set_propagate_natural_height(True)\n        scroll.add(self.labels["devices"])')
    edit(r'^        self.left_panel.add\(scroll\)',
         '        self.left_panel.pack_start(scroll, True, True, 0)\n'
         '        if self._screen.vertical_mode:\n            self.left_panel.set_margin_bottom(10)')
    edit(r'^            if not self._gtk.ultra_tall:\n                self.update_graph_visibility\(force_hide=(?:False|True)\)\n', '', 2)
    edit(r'(?s)^    def update_graph\(.*?(?=^    def back\()', '')
    edit(r'self.arrangeMenuItems\(items, [23], True\)', 'self.create_home_buttons(items)', 2)
    edit(r'self.main_menu.attach\(self.create_left_panel\(\), 0, 0, 1, 3\)',
         'self.main_menu.attach(self.create_left_panel(), 0, 0, 1, 2)')
    edit(r'(?s)^            top = self.main_menu.get_child_at\(0, 0\)\n.*?^            self.main_menu.attach\(top, 0, 0, 1, 3\)\n',
         '            self.main_menu.remove(self.labels["keypad"])\n')
    edit(r'(?s)^            top = self.main_menu.get_child_at\(0, 0\)\n.*?^            self.main_menu.attach\(self.labels\["keypad"\], 0, 2, 1, 2\)\n',
         '            self.main_menu.remove(self.menu_scroll)\n            self.main_menu.attach(self.labels["keypad"], 0, 2, 1, 3)\n')
    edit(r'self.main_menu.attach\(self.menu_scroll, 0, 3, 1, 2\)',
         'self.main_menu.attach(self.menu_scroll, 0, 2, 1, 3)', 2)
    edit(r'^    def activate\(self\):\n', '''    def create_home_buttons(self, items):
        grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True,
                        hexpand=True, vexpand=True)
        positions = (
            ("move", 0, 0, 1), ("temperature", 1, 0, 1), ("extrude", 2, 0, 1),
            ("prepare_preview", 0, 1, 1), ("led", 1, 1, 1), ("network", 2, 1, 1),
            ("more", 0, 2, 1), ("print", 1, 2, 2),
        )
        menu = {key: value for item in items for key, value in item.items()}
        for key, column, row, width in positions:
            item = menu.get(key)
            if item and self.evaluate_enable(item["enable"]):
                grid.attach(self.labels[key], column, row, width, 1)
        return grid

    def activate(self):
''')
    return source
