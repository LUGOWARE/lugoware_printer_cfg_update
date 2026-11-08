import re
import time

import gi

gi.require_version("Gtk", "3.0")
from datetime import datetime

from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel

COLORS = {
    "command": "#bad8ff",
    "error": "#ff6975",
    "response": "#b8b8b8",
    "time": "grey",
    "warning": "#c9c9c9",
}


class Panel(ScreenPanel):
    _lugo_provider = None
    def __init__(self, screen, title):
        title = title or _("Console")
        super().__init__(screen, title)
        self.content.get_style_context().add_class("lugo-theme")
        if Panel._lugo_provider is None:
            provider = Gtk.CssProvider()
            provider.load_from_data(b'\n            .lugo-theme button {\n                background-image: none; background-color: #252525;\n                 \n                box-shadow: none; text-shadow: none;\n              border-radius: .25em;  border: 1px solid #252525; }\n            .lugo-theme button:active, .lugo-theme button:checked,\n            .lugo-theme button.button_active {\n                background-color: #424242; \n              border-radius: .25em;  border-color: #424242; }\n            .lugo-theme button:disabled { background-color: #252525;    border-radius: .25em;  border-color: #252525; }\n            .lugo-theme .frame-item, .lugo-theme .tz-current {\n                background-color: #252525; \n                \n             border: 0; border-radius: .25em; }\n            .lugo-theme .timezone-panel button.tz-apply {     border-radius: .25em;  border: 1px solid #252525; }\n            .lugo-theme entry {\n                background-image: none; background-color: #121212;\n                border: 1px solid #252525; border-radius: 7px; color: #e2e2e2;\n            }\n            .lugo-theme entry:focus { border-color: #424242; }\n            .lugo-theme textview, .lugo-theme textview text { background-color: #121212; }\n            .lugo-theme switch { background-image: none; background-color: #1c1c1c; border: 1px solid #282828; border-radius: 20px; }\n            .lugo-theme switch:checked { background-color: #2f5631; }\n            .lugo-theme switch slider { background-image: none; background-color: #e2e2e2; border-radius: 20px; }\n\n.lugo-theme button, .lugo-theme button:active, .lugo-theme button:disabled,\n.lugo-theme button.button_active, .lugo-theme button.lugo-diameter,\n.lugo-theme button.lugo-selected, .lugo-theme button.lugo-diameter.lugo-selected { border: 0; }\n.lugo-theme .frame-item button, .lugo-theme .tz-current button { border: 1px solid #252525; }\n\n.fan_controls button,\n.fine-card button,\n.lugo-temperature-control button,\n.lugo-diagnostics .diagnostic-card button,\n.lugo-theme .frame-item button,\n.lugo-theme .tz-current button,\n.lugo-settings .frame-item button { background-color: #1f1f1f; }\n.fan_controls button:active,\n.fan_controls button:checked,\n.fan_controls button.selected,\n.fan_controls button.lugo-selected,\n.fan_controls button.button_active,\n.fan_controls button.lugo-tapped,\n.fine-card button:active,\n.fine-card button:checked,\n.fine-card button.selected,\n.fine-card button.lugo-selected,\n.fine-card button.button_active,\n.fine-card button.lugo-tapped,\n.lugo-temperature-control button:active,\n.lugo-temperature-control button:checked,\n.lugo-temperature-control button.selected,\n.lugo-temperature-control button.lugo-selected,\n.lugo-temperature-control button.button_active,\n.lugo-temperature-control button.lugo-tapped,\n.lugo-diagnostics .diagnostic-card button:active,\n.lugo-diagnostics .diagnostic-card button:checked,\n.lugo-diagnostics .diagnostic-card button.selected,\n.lugo-diagnostics .diagnostic-card button.lugo-selected,\n.lugo-diagnostics .diagnostic-card button.button_active,\n.lugo-diagnostics .diagnostic-card button.lugo-tapped,\n.lugo-theme .frame-item button:active,\n.lugo-theme .frame-item button:checked,\n.lugo-theme .frame-item button.selected,\n.lugo-theme .frame-item button.lugo-selected,\n.lugo-theme .frame-item button.button_active,\n.lugo-theme .frame-item button.lugo-tapped,\n.lugo-theme .tz-current button:active,\n.lugo-theme .tz-current button:checked,\n.lugo-theme .tz-current button.selected,\n.lugo-theme .tz-current button.lugo-selected,\n.lugo-theme .tz-current button.button_active,\n.lugo-theme .tz-current button.lugo-tapped,\n.lugo-settings .frame-item button:active,\n.lugo-settings .frame-item button:checked,\n.lugo-settings .frame-item button.selected,\n.lugo-settings .frame-item button.lugo-selected,\n.lugo-settings .frame-item button.button_active,\n.lugo-settings .frame-item button.lugo-tapped,\n.lugo-extrusion button.lugo-inner-control:active,\n.lugo-extrusion button.lugo-inner-control:checked,\n.lugo-extrusion button.lugo-inner-control.selected,\n.lugo-extrusion button.lugo-inner-control.lugo-selected,\n.lugo-extrusion button.lugo-inner-control.button_active,\n.lugo-extrusion button.lugo-inner-control.lugo-tapped { background-color: #424242; }\n')
            Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(), provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER + 3)
            Panel._lugo_provider = provider

        self.autoscroll = True

        o1_button = self._gtk.Button(
            "arrow-down", _("Auto-scroll") + " ", None, self.bts, Gtk.PositionType.RIGHT, 1
        )
        o1_button.get_style_context().add_class("button_active")
        o1_button.get_style_context().add_class("buttons_slim")
        o1_button.connect("clicked", self.set_autoscroll)

        o2_button = self._gtk.Button(
            "refresh", _("Clear") + " ", None, self.bts, Gtk.PositionType.RIGHT, 1
        )
        o2_button.get_style_context().add_class("buttons_slim")
        o2_button.connect("clicked", self.clear)

        options = Gtk.Grid(vexpand=False)
        options.attach(o1_button, 0, 0, 1, 1)
        options.attach(o2_button, 1, 0, 1, 1)

        sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)

        tb = Gtk.TextBuffer()
        tv = Gtk.TextView(buffer=tb, editable=False, cursor_visible=False)
        tv.connect("size-allocate", self._autoscroll)
        tv.connect("touch-event", self._screen.remove_keyboard)
        tv.connect("button-press-event", self._screen.remove_keyboard)

        sw.add(tv)

        ebox = Gtk.Box(hexpand=True, vexpand=False)

        entry = Gtk.Entry(hexpand=True, vexpand=False)
        entry.connect("button-press-event", self._screen.show_keyboard)
        entry.connect("touch-event", self._screen.show_keyboard)
        entry.connect("button-press-event", self._screen.show_keyboard)
        entry.connect("activate", self._send_command)
        entry.grab_focus_without_selecting()

        enter = self._gtk.Button(
            "resume", " " + _("Send") + " ", None, 0.66, Gtk.PositionType.RIGHT, 1
        )
        enter.get_style_context().add_class("buttons_slim")

        enter.set_hexpand(False)
        enter.connect("clicked", self._send_command)

        ebox.add(entry)
        ebox.add(enter)

        self.labels.update({"entry": entry, "sw": sw, "tb": tb, "tv": tv})

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.pack_start(options, False, False, 5)
        content_box.add(sw)
        content_box.pack_end(ebox, False, False, 0)
        self.content.add(content_box)

    def clear(self, widget=None):
        self.labels["tb"].set_text("")

    def add_gcode(self, msgtype, msgtime, message):
        if msgtype == "command":
            color = COLORS["command"]
        elif message.startswith("!!"):
            color = COLORS["error"]
            message = message.replace("!! ", "")
        elif message.startswith("//"):
            color = COLORS["warning"]
            message = message.replace("// ", "")
        elif re.match("^(?:ok\\s+)?(B|C|T\\d*):", message):
            return
        else:
            color = COLORS["response"]

        message = f'<span color="{color}"><b>{message}</b></span>'

        message = message.replace("\n", "\n         ")

        self.labels["tb"].insert_markup(
            self.labels["tb"].get_end_iter(),
            f'\n<span color="{COLORS["time"]}">'
            f"{datetime.fromtimestamp(msgtime).strftime('%H:%M:%S')}</span> {message}",
            -1,
        )
        # Limit the length
        if self.labels["tb"].get_line_count() > 999:
            self.labels["tb"].delete(
                self.labels["tb"].get_iter_at_line(0), self.labels["tb"].get_iter_at_line(1)
            )

    def gcode_response(self, result, method, params):
        if method != "server.gcode_store":
            return

        for resp in result["result"]["gcode_store"]:
            self.add_gcode(resp["type"], resp["time"], resp["message"])

    def process_update(self, action, data):
        if action == "notify_gcode_response":
            self.add_gcode("response", time.time(), data)

    def set_autoscroll(self, widget):
        self.autoscroll ^= True
        self.toggle_active_class(widget, self.autoscroll)

    @staticmethod
    def toggle_active_class(widget, cond):
        if cond:
            widget.get_style_context().add_class("button_active")
        else:
            widget.get_style_context().remove_class("button_active")

    def _autoscroll(self, *args):
        if self.autoscroll:
            adj = self.labels["sw"].get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _send_command(self, *args):
        cmd = self.labels["entry"].get_text()
        self.labels["entry"].set_text("")
        self._screen.remove_keyboard()

        self.add_gcode("command", time.time(), cmd)
        self._screen._ws.api.gcode_script(cmd)

    def activate(self):
        self.clear()
        self._screen._ws.send_method("server.gcode_store", {"count": 100}, self.gcode_response)
