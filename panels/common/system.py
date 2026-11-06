import datetime
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("System")
        super().__init__(screen, title)
        self.current_row = 0
        self.mem_multiplier = None
        self.cpu_flowbox = None
        self.cpu_labels = []
        self.scales = {}
        self.labels = {}
        self.grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        self.backend = "Wayland" if screen.wayland else "XServer"
        self.disk_usages = []
        self._roots_pending = 0
        self._activation_id = 0

        self.sysinfo = screen.printer.system_info

        if self.sysinfo:
            self.create_layout()
        else:
            self.content.add(Gtk.Label(label=_("No info available"), vexpand=True))

    def back(self):
        if not self.sysinfo:
            self._screen.panels_reinit.append("system")
        return False

    def activate(self):
        self._activation_id += 1
        self._current_activation = self._activation_id
        self._roots_pending = 0
        self.disk_usages = []
        for widget in self.labels.get("disk_usage", []):
            try:
                self.grid.remove(widget)
            except Exception:
                pass
            widget.destroy()
        for widget in self.scales.get("disk_usage", []):
            try:
                self.grid.remove(widget)
            except Exception:
                pass
            widget.destroy()
        self.labels["disk_usage"] = []
        self.scales["disk_usage"] = []
        self._screen._ws.api.get_file_roots(self._on_roots_received)

    def _on_roots_received(self, data, method, params):
        if getattr(self, "_activation_id", 0) != self._current_activation:
            return
        if "error" in data:
            logging.error(f"Error getting file roots {data['error']}")
            self._update_disk_display()
            return
        roots = data.get("result", [])
        if not roots:
            logging.debug("No file roots found, falling back to gcodes")
            self._roots_pending = 1
            self._screen._ws.api.get_dir_info(self._update_disk_usage, "gcodes")
            return
        for root in roots:
            root_name = root.get("name", "unknown")
            self._roots_pending += 1
            self._screen._ws.api.get_dir_info(self._update_disk_usage, root_name)

    def _update_disk_usage(self, data, method, params):
        if getattr(self, "_activation_id", 0) != self._current_activation:
            return
        if "error" in data:
            logging.error(f"Error getting disk usage {data['error']}")
            self._roots_pending -= 1
            if self._roots_pending <= 0:
                self._update_disk_display()
            return
        if "disk_usage" not in data.get("result", {}):
            logging.error(data)
            self._roots_pending -= 1
            if self._roots_pending <= 0:
                self._update_disk_display()
            return
        disk_usage = data["result"]["disk_usage"]
        root_info = data["result"].get("root_info", {})
        root_name = root_info.get("name") or (
            params.get("path") if isinstance(params, dict) else str(params)
        )
        key = (disk_usage.get("total"), disk_usage.get("used"), disk_usage.get("free"))
        for entry in self.disk_usages:
            if (
                entry["disk_usage"].get("total") == key[0]
                and entry["disk_usage"].get("used") == key[1]
                and entry["disk_usage"].get("free") == key[2]
            ):
                if root_name not in entry["names"]:
                    entry["names"].append(root_name)
                logging.debug(f"Root {root_name} merged with existing entry")
                self._roots_pending -= 1
                if self._roots_pending <= 0:
                    self._update_disk_display()
                return
        self.disk_usages.append({"names": [root_name], "disk_usage": disk_usage})
        self._roots_pending -= 1
        if self._roots_pending <= 0:
            self._update_disk_display()

    def _update_disk_display(self):
        GLib.idle_add(self._ui_rebuild_disks)

    def _ui_rebuild_disks(self):
        for child in self.disk_container.get_children():
            self.disk_container.remove(child)
            child.destroy()

        self.labels["disk_usage"] = []
        self.scales["disk_usage"] = []

        for du in self.disk_usages:
            names = ", ".join(du["names"])
            usage = du["disk_usage"]
            used = usage.get("used", 0)
            total = usage.get("total", 1)
            used_percent = (used / total) * 100 if total > 0 else 0

            label = Gtk.Label(label="", xalign=0, wrap=True, max_width_chars=50)
            label.set_line_wrap_mode(Pango.WrapMode.WORD)
            label.get_style_context().add_class("printing-info")
            if len(self.disk_usages) == 1 and len(du["names"]) > 1:
                label.set_label(
                    f"{_('Disk')}: {self.format_size(used)} / {self.format_size(total)}"
                )
            else:
                label.set_label(
                    f"{_('Disk')} ({names}): {self.format_size(used)} / {self.format_size(total)}"
                )
            self.disk_container.pack_start(label, False, False, 0)
            self.labels["disk_usage"].append(label)

            scale = Gtk.ProgressBar(hexpand=True, show_text=False)
            scale.set_fraction(used_percent / 100)
            self.disk_container.pack_start(scale, False, False, 2)
            self.scales["disk_usage"].append(scale)

        self.disk_container.show_all()
        return False

    def card(self, title=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        box.get_style_context().add_class("system-card")
        if title:
            label = Gtk.Label(label=title, xalign=0)
            label.get_style_context().add_class("system-heading")
            box.pack_start(label, False, False, 0)
        return box

    def create_layout(self):
        self.grid.set_row_spacing(10)
        self.grid.set_margin_start(8)
        self.grid.set_margin_end(8)
        self.grid.set_margin_top(6)
        self.grid.set_margin_bottom(8)
        self.cpu_count = int(self.sysinfo.get("cpu_info", {}).get("cpu_count", 0))
        for key in ("cpu_usage", "memory_usage"):
            card = self.card()
            self.labels[key] = Gtk.Label(label="CPU" if key == "cpu_usage" else _("Memory"), xalign=0)
            self.labels[key].get_style_context().add_class("system-heading")
            card.pack_start(self.labels[key], False, False, 0)
            self.scales[key] = Gtk.ProgressBar(hexpand=True, show_text=False)
            card.pack_start(self.scales[key], False, False, 0)
            if key == "cpu_usage":
                cores = Gtk.Box(spacing=6, homogeneous=True)
                for i in range(self.cpu_count):
                    label = Gtk.Label(label=f"{_('Core')} {i+1}\n—", hexpand=True)
                    label.get_style_context().add_class("system-core")
                    self.cpu_labels.append(label)
                    cores.pack_start(label, True, True, 0)
                card.pack_start(cores, False, False, 0)
            self.grid.attach(card, 0, self.current_row, 2, 1)
            self.current_row += 1
        self.labels["disk_usage"] = []
        self.scales["disk_usage"] = []
        self.disk_container = self.card()
        self.grid.attach(self.disk_container, 0, self.current_row, 2, 1)
        self.current_row += 1
        self.populate_info()
        css = Gtk.CssProvider()
        css.load_from_data(b'\n            .system-card { background-color: #252525; \n                 padding: 12px;  border: 0; border-radius: .25em; }\n            .system-card label { font-size: 17px; }\n            .system-card .system-heading { font-size: 20px; font-weight: bold; }\n            .system-card .system-core { font-size: 15px; color: #bbbbbb; }\n            .system-card progressbar trough { min-height: 12px; background-color: #111111; border-radius: 4px; }\n            .system-card progressbar progress { min-height: 12px; background-color: #305730; border-radius: 4px; }\n        ')
        # Scoped CSS also covers disk labels created asynchronously.
        from gi.repository import Gdk
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.grid)
        self.content.add(scroll)

    def set_mem_multiplier(self, data):
        memory_units = data.get("memory_units", "kB").lower()
        units_mapping = {
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
            "pb": 1024**5,
        }
        self.mem_multiplier = units_mapping.get(memory_units, 1)

    def add_label_to_grid(self, text, column, bold=False):
        if bold:
            text = f"<b>{text}</b>"
        label = Gtk.Label(label=text, use_markup=True, xalign=0, wrap=True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.grid.attach(label, column, self.current_row, 1, 1)
        self.current_row += 1

    def populate_info(self):
        summary = self.card(_("System"))
        for key in ("date", "backend"):
            self.labels[key] = Gtk.Label(label="", xalign=0, wrap=True)
            summary.pack_start(self.labels[key], False, False, 0)
        self.grid.attach(summary, 0, self.current_row, 2, 1)
        self.current_row += 1
        titles = {"cpu_info": _("Processor"), "distribution": _("Operating system"),
                  "python": "Python", "network": _("Network"), "sd_info": _("Storage")}
        skip = {"virtualization", "provider", "available_services", "service_state", "instance_ids"}
        for category, data in self.sysinfo.items():
            if category in skip or not data:
                continue
            card = self.card()
            expander = Gtk.Expander(label=titles.get(category, _(self.prettify(category))))
            expander.set_expanded(True)
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            details.set_margin_top(10)
            def add_rows(values):
                for key, value in values.items():
                    if key in ("version_parts", "memory_units") or value is None or value == "":
                        continue
                    if isinstance(value, dict):
                        add_rows(value)
                        continue
                    if key == "total_memory":
                        self.set_mem_multiplier(values)
                        value = self.format_size(int(value) * self.mem_multiplier)
                    if isinstance(value, list):
                        value = ", ".join(str(v.get("address", v)) if isinstance(v, dict) else str(v) for v in value)
                    label = Gtk.Label(label=f"{_(self.prettify(key))}: {value}", xalign=0, wrap=True)
                    label.set_max_width_chars(36)
                    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    details.pack_start(label, False, False, 0)
            add_rows(data if isinstance(data, dict) else {category: data})
            expander.add(details)
            card.pack_start(expander, False, False, 0)
            self.grid.attach(card, 0, self.current_row, 2, 1)
            self.current_row += 1

    def process_update(self, action, data):
        if not self.sysinfo:
            return
        if action == "notify_proc_stat_update":
            self.labels["cpu_usage"].set_label(f"CPU\n{_('Overall usage')}  {data['system_cpu_usage']['cpu']:.0f}%")
            self.scales["cpu_usage"].set_fraction(float(data["system_cpu_usage"]["cpu"]) / 100)
            for i, label in enumerate(self.cpu_labels):
                label.set_label(f"{_('Core')} {i+1}\n{data['system_cpu_usage'].get(f'cpu{i}', 0):.0f}%")

            self.labels["memory_usage"].set_label(
                _("Memory")
                + f": {(data['system_memory']['used'] / data['system_memory']['total']) * 100:.0f}%"
            )
            self.scales["memory_usage"].set_fraction(
                float(data["system_memory"]["used"]) / float(data["system_memory"]["total"])
            )

        now = datetime.datetime.now().astimezone()
        self.labels["date"].set_label(now.strftime("%Y-%m-%d  %H:%M:%S %Z"))

        self.labels["backend"].set_label(_("Display") + ": " + self.backend)
