import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.objectmap import ObjectMap


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Exclude Object")
        super().__init__(screen, title)
        self._screen = screen
        self.object_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self.buttons = {}
        self.current_object = self._gtk.Button(
            "exclude", "", scale=self.bts, position=Gtk.PositionType.LEFT, lines=1
        )
        self.current_object.connect("clicked", self.exclude_current)
        self.current_object.set_vexpand(False)
        self.excluded_objects = self._printer.get_stat("exclude_object", "excluded_objects") or []
        logging.info(f"Excluded: {self.excluded_objects}")
        self.objects = self._printer.get_stat("exclude_object", "objects") or []
        self.labels["map"] = None
        for obj in self.objects:
            logging.info(f"Adding {obj['name']}")
            self.add_object(obj["name"])

        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
        scroll.set_overlay_scrolling(False)
        scroll.add(self.object_list)

        grid = Gtk.Grid(column_homogeneous=True)
        grid.attach(self.current_object, 0, 0, 2, 1)
        grid.attach(Gtk.Separator(), 0, 1, 2, 1)

        if self.objects and "polygon" in self.objects[0]:
            self.labels["map"] = ObjectMap(self._screen, self._printer, self._gtk.font_size)
            self.labels["map"].exclude_callback = lambda name: self.exclude_object(None, name)
            if self._screen.vertical_mode:
                grid.attach(self.labels["map"], 0, 2, 2, 1)
                grid.attach(scroll, 0, 3, 2, 1)
            else:
                grid.attach(self.labels["map"], 0, 2, 1, 1)
                grid.attach(scroll, 1, 2, 1, 1)
        else:
            grid.attach(scroll, 0, 2, 2, 1)

        self.content.add(grid)
        self.content.show_all()

    def add_object(self, name):
        if name in self.buttons:
            return
        button = self._gtk.Button()
        for child in button.get_children():
            button.remove(child)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_start(10)
        row.set_margin_end(8)
        title = Gtk.Label(label=self.object_label(name), xalign=0, hexpand=True)
        title.set_halign(Gtk.Align.FILL)
        title.set_width_chars(1)
        title.set_line_wrap(True)
        title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        status = Gtk.Label(xalign=1)
        status.set_halign(Gtk.Align.END)
        status.set_max_width_chars(12)
        status.set_line_wrap(True)
        row.pack_start(title, True, True, 0)
        row.pack_end(status, False, False, 0)
        button.add(row)
        button.object_title = title
        button.object_status = status
        button.connect('clicked', self.exclude_object, name)
        button.get_style_context().add_class('frame-item')
        self.buttons[name] = button
        self.object_list.add(button)
        self.update_object_row(name, button)

    def update_object_row(self, name, button):
        excluded = name in self.excluded_objects
        button.object_title.set_text(self.object_label(name))
        pending = name in self.pending_objects()
        button.object_status.set_text('✕ ' + _('Excluded') if excluded else (_('Exclusion pending') if pending else ''))
        button.set_sensitive(not excluded)

    def object_label(self, name):
        number = next((i for i, obj in enumerate(self.objects, 1) if obj['name'] == name), '?')
        text = f"[{number}] {name.replace('_', ' ')}"
        return text

    def pending_objects(self):
        return (self._printer.get_stat('exclude_tool_guard') or {}).get('pending_excludes', [])

    def exclude_object(self, widget, name):
        if name in self.excluded_objects:
            return

        if name in self.pending_objects():
            self._screen._send_action(widget, 'printer.exclude_tool_guard.request',
                                      {'name': name, 'action': 'cancel'})
            return

        if len(set(self.excluded_objects) | set(self.pending_objects())) >= len(self.objects) - 1:
            # Do not exclude the last object, this is a workaround for a bug of klipper that starts
            # to move the toolhead really fast skipping gcode until the file ends
            # Remove this if they fix it.
            self._screen._confirm_send_action(
                widget,
                _("Are you sure you wish to cancel this print?"),
                "printer.print.cancel",
            )
            return
        script = {"name": name, "action": "exclude"}
        self._screen._confirm_send_action(
            widget,
            _("Are you sure do you want to exclude the object?") + f"\n\n{self.object_label(name)}",
            "printer.exclude_tool_guard.request",
            script,
        )

    def exclude_current(self, widget):
        current = self._printer.data["exclude_object"]["current_object"]
        if current is None:
            return
        self.exclude_object(widget, f"{current}")

    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'exclude_tool_guard' in data:
                for name, button in self.buttons.items():
                    self.update_object_row(name, button)
                self.update_graph()
            if "exclude_object" in data:
                if "objects" in data["exclude_object"]:  # Update objects
                    self.objects = data["exclude_object"]["objects"]
                    logging.info(f"Objects: {data['exclude_object']['objects']}")
                    for obj in self.buttons:
                        self.object_list.remove(self.buttons[obj])
                    self.buttons = {}
                    for obj in self.objects:
                        logging.info(f"Adding {obj['name']}")
                        self.add_object(obj["name"])
                    self.content.show_all()
                if "current_object" in data["exclude_object"]:  # Update objects
                    # Update current objects
                    if data["exclude_object"]["current_object"]:
                        self.current_object.set_label(
                            f"{data['exclude_object']['current_object'].replace('_', ' ')}"
                        )
                    self.update_graph()
                if "excluded_objects" in data["exclude_object"]:  # Update objects
                    # Update excluded objects
                    logging.info(f"Excluded objects: {data['exclude_object']['excluded_objects']}")
                    self.excluded_objects = data["exclude_object"]["excluded_objects"]
                    for name, button in self.buttons.items():
                        self.update_object_row(name, button)
                    self.update_graph()

        elif action == "notify_gcode_response" and "Excluding object" in data:
            self._screen.show_popup_message(data, level=1)
            self.update_graph()

    def activate(self):
        self.update_graph()

    def update_graph(self):
        self.excluded_objects = self._printer.get_stat('exclude_object', 'excluded_objects') or []
        for name, button in self.buttons.items():
            self.update_object_row(name, button)
        if self.labels["map"]:
            self.labels["map"].queue_draw()
