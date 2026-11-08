import logging
import re
from html import escape

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    z_deltas = ["0.01", "0.05"]
    z_delta = z_deltas[-1]
    speed_deltas = ["5", "25"]
    s_delta = speed_deltas[-1]
    extrude_deltas = ["1", "2"]
    e_delta = extrude_deltas[-1]
    speed = extrusion = 100
    z_offset = 0.0

    def __init__(self, screen, title):
        super().__init__(screen, title or _("Fine Tuning"))
        self.z_delta = "0.05"
        self.s_delta = 10
        self.e_delta = 2
        self.z_offset = float(self._printer.get_stat("gcode_move", "homing_origin")[2])
        self.z_reported = self.z_offset
        self.z_pending = set()
        self.z_serial = 0
        self.speed = round(float(self._printer.get_stat("gcode_move", "speed_factor")) * 100)
        self.extrusion = round(float(self._printer.get_stat("gcode_move", "extrude_factor")) * 100)
        self.steps = {}
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         homogeneous=False, vexpand=True, hexpand=True)
        layout.set_margin_start(8)
        layout.set_margin_end(8)
        css = Gtk.CssProvider()
        css.load_from_data(b'\n            .fine-card { background-color: #252525;   padding: 8px;  border: 0; border-radius: .25em; }\n            .fine-card button { background-image: none; background-color: #252525;\n                  padding: 4px;\n                min-width: 0; min-height: 30px; box-shadow: none;   border-radius: .25em;  border: 1px solid #252525; }\n            .fine-card button:active, .fine-card button.selected {\n                background-color: #424242;    border-radius: .25em;  border-color: #424242; }\n            .fine-card button label { color: #e2e2e2; }\n            .fine-card button.selected label { color: #e2e2e2; font-weight: bold; }\n            .fine-card .fine-z-status { font-size: 15px; }\n            .fine-card .fine-value { font-size: 25px; }\n            .fine-card .fine-title { font-size: 21px; font-weight: 600; }\n            .fine-card.fine-divider { padding-bottom: 8px; }\n            .fine-card button.fine-step { min-height: 36px; font-size: 20px;   border-radius: .25em;   }\n            .fine-card button.fine-adjust { min-height: 60px;   border-radius: .25em;   }\n        \n.fan_controls button,\n.fine-card button,\n.lugo-temperature-control button,\n.lugo-diagnostics .diagnostic-card button,\n.lugo-theme .frame-item button,\n.lugo-theme .tz-current button,\n.lugo-settings .frame-item button { background-color: #1f1f1f; }\n.fan_controls button:active,\n.fan_controls button:checked,\n.fan_controls button.selected,\n.fan_controls button.lugo-selected,\n.fan_controls button.button_active,\n.fan_controls button.lugo-tapped,\n.fine-card button:active,\n.fine-card button:checked,\n.fine-card button.selected,\n.fine-card button.lugo-selected,\n.fine-card button.button_active,\n.fine-card button.lugo-tapped,\n.lugo-temperature-control button:active,\n.lugo-temperature-control button:checked,\n.lugo-temperature-control button.selected,\n.lugo-temperature-control button.lugo-selected,\n.lugo-temperature-control button.button_active,\n.lugo-temperature-control button.lugo-tapped,\n.lugo-diagnostics .diagnostic-card button:active,\n.lugo-diagnostics .diagnostic-card button:checked,\n.lugo-diagnostics .diagnostic-card button.selected,\n.lugo-diagnostics .diagnostic-card button.lugo-selected,\n.lugo-diagnostics .diagnostic-card button.button_active,\n.lugo-diagnostics .diagnostic-card button.lugo-tapped,\n.lugo-theme .frame-item button:active,\n.lugo-theme .frame-item button:checked,\n.lugo-theme .frame-item button.selected,\n.lugo-theme .frame-item button.lugo-selected,\n.lugo-theme .frame-item button.button_active,\n.lugo-theme .frame-item button.lugo-tapped,\n.lugo-theme .tz-current button:active,\n.lugo-theme .tz-current button:checked,\n.lugo-theme .tz-current button.selected,\n.lugo-theme .tz-current button.lugo-selected,\n.lugo-theme .tz-current button.button_active,\n.lugo-theme .tz-current button.lugo-tapped,\n.lugo-settings .frame-item button:active,\n.lugo-settings .frame-item button:checked,\n.lugo-settings .frame-item button.selected,\n.lugo-settings .frame-item button.lugo-selected,\n.lugo-settings .frame-item button.button_active,\n.lugo-settings .frame-item button.lugo-tapped,\n.lugo-extrusion button.lugo-inner-control:active,\n.lugo-extrusion button.lugo-inner-control:checked,\n.lugo-extrusion button.lugo-inner-control.selected,\n.lugo-extrusion button.lugo-inner-control.lugo-selected,\n.lugo-extrusion button.lugo-inner-control.button_active,\n.lugo-extrusion button.lugo-inner-control.lugo-tapped { background-color: #424242; }\n')
        definitions = [
            ("z_offset", _("Z offset"), "zoffset", self.change_babystepping,
             ("0.01", "0.05", "0.1"), "mm"),
            ("speed", _("Print speed"), "speedfactor", self.change_speed,
             (5, 10, 25), "%"),
            ("extrude", _("Extrusion"), "extrudefactor", self.change_extrusion,
             (1, 2, 5), "%"),
        ]
        for kind, title_text, value_key, callback, values, unit in definitions:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            card.get_style_context().add_class("fine-card")
            if kind != "extrude":
                card.get_style_context().add_class("fine-divider")
            header = Gtk.Box(spacing=8)
            heading = Gtk.Label(label=title_text, xalign=0)
            heading.get_style_context().add_class("fine-title")
            header.pack_start(heading, True, True, 0)
            reset = Gtk.Button(label=_("Reset"))
            reset.connect("clicked", self.confirm_reset, callback)
            header.pack_end(reset, False, False, 0)
            card.pack_start(header, False, False, 0)
            controls = Gtk.Grid(column_spacing=8, column_homogeneous=True, vexpand=True)
            value = Gtk.Label()
            value.get_style_context().add_class("fine-value")
            self.labels[value_key] = value
            for column, direction in ((0, "-"), (2, "+")):
                button = Gtk.Button()
                button.get_style_context().add_class("fine-adjust")
                content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
                if kind == "z_offset":
                    icon = "z-closer" if direction == "-" else "z-farther"
                    content.pack_start(self._gtk.Image(icon, 36, 36), False, False, 0)
                    label = Gtk.Label(label=_("Reduce gap") if direction == "-" else _("Increase gap"), wrap=True)
                else:
                    label = Gtk.Label(label="−" if direction == "-" else "+")
                    label.get_style_context().add_class("fine-value")
                content.pack_start(label, True, True, 0)
                button.add(content)
                button.connect("clicked", callback, direction)
                controls.attach(button, column, 0, 1, 1)
            if kind == "z_offset":
                value.get_style_context().remove_class("fine-value")
                value.set_justify(Gtk.Justification.CENTER)
                value.get_style_context().add_class("fine-z-status")
            controls.attach(value, 1, 0, 1, 1)
            card.pack_start(controls, True, True, 0)
            steps = Gtk.Box(spacing=6, homogeneous=True)
            self.steps[kind] = []
            for index, amount in enumerate(values):
                button = Gtk.Button(label=f"{amount} {unit}" if unit == "mm" else f"{amount}%")
                button.get_style_context().add_class("fine-step")
                button.connect("clicked", self.choose_step, kind, amount)
                if index == 1:
                    button.get_style_context().add_class("selected")
                self.steps[kind].append(button)
                steps.pack_start(button, True, True, 0)
            card.pack_start(steps, False, False, 0)
            layout.pack_start(card, True, True, 0)
        self.render_z()
        self.labels["speedfactor"].set_label(f"{self.speed}%")
        self.labels["extrudefactor"].set_label(f"{self.extrusion}%")
        def style(widget):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    style(child)
        style(layout)
        self.content.add(layout)

    def activate(self):
        for kind, amount in (("z_offset", "0.05"), ("speed", 10), ("extrude", 2)):
            self.choose_step(self.steps[kind][1], kind, amount)

    def confirm_reset(self, widget, callback):
        callback(widget, "reset")

    def choose_step(self, widget, kind, amount):
        for button in self.steps[kind]:
            button.get_style_context().remove_class("selected")
        widget.get_style_context().add_class("selected")
        if kind == "z_offset":
            self.z_delta = amount
        elif kind == "speed":
            self.s_delta = amount
        else:
            self.e_delta = amount

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "gcode_move" in data:
            if "homing_origin" in data["gcode_move"]:
                self.z_reported = float(data["gcode_move"]["homing_origin"][2])
                if not self.z_pending:
                    self.z_offset = self.z_reported
                self.render_z()
            if "extrude_factor" in data["gcode_move"]:
                self.extrusion = round(float(data["gcode_move"]["extrude_factor"]) * 100)
                self.labels["extrudefactor"].set_label(f"  {self.extrusion:3}%")
            if "speed_factor" in data["gcode_move"]:
                self.speed = round(float(data["gcode_move"]["speed_factor"]) * 100)
                self.labels["speedfactor"].set_label(f"  {self.speed:3}%")

    def change_babystepping(self, widget, direction):
        if direction == "reset":
            self.z_offset = 0.0
            script = "SET_GCODE_OFFSET Z=0 MOVE=1"
        elif direction == "+":
            self.z_offset += float(self.z_delta)
        elif direction == "-":
            self.z_offset -= float(self.z_delta)
        if direction != "reset":
            script = f"SET_GCODE_OFFSET Z_ADJUST={direction}{self.z_delta} MOVE=1"
        self.z_serial += 1
        serial = self.z_serial
        self.z_pending.add(serial)
        self.render_z()
        sent = self._screen._ws.send_method("printer.gcode.script", {"script": script}, self.z_response, serial)
        if sent is False:
            self.z_response({"error": {"message": _("Failed to send command")}}, serial=serial)

    def render_z(self):
        color = "#e3ad57" if self.z_pending else "#aaaaaa"
        self.labels["zoffset"].set_markup(
            f'<span foreground="{color}" size="16128" weight="semibold">{escape(_("Requested"))}</span>\n'
            f'<span size="13824">{self.z_offset:+.2f}<span size="12288">mm</span></span>\n'
            f'<span foreground="#aaaaaa" size="16128" weight="semibold">{escape(_("Reported"))}</span>\n'
            f'<span size="13824">{self.z_reported:+.2f}<span size="12288">mm</span></span>'
        )

    def z_response(self, response, method=None, params=None, serial=None):
        if serial not in self.z_pending:
            return
        self.z_pending.discard(serial)
        if "error" in response:
            self._screen.show_popup_message(str(response["error"].get("message", "Z offset error")))
        self.render_z()
        if not self.z_pending:
            self._screen._ws.send_method("printer.objects.query",
                {"objects": {"gcode_move": ["homing_origin"]}}, self.z_readback, self.z_serial)

    def z_readback(self, response, method=None, params=None, serial=None):
        if serial != self.z_serial or self.z_pending:
            return
        origin = response.get("result", {}).get("status", {}).get("gcode_move", {}).get("homing_origin")
        if origin is not None:
            self.z_reported = float(origin[2])
            self.z_offset = self.z_reported
            self.render_z()

    def change_extrusion(self, widget, direction):
        if direction == "+":
            self.extrusion += int(self.e_delta)
        elif direction == "-":
            self.extrusion -= int(self.e_delta)
        elif direction == "reset":
            self.extrusion = 100
        self.extrusion = max(self.extrusion, 1)
        self.labels["extrudefactor"].set_label(f"  {self.extrusion:3}%")
        self._screen._send_action(
            widget,
            "printer.gcode.script",
            {"script": KlippyGcodes.set_extrusion_rate(self.extrusion)},
        )

    def change_speed(self, widget, direction):
        if direction == "+":
            self.speed += int(self.s_delta)
        elif direction == "-":
            self.speed -= int(self.s_delta)
        elif direction == "reset":
            self.speed = 100

        self.speed = max(self.speed, 1)
        self.labels["speedfactor"].set_label(f"  {self.speed:3}%")
        self._screen._send_action(
            widget, "printer.gcode.script", {"script": KlippyGcodes.set_speed_rate(self.speed)}
        )
