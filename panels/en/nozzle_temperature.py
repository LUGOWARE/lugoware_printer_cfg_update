"""Reuse the installed temperature panel, displaying only nozzle heaters."""
import re

from gi.repository import Gtk
from panels.temperature import Panel as TemperaturePanel


class Panel(TemperaturePanel):
    def show_numpad(self, widget, device=None):
        super().show_numpad(widget, device)
        self._hide_pid_buttons(self.labels["keypad"])

    @classmethod
    def _hide_pid_buttons(cls, widget):
        def texts(node):
            if isinstance(node, Gtk.Label):
                return [node.get_text()]
            return [text for child in node.get_children() for text in texts(child)] if isinstance(node, Gtk.Container) else []
        if isinstance(widget, Gtk.Button) and any("PID" in text.upper() for text in texts(widget)):
            widget.set_no_show_all(True)
            widget.hide()
            return
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                cls._hide_pid_buttons(child)

    def add_device(self, device):
        if not re.fullmatch(r"extruder\d*", device):
            return False
        return super().add_device(device)

    def update_graph_visibility(self, force_hide=False):
        # Keep the space above the keypad dedicated to centered nozzle rows.
        return super().update_graph_visibility(force_hide=True)

    def activate(self):
        super().activate()
        if not self.devices:
            self._screen.show_popup_message("No nozzle heaters available.")
            return
        self.labels["devices"].set_valign(Gtk.Align.CENTER)
        self.labels["devices"].set_halign(Gtk.Align.FILL)
        self.labels["devices"].set_hexpand(True)
        self.labels["devices"].set_row_homogeneous(True)
        heater = self._printer.get_stat("toolhead", "extruder")
        if heater not in self.devices:
            heater = next(iter(self.devices))
        self.active_heaters = [heater]
        if self.active_heater is None:
            self.show_numpad(None, heater)
